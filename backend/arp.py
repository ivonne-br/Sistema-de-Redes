# Interpretar línea de salida de arp (IPv4, MAC, interfaz)

import ipaddress
import re
import os
import platform
import subprocess

from datetime import datetime, timezone

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

def interpretar_tabla_arp(texto):
    """Interpreta texto ARP y conserva los errores por línea."""
    entradas = []
    errores = []

    for numero_linea, linea in enumerate(texto.splitlines(), start=1):
        if not linea.strip():
            continue

        try:
            entrada = interpretar_linea_arp(linea)
        except ValueError as error:
            errores.append({
                "numero_linea": numero_linea,
                "detalle": str(error),
            })
        else:
            entradas.append(entrada)

    return {
        "entradas": entradas,
        "errores": errores,
    }

def leer_cache_arp(limite_proceso_s, *, diagnostico=False):
    """Lee la caché ARP en macOS sin interpretar su contenido."""
    if type(diagnostico) is not bool:
        raise TypeError("diagnostico debe ser booleano.")
    if type(limite_proceso_s) is not int:
        raise TypeError("limite_proceso_s debe ser un número entero.")

    if limite_proceso_s <= 0:
        raise ValueError("limite_proceso_s debe ser mayor que cero.")

    resultado = {
        "estado": "error_recoleccion",
        "texto": None,
        "detalle": None,
    }

    if diagnostico:
        resultado["diagnostico"] = {
            "comando": ["/usr/sbin/arp", "-an"],
            "limite_proceso_s": limite_proceso_s,
            "etapa": "antes_ejecucion",
            "ejecucion_completada": False,
            "codigo_salida": None,
            "tipo_stdout": None,
            "stdout_caracteres": None,
            "stdout_lineas": None,
            "stderr_caracteres": None,
            "interpretacion_ejecutada": False,
            "entradas": None,
            "errores": None,
            "excepcion": None,
        }

    def registrar_etapa(**datos):
        if diagnostico:
            resultado["diagnostico"].update(datos)

    if platform.system() != "Darwin":
        registrar_etapa(etapa="plataforma_no_compatible")
        resultado["detalle"] = "La lectura ARP requiere macOS."
        return resultado

    try:
        proceso = subprocess.run(
            ["/usr/sbin/arp", "-an"],
            capture_output=True,
            text=True,
            timeout=limite_proceso_s,
            env={**os.environ, "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired:
        registrar_etapa(etapa="ejecucion", excepcion="TimeoutExpired")
        resultado["detalle"] = "La lectura ARP excedió el límite de ejecución."
        return resultado
    except OSError as error:
        registrar_etapa(etapa="ejecucion", excepcion=type(error).__name__)
        resultado["detalle"] = "No se pudo ejecutar arp."
        return resultado
    except UnicodeError as error:
        registrar_etapa(etapa="decodificacion", excepcion=type(error).__name__)
        resultado["detalle"] = "No se pudo convertir la salida ARP a texto."
        return resultado

    registrar_etapa(
        etapa="captura", ejecucion_completada=True, codigo_salida=proceso.returncode,
        tipo_stdout=type(proceso.stdout).__name__,
    )
    if not isinstance(proceso.stdout, str) or not isinstance(proceso.stderr, str):
        registrar_etapa(etapa="tipo_salida")
        resultado["detalle"] = "La salida del proceso ARP no es texto."
        return resultado
    registrar_etapa(
        stdout_caracteres=len(proceso.stdout), stdout_lineas=len(proceso.stdout.splitlines()),
        stderr_caracteres=len(proceso.stderr),
    )
    if proceso.returncode != 0 or proceso.stderr.strip():
        registrar_etapa(etapa="error_comando")
        resultado["detalle"] = (
            f"Arp informó un error; código de salida: {proceso.returncode}."
        )
        return resultado

    resultado["estado"] = "lectura_correcta"
    resultado["texto"] = proceso.stdout
    return resultado

def consultar_arp(limite_proceso_s, *, diagnostico=False):
    """Lee e interpreta la caché ARP, conservando fallos y resultados."""
    if type(diagnostico) is not bool:
        raise TypeError("diagnostico debe ser booleano.")
    resultado = {
        "fuente": "cache_arp_macos",
        "inicio": datetime.now(timezone.utc).isoformat(),
        "estado": "error_recoleccion",
        "entradas": [],
        "errores": [],
        "detalle": None,
    }

    lectura = (leer_cache_arp(limite_proceso_s, diagnostico=True)
               if diagnostico else leer_cache_arp(limite_proceso_s))
    if diagnostico:
        resultado["diagnostico"] = dict(lectura["diagnostico"])

    if lectura["estado"] == "error_recoleccion":
        resultado["detalle"] = lectura["detalle"]
        return resultado

    tabla = interpretar_tabla_arp(lectura["texto"])
    resultado["entradas"] = tabla["entradas"]
    resultado["errores"] = tabla["errores"]
    if diagnostico:
        resultado["diagnostico"].update(
            etapa="interpretacion", interpretacion_ejecutada=True,
            entradas=len(tabla["entradas"]), errores=len(tabla["errores"]),
        )

    if not tabla["entradas"] and not tabla["errores"]:
        resultado["estado"] = "lectura_sin_entradas"
        resultado["detalle"] = (
            "La consulta no devolvió entradas. No se puede determinar "
            "con esta lectura si la caché está vacía o si su visibilidad "
            "está limitada."
        )
    elif not tabla["errores"]:
        resultado["estado"] = "lectura_correcta"
    elif tabla["entradas"]:
        resultado["estado"] = "lectura_parcial"
        resultado["detalle"] = "Algunas líneas no pudieron interpretarse."
    else:
        resultado["estado"] = "error_interpretacion"
        resultado["detalle"] = "Ninguna línea no vacía pudo interpretarse."

    return resultado

def diagnosticar_arp(limite_proceso_s=5, *, texto_referencia=None):
    """Resume puntos de control sin exponer IP, MAC ni texto ARP recibido."""
    if texto_referencia is not None and not isinstance(texto_referencia, str):
        raise TypeError("texto_referencia debe ser texto o None.")
    consulta = consultar_arp(limite_proceso_s, diagnostico=True)
    referencia = None
    if texto_referencia is not None:
        tabla = interpretar_tabla_arp(texto_referencia)
        referencia = {
            "fuente": "texto_arp_stdin", "caracteres": len(texto_referencia),
            "lineas": len(texto_referencia.splitlines()),
            "entradas": len(tabla["entradas"]), "errores": len(tabla["errores"]),
        }
    estado_lectura = consulta["estado"]
    if estado_lectura == "error_recoleccion":
        estado, conclusion = "error_recoleccion", "fallo_de_ejecucion_o_captura"
    elif estado_lectura == "lectura_sin_entradas":
        estado = "diagnostico_sin_datos"
        if referencia is not None and referencia["entradas"]:
            conclusion = "python_sin_datos_con_referencia_interpretable"
        else:
            conclusion = "python_sin_datos_sin_referencia_interpretable"
    elif estado_lectura in ("error_interpretacion", "lectura_parcial"):
        estado, conclusion = "diagnostico_con_errores", "texto_recibido_con_errores_de_interpretacion"
    else:
        estado, conclusion = "diagnostico_con_datos", "texto_recibido_e_interpretado"
    return {
        "fuente": "diagnostico_arp_macos", "inicio": consulta["inicio"],
        "fin": datetime.now(timezone.utc).isoformat(), "estado": estado,
        "estado_lectura": estado_lectura, "detalle": consulta["detalle"],
        "diagnostico": consulta["diagnostico"], "referencia": referencia,
        "conclusion": conclusion,
    }


def crear_contexto_arp(interfaz, ipv4_local, gateway=None):
    """Valida el contexto IPv4 explícito; no consulta el sistema.""" # validar interfaz
    if not isinstance(interfaz, str) or not interfaz.strip() or any(
        caracter.isspace() for caracter in interfaz
    ):
        raise ValueError("La interfaz debe ser un nombre sin espacios.")
    if "/" not in ipv4_local:
        raise ValueError("La IPv4 local debe incluir máscara o prefijo, por ejemplo 192.0.2.10/24.")
    local = ipaddress.IPv4Interface(ipv4_local)
    red = local.network

    def es_host(direccion):
        return (
            direccion in red
            and not direccion.is_multicast
            and not direccion.is_unspecified
            and direccion != ipaddress.IPv4Address("255.255.255.255")
            and (red.prefixlen >= 31 or direccion not in (red.network_address, red.broadcast_address))
        )

    if not es_host(local.ip):
        raise ValueError("La IPv4 local debe ser una dirección de host de la subred.")
    puerta = ipaddress.IPv4Address(gateway) if gateway is not None else None
    if puerta is not None and (not es_host(puerta) or puerta == local.ip):
        raise ValueError("El gateway debe ser otro host de la misma subred.")
    return {
        "interfaz": interfaz,
        "ipv4_local": str(local),
        "subred": str(red),
        "gateway": str(puerta) if puerta is not None else None,
    }

def clasificar_entradas_arp(entradas, interfaz, ipv4_local, gateway=None):
    """Clasifica entradas interpretadas sin modificarlas ni confirmar presencia."""
    contexto = crear_contexto_arp(interfaz, ipv4_local, gateway)
    local = ipaddress.IPv4Interface(contexto["ipv4_local"])
    red = local.network
    clasificadas = []
    for entrada in entradas:
        direccion = ipaddress.IPv4Address(entrada["ipv4"])
        if entrada["interfaz"] != interfaz:
            categoria, motivo = "otra_interfaz", "La entrada pertenece a otra interfaz."
        elif direccion == local.ip:
            categoria, motivo = "equipo_propio", "Coincide con la IPv4 local indicada."
        elif entrada["ipv4"] == contexto["gateway"]:
            categoria, motivo = "gateway", "Coincide con la puerta de enlace indicada."
        elif direccion.is_multicast:
            categoria, motivo = "multicast", "La IPv4 identifica un grupo multicast."
        elif direccion == ipaddress.IPv4Address("255.255.255.255") or (
            red.prefixlen < 31 and direccion == red.broadcast_address
        ):
            categoria, motivo = "broadcast", "Es una dirección de difusión."
        elif red.prefixlen < 31 and direccion == red.network_address:
            categoria, motivo = "direccion_red", "Identifica la subred, no un host."
        elif direccion not in red:
            categoria, motivo = "fuera_subred", "La IPv4 no pertenece a la subred indicada."
        else:
            categoria, motivo = "vecino", "Es otra IPv4 de host de la subred; su presencia actual no está confirmada."
        clasificadas.append({
            **entrada,
            "categoria": categoria,
            "motivo": motivo,
            "resolucion_mac": "incompleta" if entrada["mac"] is None else "resuelta",
        })
    return clasificadas
