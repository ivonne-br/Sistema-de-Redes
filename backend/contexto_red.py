"""Contexto IPv4 actual de macOS: lectura local, interpretación y coordinación."""

import ipaddress
import os
import platform
import re
import subprocess
from datetime import datetime, timezone

from backend.arp import crear_contexto_arp


class ErrorContexto(ValueError):
    """Fallo esperado con un estado que puede comunicar el CLI."""

    def __init__(self, estado, detalle):
        super().__init__(detalle)
        self.estado = estado


def leer_comando_contexto(comando, limite_proceso_s):
    """Ejecuta una consulta local acotada; conserva texto, error y código."""
    try:
        proceso = subprocess.run(
            comando, capture_output=True, text=True, timeout=limite_proceso_s,
            env={**os.environ, "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired:
        raise ErrorContexto("error_recoleccion", "La consulta de contexto excedió el límite de ejecución.") from None
    except (OSError, UnicodeError):
        raise ErrorContexto("error_recoleccion", "No se pudo ejecutar o leer la consulta de contexto.") from None
    return {"texto": proceso.stdout, "error": proceso.stderr, "codigo": proceso.returncode}


def interpretar_ruta_ipv4(lectura):
    """Interpreta route sin ejecutar comandos; distingue ruta ausente de fallo."""
    if lectura["codigo"] != 0:
        if lectura["error"].strip() == "route: writing to routing socket: not in table":
            raise ErrorContexto("sin_ruta", "No existe una ruta IPv4 predeterminada visible.")
        raise ErrorContexto("error_recoleccion", "No se pudo consultar la ruta IPv4 predeterminada.")
    if lectura["error"].strip():
        raise ErrorContexto("error_recoleccion", "La consulta de ruta informó un error.")
    campos = {}
    for linea in lectura["texto"].splitlines():
        clave, separador, valor = linea.strip().partition(":")
        if separador and clave in {"destination", "interface", "gateway", "flags"}:
            if clave in campos:
                raise ErrorContexto("error_interpretacion", "La ruta contiene campos repetidos.")
            campos[clave] = valor.strip()
    interfaz = campos.get("interface", "")
    if (campos.get("destination") != "default"
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", interfaz) is None
            or re.fullmatch(r"<[^<>]+>", campos.get("flags", "")) is None):
        raise ErrorContexto("error_interpretacion", "No se reconoce una ruta IPv4 predeterminada con interfaz y flags.")
    gateway = campos.get("gateway")
    if "GATEWAY" in campos["flags"][1:-1].split(","):
        try:
            gateway = str(ipaddress.IPv4Address(gateway))
        except (ValueError, TypeError):
            raise ErrorContexto("error_interpretacion", "La ruta no contiene un gateway IPv4 interpretable.") from None
    else:
        # Una ruta directa no declara un router IPv4 (puede mostrar link#N).
        gateway = None
    return {"interfaz": interfaz, "gateway": gateway}


def interpretar_ipv4_interfaz(texto, interfaz):
    """Extrae una IPv4 y máscara contigua de ifconfig, sin elegir entre alias."""
    lineas = texto.splitlines()
    if not lineas or not lineas[0].startswith(interfaz + ": flags="):
        raise ErrorContexto("error_interpretacion", "No se reconoce la salida de la interfaz seleccionada.")
    if any(linea and not linea[0].isspace() for linea in lineas[1:]):
        raise ErrorContexto("error_interpretacion", "La salida contiene más de una interfaz o texto inesperado.")
    direcciones = []
    for linea in lineas[1:]:
        partes = linea.split()
        if not partes or partes[0] != "inet":
            continue
        try:
            if len(partes) < 4 or partes[2] != "netmask":
                raise ValueError
            direccion = ipaddress.IPv4Address(partes[1])
            mascara = partes[3]
            if mascara.startswith("0x"):
                if re.fullmatch(r"0x[0-9a-fA-F]{8}", mascara) is None:
                    raise ValueError
                mascara = str(ipaddress.IPv4Address(int(mascara, 16)))
            mascara = ipaddress.IPv4Address(mascara)
            bits = f"{int(mascara):032b}"
            if "01" in bits:
                raise ValueError
            direcciones.append(f"{direccion}/{bits.count('1')}")
        except ValueError:
            raise ErrorContexto("error_interpretacion", "IPv4 o máscara de interfaz no interpretable o no contigua.") from None
    if not direcciones:
        raise ErrorContexto("sin_ipv4", "La interfaz de la ruta no tiene una dirección IPv4.")
    if len(direcciones) != 1:
        raise ErrorContexto("error_interpretacion", "La interfaz tiene varias IPv4; utiliza un contexto manual explícito.")
    return direcciones[0]


def consultar_contexto_ipv4(limite_proceso_s=5):
    """Coordina dos lecturas actuales y valida el contexto con las reglas ARP."""
    if type(limite_proceso_s) is not int:
        raise TypeError("limite_proceso_s debe ser un número entero.")
    if limite_proceso_s <= 0:
        raise ValueError("limite_proceso_s debe ser mayor que cero.")
    resultado = {
        "fuente": "contexto_ipv4_macos", "inicio": datetime.now(timezone.utc).isoformat(),
        "fin": None, "estado": "error_recoleccion", "contexto": None, "detalle": None,
    }
    try:
        if platform.system() != "Darwin":
            raise ErrorContexto("error_recoleccion", "La consulta de contexto requiere macOS.")
        ruta = interpretar_ruta_ipv4(leer_comando_contexto(
            ["/sbin/route", "-n", "get", "-inet", "default"], limite_proceso_s,
        ))
        lectura = leer_comando_contexto(["/sbin/ifconfig", ruta["interfaz"]], limite_proceso_s)
        if lectura["codigo"] != 0 or lectura["error"].strip():
            raise ErrorContexto("error_recoleccion", "No se pudo consultar la interfaz de la ruta.")
        ipv4 = interpretar_ipv4_interfaz(lectura["texto"], ruta["interfaz"])
        try:
            contexto = crear_contexto_arp(ruta["interfaz"], ipv4, ruta["gateway"])
        except ValueError as error:
            raise ErrorContexto("error_interpretacion", f"Contexto incompatible con la clasificación ARP: {error}") from None
        contexto["mascara"] = str(ipaddress.IPv4Interface(ipv4).netmask)
        resultado.update(estado="contexto_correcto", contexto=contexto)
    except ErrorContexto as error:
        resultado.update(estado=error.estado, detalle=str(error))
    resultado["fin"] = datetime.now(timezone.utc).isoformat()
    return resultado
