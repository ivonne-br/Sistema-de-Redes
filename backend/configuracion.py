# Representar y validar los tiempos de sonda => objeto de configuración
"""Parámetros y validación de la sonda individual."""

from dataclasses import dataclass, field
import json
from pathlib import Path

@dataclass(frozen=True)
class ConfiguracionSonda:
    espera_ms: int = 1000
    limite_proceso_s: int = 5

    def __post_init__(self):
        if type(self.espera_ms) is not int:
            raise TypeError("espera_ms debe ser un número entero.")

        if type(self.limite_proceso_s) is not int:
            raise TypeError("limite_proceso_s debe ser un número entero.")

        if self.espera_ms <= 0:
            raise ValueError("espera_ms debe ser mayor que cero.")

        if self.limite_proceso_s <= 0:
            raise ValueError("limite_proceso_s debe ser mayor que cero.")

        if self.limite_proceso_s * 1000 <= self.espera_ms:
            raise ValueError(
                "El límite del proceso debe ser mayor "
                "que la espera de respuesta."
            )

@dataclass(frozen=True)
class ConfiguracionMemoria:
    """Límites de la memoria de observaciones de una sesión."""

    capacidad: int = 100
    retencion_s: int = 600

    def __post_init__(self):
        for nombre in ("capacidad", "retencion_s"):
            valor = getattr(self, nombre)
            if type(valor) is not int:
                raise TypeError(f"{nombre} debe ser un número entero.")
            if valor <= 0:
                raise ValueError(f"{nombre} debe ser mayor que cero.")


@dataclass(frozen=True)
class ConfiguracionBackend:
    """Configuración compartida; conserva los valores de la sonda existente."""

    sonda: ConfiguracionSonda = field(default_factory=ConfiguracionSonda)
    limite_contexto_s: int = 5
    nivel_log: str = "WARNING"
    memoria: ConfiguracionMemoria = field(default_factory=ConfiguracionMemoria)

    def __post_init__(self):
        if not isinstance(self.memoria, ConfiguracionMemoria):
            raise TypeError("memoria debe ser una ConfiguracionMemoria.")
        if not isinstance(self.sonda, ConfiguracionSonda):
            raise TypeError("sonda debe ser una ConfiguracionSonda.")
        if type(self.limite_contexto_s) is not int:
            raise TypeError("limite_contexto_s debe ser un número entero.")
        if self.limite_contexto_s <= 0:
            raise ValueError("limite_contexto_s debe ser mayor que cero.")
        if self.nivel_log not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("nivel_log debe ser DEBUG, INFO, WARNING, ERROR o CRITICAL.")


def _objeto_sin_duplicados(pares):
    """Evita que JSON reemplace silenciosamente una opción repetida."""
    objeto = {}
    for clave, valor in pares:
        if clave in objeto:
            raise ValueError(f"Campo de configuración repetido: {clave}.")
        objeto[clave] = valor
    return objeto


def _rechazar_constante(valor):
    raise ValueError("La configuración no admite NaN ni Infinity.")


def interpretar_configuracion(texto):
    """Valida JSON y sus opciones sin leer archivos ni consultar la red."""
    try:
        datos = json.loads(texto, object_pairs_hook=_objeto_sin_duplicados,
                           parse_constant=_rechazar_constante)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON de configuración inválido en línea {error.lineno}, columna {error.colno}.") from None
    if not isinstance(datos, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    desconocidos = datos.keys() - {"sonda", "limite_contexto_s", "nivel_log", "memoria"}
    if desconocidos:
        raise ValueError(f"Opciones desconocidas: {', '.join(sorted(desconocidos))}.")
    sonda = datos.get("sonda", {})
    if not isinstance(sonda, dict):
        raise ValueError("sonda debe ser un objeto JSON.")
    desconocidos = sonda.keys() - {"espera_ms", "limite_proceso_s"}
    if desconocidos:
        raise ValueError(f"Opciones de sonda desconocidas: {', '.join(sorted(desconocidos))}.")
    memoria = datos.get("memoria", {})
    if not isinstance(memoria, dict):
        raise ValueError("memoria debe ser un objeto JSON.")
    desconocidos = memoria.keys() - {"capacidad", "retencion_s"}
    if desconocidos:
        raise ValueError(f"Opciones de memoria desconocidas: {', '.join(sorted(desconocidos))}.")
    return ConfiguracionBackend(
        memoria=ConfiguracionMemoria(**memoria),
        sonda=ConfiguracionSonda(**sonda),
        limite_contexto_s=datos.get("limite_contexto_s", 5),
        nivel_log=datos.get("nivel_log", "WARNING"),
    )


def cargar_configuracion(ruta=None):
    """Lee un archivo UTF-8 explícito, o usa valores predeterminados."""
    if ruta is None:
        return ConfiguracionBackend()
    try:
        texto = Path(ruta).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ValueError("No se pudo leer el archivo de configuración como UTF-8.") from None
    return interpretar_configuracion(texto)
