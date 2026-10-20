"""Recibe observaciones ARP y conserva copias acotadas para ConsultaARP.

Entrega historial y edades; el reloj compartido cuenta también el reposo para
expirar datos. La configuración y un reloj alternativo son entradas inyectables.
"""

from collections import deque
from copy import deepcopy
from threading import Lock
from backend.reloj import tiempo_continuo
import math

from backend.configuracion import ConfiguracionMemoria
from backend.descubrimiento import normalizar_contexto_observacion

_SIN_FILTRO = object()
_ESTADOS = {
    "observacion_correcta", "observacion_parcial", "sin_entradas",
    "error_interpretacion", "error_contexto",
    "error_recoleccion", "sin_datos_visibles",
}


def clave_contexto(contexto):
    """Compara configuración IPv4; no identifica físicamente una red."""
    if contexto is None:
        return None
    normalizado = normalizar_contexto_observacion(contexto)
    return tuple(normalizado[campo] for campo in (
        "interfaz", "ipv4_local", "subred", "gateway",
    ))


class MemoriaObservaciones:
    """Guarda copias de observar_arp; expira por tiempo desde su inserción."""

    def __init__(self, configuracion=None, *, reloj=tiempo_continuo):
        self._configuracion = configuracion if configuracion is not None else ConfiguracionMemoria()
        if not isinstance(self._configuracion, ConfiguracionMemoria):
            raise TypeError("configuracion debe ser una ConfiguracionMemoria.")
        if not callable(reloj):
            raise TypeError("reloj debe ser una función monotónica.")
        self._reloj = reloj
        self._registros = deque()
        self._lock = Lock()
        self._por_capacidad = 0
        self._por_antiguedad = 0

    def _purgar(self, ahora):
        """Retira vencidas antes de guardar o consultar; se llama bajo el lock."""
        while self._registros and ahora - self._registros[0][0] >= self._configuracion.retencion_s:
            self._registros.popleft()
            self._por_antiguedad += 1

    def guardar(self, observacion, *, demora_captura_s=None):
        """Guarda una observación interna v1 sin fusionar resultados ni ocultar fallos."""
        # La demora se mide desde el fin de la consulta hasta la entrega al almacén.
        # None significa que no se conoce la edad de captura (por ejemplo, stdin).
        if demora_captura_s is not None:
            if type(demora_captura_s) not in (int, float):
                raise TypeError("demora_captura_s debe ser un número o None.")
            if demora_captura_s < 0 or not math.isfinite(demora_captura_s):
                raise ValueError("demora_captura_s debe ser finita y no negativa.")
        entrega = self._reloj()
        if not isinstance(observacion, dict):
            raise ValueError("La observación debe ser un diccionario producido por observar_arp.")
        copia = deepcopy(observacion)
        requeridos = {
            "version_esquema", "id_observacion", "estado", "contexto", "entradas",
            "errores", "resumen", "fuente", "fuente_contexto", "consulta_contexto",
            "inicio_procesamiento", "fin_procesamiento", "momento_captura_origen",
        }
        if not requeridos.issubset(copia):
            raise ValueError("La observación está incompleta.")
        if type(copia["version_esquema"]) is not int or copia["version_esquema"] != 1:
            raise ValueError("Solo se admiten observaciones de versión 1.")
        if not isinstance(copia["id_observacion"], str) or not copia["id_observacion"].strip():
            raise ValueError("La observación requiere un identificador.")
        if not isinstance(copia["estado"], str) or copia["estado"] not in _ESTADOS:
            raise ValueError("Estado de observación no reconocido.")
        if not isinstance(copia["entradas"], list) or not isinstance(copia["errores"], list) or not isinstance(copia["resumen"], dict):
            raise ValueError("Entradas, errores o resumen tienen un tipo incorrecto.")
        fallo_fuente = copia["estado"] in ("error_recoleccion", "sin_datos_visibles")
        if fallo_fuente:
            consulta = copia.get("consulta_arp", {})
            if not isinstance(consulta, dict) or consulta.get("estado") != copia["estado"] or copia["entradas"]:
                raise ValueError("El fallo ARP requiere su consulta y no admite entradas.")
            if copia["resumen"].get("vecinos_candidatos") is not None or copia["resumen"].get("por_categoria") is not None:
                raise ValueError("Un fallo ARP no permite recuentos de clasificación.")
            contexto_consultado = copia["consulta_contexto"]
            if not isinstance(contexto_consultado, dict) or (
                (copia["contexto"] is not None) != (contexto_consultado.get("estado") == "contexto_correcto")
            ):
                raise ValueError("El contexto no corresponde a su consulta.")
        elif (copia["contexto"] is None) != (copia["estado"] == "error_contexto"):
            raise ValueError("El contexto no corresponde al estado de la observación.")
        clave = clave_contexto(copia["contexto"])
        with self._lock:
            ahora = self._reloj()
            self._purgar(ahora)
            if any(registro[2]["id_observacion"] == copia["id_observacion"] for registro in self._registros):
                raise ValueError("Ya existe una observación conservada con ese identificador.")
            if len(self._registros) >= self._configuracion.capacidad:
                self._registros.popleft()
                self._por_capacidad += 1
            captura = None if demora_captura_s is None else entrega - demora_captura_s
            self._registros.append((ahora, clave, copia, captura))

    def instantanea_temporal(self, *, id_ejecucion):
        """Copia una ejecución y calcula todas sus edades con un mismo instante."""
        with self._lock:
            ahora = self._reloj()
            self._purgar(ahora)
            return [
                {"observacion": deepcopy(registro[2]),
                 "antiguedad_s": None if registro[3] is None else ahora - registro[3]}
                for registro in self._registros
                if registro[2].get("id_ejecucion") == id_ejecucion
            ]

    def historial(self, *, contexto=_SIN_FILTRO, id_contexto=_SIN_FILTRO):
        """Devuelve copias en orden de inserción; contexto=None filtra los fallos sin contexto."""
        clave = clave_contexto(contexto) if contexto is not _SIN_FILTRO else _SIN_FILTRO
        with self._lock:
            self._purgar(self._reloj())
            return [deepcopy(registro[2]) for registro in self._registros
                    if (clave is _SIN_FILTRO or registro[1] == clave)
                    and (id_contexto is _SIN_FILTRO or registro[2].get("id_contexto", _SIN_FILTRO) == id_contexto)]

    def ultima(self, *, contexto=_SIN_FILTRO, id_contexto=_SIN_FILTRO):
        """Devuelve el último intento conservado, aunque haya fallado, o None."""
        clave = clave_contexto(contexto) if contexto is not _SIN_FILTRO else _SIN_FILTRO
        with self._lock:
            self._purgar(self._reloj())
            for registro in reversed(self._registros):
                if (clave is _SIN_FILTRO or registro[1] == clave) and (
                    id_contexto is _SIN_FILTRO or registro[2].get("id_contexto", _SIN_FILTRO) == id_contexto
                ):
                    return deepcopy(registro[2])
            return None

    def estadisticas(self):
        """Informa retención y descartes acumulados durante la vida de esta memoria."""
        with self._lock:
            self._purgar(self._reloj())
            return {
                "conservadas": len(self._registros),
                "capacidad": self._configuracion.capacidad,
                "retencion_s": self._configuracion.retencion_s,
                "descartadas_por_capacidad": self._por_capacidad,
                "descartadas_por_antiguedad": self._por_antiguedad,
            }
