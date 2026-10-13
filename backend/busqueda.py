"""Busca IPv4 locales con sondas periódicas, separadas de la evidencia ARP.

Recibe observaciones del coordinador y una sonda; conserva la última comprobación
por IPv4 del tramo actual y entrega copias con antigüedad a la API. No identifica
teléfonos, no confirma desconexiones y no modifica la memoria histórica ARP.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from ipaddress import IPv4Interface, IPv4Network
from threading import Event, Lock
from time import monotonic

from backend.configuracion import ConfiguracionSonda
from backend.sonda import ejecutar_sonda

_REDES_PRIVADAS = tuple(IPv4Network(r) for r in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def destinos_locales(contexto):
    """Devuelve hosts privados de una subred pequeña; excluye el Mac y gateway."""
    local = IPv4Interface(contexto["ipv4_local"])
    if not any(local.network.subnet_of(red) for red in _REDES_PRIVADAS):
        raise ValueError("La búsqueda automática solo admite subredes IPv4 privadas.")
    if local.network.num_addresses > 256:
        raise ValueError("La subred supera 256 direcciones; no se explora parcialmente.")
    excluidos = {str(local.ip), contexto.get("gateway")}
    return [str(ip) for ip in local.network.hosts() if str(ip) not in excluidos]


class BusquedaLocal:
    """Un barrido a la vez, ocho sondas como máximo y parada entre lotes."""

    def __init__(self, obtener_observacion, *, intervalo_s=60, sonda=ejecutar_sonda,
                 reloj=monotonic, parada=None):
        self._obtener = obtener_observacion
        self._intervalo = intervalo_s
        self._sonda = sonda
        self._reloj = reloj
        self._parada = parada if parada is not None else Event()
        self._lock = Lock()
        self._resultados = {}
        self._estado = {"estado": "esperando_contexto", "id_contexto": None, "contexto": None,
                        "detalle": None, "inicio_barrido": None, "fin_barrido": None,
                        "destinos_total": None, "consultados": 0}
        # Cada proceso está acotado a 2 s. El RTT no se usa para deducir salud.
        self._config_sonda = ConfiguracionSonda(espera_ms=1000, limite_proceso_s=2)

    def detener(self):
        """Solicita parada; las sondas ya iniciadas terminan dentro de su límite."""
        self._parada.set()

    def estado(self, *, id_contexto=None):
        """Devuelve copias; no renueva fechas y no mezcla datos de otro tramo."""
        with self._lock:
            estado = deepcopy(self._estado)
            resultados = deepcopy(self._resultados)
        if id_contexto != estado["id_contexto"]:
            estado = {"estado": "esperando_contexto", "id_contexto": id_contexto, "contexto": None,
                      "detalle": "Todavía no hay comprobaciones de este contexto.",
                      "inicio_barrido": None, "fin_barrido": None,
                      "destinos_total": None, "consultados": 0}
            resultados = {}
        ahora = self._reloj()
        filas = []
        for ip, registro in sorted(resultados.items()):
            fila = {k: v for k, v in registro.items() if not k.startswith("_")}
            fila["antiguedad_s"] = max(0, ahora - registro["_fin_monotonico"])
            fila["vigencia"] = "vigente" if fila["antiguedad_s"] < 180 else "desactualizado"
            filas.append(fila)
        return {**estado, "intervalo_s": self._intervalo, "vigencia_s": 180,
                "metodo": "icmp_ping_macos", "resultados": filas}

    def _mismo_contexto(self, identificador):
        observacion = self._obtener()
        return observacion is not None and observacion.get("id_contexto") == identificador

    def _comprobar(self, ip, identificador):
        """Consulta una IPv4 solo si el tramo sigue vigente; conserva fallo explícito."""
        if self._parada.is_set() or not self._mismo_contexto(identificador):
            return None
        try:
            resultado = self._sonda(ip, self._config_sonda)
            estado = resultado["estado"]
            if estado not in ("respuesta_valida", "sin_respuesta", "error_recoleccion"):
                raise ValueError("Estado de sonda desconocido.")
        except Exception:
            estado = "error_recoleccion"
        return {"ipv4": ip, "estado": estado,
                "fin_comprobacion": datetime.now(timezone.utc).isoformat(),
                "_fin_monotonico": self._reloj()}

    def barrer(self):
        """Comprueba una subred; cambio de tramo o parada interrumpe los lotes pendientes."""
        observacion = self._obtener()
        if not observacion or observacion.get("id_contexto") is None:
            with self._lock:
                self._estado.update(estado="esperando_contexto", id_contexto=None, contexto=None,
                                    detalle="El recolector aún no tiene un contexto IPv4 válido.",
                                    inicio_barrido=None, fin_barrido=None,
                                    destinos_total=None, consultados=0)
                self._resultados.clear()
            return
        identificador = observacion["id_contexto"]
        with self._lock:
            if identificador != self._estado["id_contexto"]:
                self._resultados.clear()
            self._estado.update(estado="buscando", id_contexto=identificador,
                                contexto=deepcopy(observacion.get("contexto")),
                                inicio_barrido=datetime.now(timezone.utc).isoformat(),
                                fin_barrido=None, consultados=0, detalle=None, destinos_total=None)
        try:
            destinos = destinos_locales(observacion["contexto"])
        except (ValueError, KeyError, TypeError) as error:
            with self._lock:
                self._estado.update(estado="omitida", detalle=str(error))
            return
        with self._lock:
            self._estado["destinos_total"] = len(destinos)
        # Primero verifica asociaciones ya conocidas; después busca IPv4 todavía desconocidas.
        conocidas = {e["ipv4"] for e in observacion.get("entradas", []) if e.get("categoria") == "vecino"}
        destinos.sort(key=lambda ip: (ip not in conocidas, int(IPv4Interface(ip).ip)))
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="sonda-local") as pool:
            for inicio in range(0, len(destinos), 8):
                if self._parada.is_set() or not self._mismo_contexto(identificador):
                    break
                lote = list(pool.map(lambda ip: self._comprobar(ip, identificador), destinos[inicio:inicio + 8]))
                if not self._mismo_contexto(identificador):
                    break
                with self._lock:
                    for resultado in lote:
                        if resultado is None:
                            continue
                        ip = resultado["ipv4"]
                        anterior = self._resultados.get(ip, {})
                        respondio = resultado["estado"] == "respuesta_valida"
                        resultado["respondio_alguna_vez"] = respondio or anterior.get("respondio_alguna_vez", False)
                        resultado["ultima_respuesta"] = (resultado["fin_comprobacion"] if respondio
                                                         else anterior.get("ultima_respuesta"))
                        self._resultados[ip] = resultado
                        self._estado["consultados"] += 1
        with self._lock:
            self._estado.update(estado="en_espera" if self._estado["consultados"] == len(destinos) else "interrumpida",
                                fin_barrido=datetime.now(timezone.utc).isoformat())

    def ejecutar(self):
        """Repite barridos sin solaparlos; espera desde el fin y se despierta al detener."""
        try:
            while not self._parada.is_set():
                self.barrer()
                with self._lock:
                    estado = self._estado["estado"]
                self._parada.wait(1 if estado in ("esperando_contexto", "interrumpida") else self._intervalo)
        except Exception:
            with self._lock:
                self._estado.update(estado="error", detalle="La búsqueda se detuvo por un error interno.")
        else:
            with self._lock:
                self._estado["estado"] = "detenida"
