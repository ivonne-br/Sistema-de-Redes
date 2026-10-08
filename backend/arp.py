# Interpretar línea de salida de arp (IPv4, MAC, interfaz)

import ipaddress
import re

def interpretar_linea_arp(linea):
    patron = (
        r"\?\s+\((?P<ipv4>[^)]+)\)\s+at\s+"
        r"(?P<mac>"
        r"[0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5}"
        r"|\(incomplete\))"
        r"\s+on\s+(?P<interfaz>\S+)\s+"
        r"(?P<marcas>(?:\w+\s+)*)"
        r"\[(?P<tipo_enlace>[^\]\s]+)\]"
    )

    coincidencia = re.fullmatch(patron, linea.strip())

    if coincidencia is None:
        raise ValueError(
            "La línea no corresponde al formato ARP esperado."
        )

    campos = coincidencia.groupdict()

    try:
        ipv4 = str(ipaddress.IPv4Address(campos["ipv4"])) # Valida que la dirección IPv4 sea correcta y la convierte a una cadena estándar
    except ipaddress.AddressValueError:
        raise ValueError(
            "La entrada ARP contiene una dirección IPv4 inválida."
        ) from None

    if campos["mac"] == "(incomplete)":
        mac = None
    else:
        componentes_mac = campos["mac"].lower().split(":")
        mac = ":".join(
            componente.zfill(2) for componente in componentes_mac
        )

    return {
        "ipv4": ipv4,
        "mac": mac,
        "interfaz": campos["interfaz"],
        "marcas": campos["marcas"].split(),
        "tipo_enlace": campos["tipo_enlace"],
    }
