"""Rutas y exclusión de inicio comunes al repositorio y al paquete.

Entradas: entorno del sistema y ubicación del ejecutable. Salidas: recursos de
solo lectura, carpeta privada escribible y bloqueo; lo consume backend.inicio.
"""

import os
from pathlib import Path
import sys
import tempfile


def empaquetada():
    return bool(getattr(sys, 'frozen', False))


def raiz_recursos():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def carpeta_estado():
    """Solo coordinación de procesos; nunca guarda mediciones ni credenciales."""
    if sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    elif sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    carpeta = base / 'Sistema de Redes'
    carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
    if carpeta.is_symlink():
        raise OSError('La carpeta de la aplicación no puede ser un enlace.')
    return carpeta


def archivo_bloqueo(identificador):
    if empaquetada():
        return carpeta_estado() / 'inicio.lock'
    usuario = getattr(os, 'getuid', lambda: 'usuario')()
    return Path(tempfile.gettempdir()) / f'redes-inicio-{usuario}-{identificador}.lock'


def bloquear(archivo):
    """Bloqueo no bloqueante liberado por el sistema al cerrar el descriptor."""
    if sys.platform == 'win32':
        import msvcrt
        archivo.seek(0)
        try:
            msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno not in (13, 11, 36):
                raise
            raise BlockingIOError() from error
    else:
        import fcntl
        fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)


def comando_web(tipo, destino, limite, codigo):
    """El auxiliar empaquetado ejecuta una sonda, nunca otro dashboard."""
    prefijo = [sys.executable, '--trabajador-web'] if empaquetada() else [
        sys.executable, '-B', '-m', 'backend.web']
    return prefijo + [tipo, destino, str(limite), str(codigo)]
