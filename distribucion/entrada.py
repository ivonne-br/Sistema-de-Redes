"""Puerta de entrada de PyInstaller; recibe argumentos y devuelve el código de salida.

Delega en backend.paquete; no inicia servicios al importarse desde desarrollo.
"""
from backend.paquete import main

if __name__ == '__main__':
    raise SystemExit(main())
