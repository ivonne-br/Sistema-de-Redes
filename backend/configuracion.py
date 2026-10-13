"""Recibe JSON y valida sondas ICMP/DNS/HTTPS, memoria y tareas de red; entrega configuración al CLI, API y monitores independientes."""

from dataclasses import dataclass, field
import json
import math
import re
from urllib.parse import urlsplit
from ipaddress import IPv4Address
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
    intervalo_arp_s: float = 5.0
    vigencia_arp_s: int = 90
    ausencias_arp: int = 3
    puerto_api: int = 8000
    busqueda_activa: bool = True
    intervalo_busqueda_s: float = 60.0
    conectividad_activa: bool = True
    intervalo_conectividad_s: float = 30.0
    muestras_conectividad: int = 5
    destinos_externos: tuple = ("1.1.1.1",)

    web_activa: bool = True
    intervalo_web_s: float = 60.0
    limite_web_s: float = 8.0
    nombre_dns: str = "www.gstatic.com"
    url_https: str = "https://www.gstatic.com/generate_204"
    codigo_https_esperado: int = 204

    def __post_init__(self):
        if type(self.web_activa) is not bool:
            raise TypeError("web_activa debe ser un booleano.")
        for nombre, minimo, maximo in (("intervalo_web_s", 10, 86400), ("limite_web_s", 1, 30)):
            valor = getattr(self, nombre)
            if type(valor) not in (int, float) or not math.isfinite(valor) or not minimo <= valor <= maximo:
                raise ValueError(f"{nombre} debe estar entre {minimo} y {maximo} segundos.")
        if not isinstance(self.nombre_dns, str) or len(self.nombre_dns) > 253 or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", parte)
            for parte in self.nombre_dns.rstrip('.').split('.')
        ):
            raise ValueError("nombre_dns debe ser un nombre de host ASCII válido.")
        try:
            IPv4Address(self.nombre_dns)
        except ValueError:
            pass
        else:
            raise ValueError("nombre_dns debe ser un nombre, no una IPv4 literal.")
        if not isinstance(self.url_https, str) or any(ord(c) <= 32 or ord(c) >= 127 for c in self.url_https):
            raise ValueError("url_https debe ser una URL ASCII sin espacios ni controles.")
        url = urlsplit(self.url_https)
        if (url.scheme != 'https' or not url.hostname or url.username is not None
                or url.password is not None or url.fragment or url.port == 0):
            raise ValueError("url_https requiere HTTPS, host y puerto válido, sin credenciales ni fragmento.")
        if type(self.codigo_https_esperado) is not int or not 200 <= self.codigo_https_esperado <= 299:
            raise ValueError("codigo_https_esperado debe ser un código entre 200 y 299.")
        if type(self.conectividad_activa) is not bool:
            raise TypeError("conectividad_activa debe ser un booleano.")
        if type(self.intervalo_conectividad_s) not in (int, float):
            raise TypeError("intervalo_conectividad_s debe ser un número.")
        if not 1 <= self.intervalo_conectividad_s <= 86400 or not math.isfinite(self.intervalo_conectividad_s):
            raise ValueError("intervalo_conectividad_s debe estar entre 1 y 86400 segundos.")
        if type(self.muestras_conectividad) is not int or not 1 <= self.muestras_conectividad <= 20:
            raise ValueError("muestras_conectividad debe ser un entero entre 1 y 20.")
        if not isinstance(self.destinos_externos, tuple) or len(self.destinos_externos) > 3:
            raise ValueError("destinos_externos debe ser una tupla de hasta tres IPv4 públicas.")
        for destino in self.destinos_externos:
            if not isinstance(destino, str):
                raise ValueError("Cada destino externo debe ser una IPv4 pública escrita como texto.")
            direccion = IPv4Address(destino)
            if not direccion.is_global or direccion.is_multicast:
                raise ValueError("Los destinos externos deben ser IPv4 públicas unicast.")
        if len(set(self.destinos_externos)) != len(self.destinos_externos):
            raise ValueError("No se permiten destinos externos repetidos.")
        if type(self.busqueda_activa) is not bool:
            raise TypeError("busqueda_activa debe ser un booleano.")
        if type(self.intervalo_busqueda_s) not in (int, float):
            raise TypeError("intervalo_busqueda_s debe ser un número.")
        if not 0 < self.intervalo_busqueda_s <= 86400 or not math.isfinite(self.intervalo_busqueda_s):
            raise ValueError("intervalo_busqueda_s debe ser finito, positivo y como máximo 86400.")
        if type(self.puerto_api) is not int:
            raise TypeError("puerto_api debe ser un entero, sin booleanos.")
        if not 0 <= self.puerto_api <= 65535:
            raise ValueError("puerto_api debe estar entre 0 y 65535; 0 elige un puerto libre.")
        if type(self.ausencias_arp) is not int:
            raise TypeError("ausencias_arp debe ser un entero, sin booleanos.")
        if self.ausencias_arp <= 0:
            raise ValueError("ausencias_arp debe ser mayor que cero.")
        if type(self.vigencia_arp_s) is not int:
            raise TypeError("vigencia_arp_s debe ser un entero, sin booleanos.")
        if self.vigencia_arp_s <= 0:
            raise ValueError("vigencia_arp_s debe ser mayor que cero.")
        if type(self.intervalo_arp_s) not in (int, float):
            raise TypeError("intervalo_arp_s debe ser un número, sin booleanos.")
        if not 0 < self.intervalo_arp_s <= 86400 or not math.isfinite(self.intervalo_arp_s):
            raise ValueError("intervalo_arp_s debe ser finito, mayor que cero y como máximo 86400.")
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
    desconocidos = datos.keys() - {"sonda", "limite_contexto_s", "nivel_log", "memoria", "intervalo_arp_s", "vigencia_arp_s", "ausencias_arp", "puerto_api", "busqueda_activa", "intervalo_busqueda_s", "conectividad_activa", "intervalo_conectividad_s", "muestras_conectividad", "destinos_externos", "web_activa", "intervalo_web_s", "limite_web_s", "nombre_dns", "url_https", "codigo_https_esperado"}
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
    externos = datos.get("destinos_externos", ["1.1.1.1"])
    if not isinstance(externos, list):
        raise ValueError("destinos_externos debe ser una lista JSON.")
    return ConfiguracionBackend(
        web_activa=datos.get("web_activa", True),
        intervalo_web_s=datos.get("intervalo_web_s", 60.0),
        limite_web_s=datos.get("limite_web_s", 8.0),
        nombre_dns=datos.get("nombre_dns", "www.gstatic.com"),
        url_https=datos.get("url_https", "https://www.gstatic.com/generate_204"),
        codigo_https_esperado=datos.get("codigo_https_esperado", 204),
        conectividad_activa=datos.get("conectividad_activa", True),
        intervalo_conectividad_s=datos.get("intervalo_conectividad_s", 30.0),
        muestras_conectividad=datos.get("muestras_conectividad", 5),
        destinos_externos=tuple(externos),
        busqueda_activa=datos.get("busqueda_activa", True),
        intervalo_busqueda_s=datos.get("intervalo_busqueda_s", 60.0),
        puerto_api=datos.get("puerto_api", 8000),
        intervalo_arp_s=datos.get("intervalo_arp_s", 5.0),
        vigencia_arp_s=datos.get("vigencia_arp_s", 90),
        ausencias_arp=datos.get("ausencias_arp", 3),
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
