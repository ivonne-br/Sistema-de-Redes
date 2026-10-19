"""Entrada de la aplicación instalada, sin herramientas de desarrollo.

Recibe opciones de diagnóstico o doble clic; entrega dashboard o aviso nativo.
Configura certificados públicos y delega el ciclo de vida en backend.inicio.
"""

import argparse
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys

from backend.entorno_aplicacion import empaquetada, raiz_recursos


def preparar_tls():
    """Incluye raíces públicas sin desactivar validación TLS ni depender de Homebrew."""
    if empaquetada():
        import certifi
        ruta = Path(certifi.where())
        if not ruta.is_file():
            raise OSError('Faltan certificados públicos. Vuelve a instalar la aplicación completa.')
        os.environ['SSL_CERT_FILE'] = str(ruta)
    contexto = ssl.create_default_context()
    if not contexto.get_ca_certs():
        raise OSError('No se encontraron certificados públicos para comprobar HTTPS.')


def mostrar_error(mensaje):
    """Aviso sin secretos; no guarda registros ni pide privilegios administrativos."""
    print(mensaje, file=sys.stderr, flush=True)
    try:
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/osascript', '-e',
                            'on run argv\ndisplay dialog (item 1 of argv) with title "Sistema de Redes" '
                            'buttons {"Aceptar"} default button "Aceptar"\nend run', mensaje],
                           timeout=120, check=False, capture_output=True)
        elif sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, mensaje, 'Sistema de Redes', 0x10)
        else:
            subprocess.run(['zenity', '--error', '--title=Sistema de Redes', '--text=' + mensaje],
                           timeout=120, check=False, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def main():
    """El modo de verificación no consulta routers ni abre el navegador."""
    parser = argparse.ArgumentParser(description='Sistema de Redes instalado')
    parser.add_argument('--autoprueba', action='store_true')
    parser.add_argument('--servicio', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--resultado', type=Path, help='JSON de autoprueba, sin información de la red.')
    parser.add_argument('--trabajador-web', nargs=4, metavar=('TIPO', 'DESTINO', 'LIMITE', 'CODIGO'))
    opciones = parser.parse_args()
    try:
        preparar_tls()
        if opciones.trabajador_web:
            from backend.web import comprobar
            tipo, destino, limite, codigo = opciones.trabajador_web
            print(json.dumps(comprobar(tipo, destino, float(limite), int(codigo))))
            return 0
        if opciones.autoprueba:
            from backend.verificar_paquete import verificar
            resultado = verificar()
            texto = json.dumps(resultado, ensure_ascii=False, indent=2)
            if opciones.resultado:
                opciones.resultado.write_text(texto, encoding='utf-8')
            print(texto, flush=True)
            return 0
        from backend.inicio import ErrorInicio, ejecutar, preparar_dashboard
        preparar_dashboard(raiz_recursos())
        if sys.platform != 'darwin':
            raise ErrorInicio('Paquete experimental: falta adaptar y verificar la recolección de red '
                              'en este sistema operativo. Todavía no es una versión para uso cotidiano.')
        if empaquetada() and not opciones.servicio:
            # Finder puede invocar de nuevo el icono porque este proceso termina.
            # El hijo conserva el servicio hasta el cierre confirmado del dashboard.
            subprocess.Popen([sys.executable, '--servicio'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True,
                             env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1'))
            return 0
        ejecutar(consola=False)
    except Exception as error:
        # No incluir tracebacks, rutas personales o datos de las consultas en avisos.
        from backend.inicio import ErrorInicio
        mensaje = str(error) if isinstance(error, ErrorInicio) else (
            'No se pudo iniciar o verificar la aplicación. Comprueba que la copia esté completa '
            'y que tu carpeta de usuario permita escritura. No se cambió la configuración de red.')
        if opciones.autoprueba or opciones.trabajador_web:
            resultado = {'correcto': False, 'detalle': mensaje}
            if opciones.resultado:
                opciones.resultado.write_text(json.dumps(resultado, ensure_ascii=False), encoding='utf-8')
            print(json.dumps(resultado, ensure_ascii=False), flush=True)
        else:
            mostrar_error(mensaje)
        return 1
    return 0
