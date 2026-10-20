"""Lectura pasiva de ARP mediante sysctl, sin ejecutar el programa arp."""

import ctypes
import errno
import platform
import socket
import struct
from datetime import datetime, timezone

# ABI de Darwin: rt_msghdr (versión 5), direcciones alineadas a 4 bytes.
# Definiciones públicas del SDK: net/route.h, net/if_dl.h y sys/socket.h.
_MIB_ARP = (4, 17, 0, 2, 2, 0x400)
_CABECERA = 92
_MAX_BYTES = 16 * 1024 * 1024


def leer_cache_arp_sistema():
    """Devuelve bytes de sysctl; acota memoria y reintenta si crece la tabla."""
    if platform.system() != "Darwin":
        raise OSError("La lectura directa ARP requiere macOS.")
    biblioteca = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    llamada = biblioteca.sysctl
    llamada.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                        ctypes.c_void_p, ctypes.c_size_t]
    llamada.restype = ctypes.c_int
    mib = (ctypes.c_int * 6)(*_MIB_ARP)
    for _ in range(3):
        longitud = ctypes.c_size_t()
        if llamada(mib, 6, None, ctypes.byref(longitud), None, 0) != 0:
            raise OSError(ctypes.get_errno(), "No se pudo consultar el tamaño ARP.")
        capacidad = longitud.value
        if capacidad > _MAX_BYTES:
            raise OSError("La tabla ARP supera el límite de memoria permitido.")
        if capacidad == 0:
            return b""
        buffer = ctypes.create_string_buffer(capacidad)
        if llamada(mib, 6, buffer, ctypes.byref(longitud), None, 0) == 0:
            if longitud.value > capacidad:
                raise OSError("La lectura ARP informó un tamaño incompatible.")
            return buffer.raw[:longitud.value]
        codigo = ctypes.get_errno()
        if codigo != errno.ENOMEM:
            raise OSError(codigo, "No se pudo leer la tabla ARP.")
    raise OSError("La tabla ARP cambió de tamaño durante los tres intentos.")


def _interpretar_registro(registro, resolver_interfaz):
    """Valida una cabecera y sus direcciones antes de obtener IPv4 y MAC."""
    if len(registro) < _CABECERA or registro[2:4] != bytes((5, 4)):
        raise ValueError("Cabecera ARP no compatible con RTM_VERSION=5 y RTM_GET.")
    flags, mascara = struct.unpack_from("=II", registro, 8)
    if not flags & 0x400 or mascara & ~0xff:
        raise ValueError("Marcas o direcciones de la cabecera ARP no compatibles.")
    direcciones = {}
    cursor = _CABECERA
    for bit in range(8):
        if mascara & (1 << bit):
            if cursor + 2 > len(registro):
                raise ValueError("Dirección ARP truncada.")
            longitud = registro[cursor]
            paso = (longitud + 3) & ~3 if longitud else 4
            if longitud < 2 or cursor + paso > len(registro):
                raise ValueError("Longitud de dirección ARP inválida.")
            direcciones[bit] = registro[cursor:cursor + longitud]
            cursor += paso
    ipv4 = direcciones.get(0, b"")
    enlace = direcciones.get(1, b"")
    if len(ipv4) < 16 or ipv4[1] != 2 or len(enlace) < 8 or enlace[1] != 18:
        raise ValueError("Falta una dirección IPv4 o una dirección de enlace válida.")
    indice = struct.unpack_from("=H", enlace, 2)[0]
    n_nombre, n_mac = enlace[5:7]
    if n_mac not in (0, 6) or 8 + n_nombre + n_mac > len(enlace):
        raise ValueError("La longitud de la MAC no es compatible.")
    interfaz = resolver_interfaz(indice)
    if not isinstance(interfaz, str) or not interfaz:
        raise ValueError("No se pudo identificar la interfaz ARP.")
    marcas = []
    if flags & 0x1000000:
        marcas.append("ifscope")
    if struct.unpack_from("=I", registro, 48)[0] == 0:
        marcas.append("permanent")
    if struct.unpack_from("=H", ipv4, 14)[0] & 1:
        marcas.append("published")
    tipos = {6: "ethernet", 15: "fddi", 37: "atm", 135: "vlan", 144: "firewire", 209: "bridge"}
    return {
        "ipv4": socket.inet_ntoa(ipv4[4:8]),
        "mac": ":".join(f"{b:02x}" for b in enlace[8 + n_nombre:8 + n_nombre + n_mac]) if n_mac else None,
        "interfaz": interfaz,
        "marcas": marcas,
        "tipo_enlace": tipos.get(enlace[4], f"tipo_{enlace[4]}"),
    }


def interpretar_cache_arp_sistema(datos, *, resolver_interfaz=None):
    """Interpreta bytes sin consultar la red; conserva errores por registro."""
    if not isinstance(datos, bytes):
        raise TypeError("La caché ARP debe recibirse como bytes.")
    if resolver_interfaz is None:
        resolver_interfaz = socket.if_indextoname
    entradas, errores = [], []
    cursor, numero = 0, 0
    while cursor < len(datos):
        numero += 1
        if len(datos) - cursor < 4:
            errores.append({"numero_registro": numero, "detalle": "Cabecera ARP truncada."})
            break
        longitud = struct.unpack_from("=H", datos, cursor)[0]
        if longitud < _CABECERA or cursor + longitud > len(datos):
            errores.append({"numero_registro": numero, "detalle": "Longitud de registro ARP inválida."})
            break  # Sin un límite fiable no se intenta adivinar el siguiente registro.
        try:
            entrada = _interpretar_registro(datos[cursor:cursor + longitud], resolver_interfaz)
        except (ValueError, OSError) as error:
            errores.append({"numero_registro": numero, "detalle": str(error)})
        else:
            entradas.append(entrada)
        cursor += longitud
    return {"entradas": entradas, "errores": errores}


def consultar_arp_sistema():
    """Coordina captura y parseo, indicando fuente, intervalo y fallos explícitos."""
    resultado = {"fuente": "cache_arp_sysctl_macos",
                 "inicio_captura": datetime.now(timezone.utc).isoformat(),
                 "fin_captura": None, "estado": "error_recoleccion",
                 "bytes_recibidos": None, "entradas": [], "errores": [], "detalle": None}
    try:
        datos = leer_cache_arp_sistema()
    except OSError as error:
        resultado["detalle"] = str(error)
    else:
        resultado["fin_captura"] = datetime.now(timezone.utc).isoformat()
        resultado["bytes_recibidos"] = len(datos)
        resultado.update(interpretar_cache_arp_sistema(datos))
        if resultado["errores"]:
            resultado["estado"] = "lectura_parcial" if resultado["entradas"] else "error_interpretacion"
        else:
            resultado["estado"] = "lectura_correcta" if resultado["entradas"] else "sin_datos_visibles"
        if not datos:
            resultado["detalle"] = "macOS no devolvió entradas; no distingue caché vacía de visibilidad restringida."
    if resultado["fin_captura"] is None:
        resultado["fin_captura"] = datetime.now(timezone.utc).isoformat()
    return resultado
