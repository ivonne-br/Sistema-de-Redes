"""Reloj compartido para antigüedad y retención, incluyendo el reposo del equipo.

Sin entradas; entrega segundos monotónicos de origen arbitrario a los monitores
y a la memoria. No representa una fecha UTC ni persiste entre arranques.
"""

import sys
import time


def tiempo_continuo():
    """Lee tiempo transcurrido sin ajustes del calendario e incluyendo suspensión.

    En macOS MONOTONIC_RAW usa mach_continuous_time. En Linux esa misma
    constante no incluye suspensión: allí corresponde BOOTTIME. Si falta el
    reloj requerido se informa el error, sin sustituirlo por tiempo de calendario.
    """
    nombre = {'darwin': 'CLOCK_MONOTONIC_RAW', 'linux': 'CLOCK_BOOTTIME'}.get(sys.platform)
    identificador = getattr(time, nombre, None) if nombre else None
    if identificador is None:
        raise RuntimeError('No hay un reloj continuo compatible con este sistema.')
    return time.clock_gettime(identificador)
