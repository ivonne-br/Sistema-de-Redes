"""Cabeceras comunes para conservar la identidad HTTP durante la sesión."""
import time
from urllib.parse import urlencode


def consulta_router(csrf):
    """Reproduce el orden y la marca de tiempo en milisegundos del panel."""
    return urlencode({'_': time.time_ns() // 1_000_000, 'csrf_token': csrf})


def cabeceras_router():
    # Se devuelve una copia: las cookies se añaden por petición, nunca aquí.
    return {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'es-MX,es;q=0.9'}
