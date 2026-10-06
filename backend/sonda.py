# Función para ejecutar una sonda ICMP: recibe una dirección IPv4 y devuelve un diccionario con el resultado de la sonda.
# macOS es el único sistema operativo soportado en esta primera versión.

import ipaddress 
import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from backend.configuracion import ConfiguracionSonda

def ejecutar_sonda(destino, configuracion=None):
    """Ejecuta una solicitud ICMP hacia una dirección IPv4 en macOS."""
    if configuracion is None:
        configuracion = ConfiguracionSonda()

    direccion = str(ipaddress.IPv4Address(destino))
    # Diccionario para observar el resultado de la sonda
    resultado = {
        "destino": direccion,
        "inicio": datetime.now(timezone.utc).isoformat(),
        "metodo": "icmp_ping_macos",
        "espera_ms": configuracion.espera_ms,
        "estado": "error_recoleccion",
        "rtt_ms": None,
        "detalle": None,
    }

    if platform.system() != "Darwin":
        resultado["detalle"] = "Esta primera versión requiere macOS para ejecutar la sonda ICMP."
        return resultado

    comando = [
        "/sbin/ping",
        "-n",
        "-c", "1", # Envía un solo paquete ICMP
        "-W", str(configuracion.espera_ms),
        direccion,
    ]

    try:
        proceso = subprocess.run( # Ejecuta el comando ping y captura la salida
            comando,
            capture_output=True,
            text=True,
            timeout=configuracion.limite_proceso_s,
            env={**os.environ, "LC_ALL": "C"}, # asegura que la salida esté en inglés para facilitar el análisis de la salida
        )
    except subprocess.TimeoutExpired:
        resultado["detalle"] = "El proceso excedió el límite de ejecución."
        return resultado
    except OSError:
        resultado["detalle"] = "No se pudo ejecutar ping."
        return resultado

    if proceso.returncode == 2 and not proceso.stderr.strip():
        resultado["estado"] = "sin_respuesta"
        resultado["detalle"] = "Ping terminó sin recibir respuesta."
        return resultado

    if proceso.returncode != 0 or proceso.stderr.strip():
        resultado["detalle"] = (
            f"Ping informó un error; código de salida: {proceso.returncode}."
        )
        return resultado

    patron = (
        rf"^\d+ bytes from {re.escape(direccion)}: "
        rf"icmp_seq=0 .*time=(\d+(?:\.\d+)?) ms"
    )
    coincidencia = re.search(patron, proceso.stdout, re.MULTILINE) # Busca el RTT en la salida del comando ping usando una expresión regular

    if coincidencia is None:
        resultado["detalle"] = "La salida no contiene un RTT interpretable."
        return resultado

    rtt = float(coincidencia.group(1))

    if rtt > resultado["espera_ms"]:
        resultado["estado"] = "sin_respuesta"
        resultado["detalle"] = "Se recibió una respuesta fuera del plazo."
        return resultado

    resultado["estado"] = "respuesta_valida"
    resultado["rtt_ms"] = rtt
    return resultado