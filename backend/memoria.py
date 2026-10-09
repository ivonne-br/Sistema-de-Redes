"""Historial acotado de observaciones ARP dentro de un proceso."""

from collections import deque
from copy import deepcopy
from threading import Lock
from time import monotonic

from backend.configuracion import ConfiguracionMemoria
from backend.descubrimiento import normalizar_contexto_observacion

_SIN_FILTRO = object()
_ESTADOS = {
    "observacion_correcta", "observacion_parcial", "sin_entradas",
    "error_interpretacion", "error_contexto",
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

    def __init__(self, configuracion=None, *, reloj=monotonic):
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

    def guardar(self, observacion):
        """Guarda una observación interna v1 sin fusionar resultados ni ocultar fallos."""
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
        if (copia["contexto"] is None) != (copia["estado"] == "error_contexto"):
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
            self._registros.append((ahora, clave, copia))

    def historial(self, *, contexto=_SIN_FILTRO):
        """Devuelve copias en orden de inserción; contexto=None filtra los fallos sin contexto."""
        clave = clave_contexto(contexto) if contexto is not _SIN_FILTRO else _SIN_FILTRO
        with self._lock:
            self._purgar(self._reloj())
            return [deepcopy(registro[2]) for registro in self._registros
                    if clave is _SIN_FILTRO or registro[1] == clave]

    def ultima(self, *, contexto=_SIN_FILTRO):
        """Devuelve el último intento conservado, aunque haya fallado, o None."""
        clave = clave_contexto(contexto) if contexto is not _SIN_FILTRO else _SIN_FILTRO
        with self._lock:
            self._purgar(self._reloj())
            for registro in reversed(self._registros):
                if clave is _SIN_FILTRO or registro[1] == clave:
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
