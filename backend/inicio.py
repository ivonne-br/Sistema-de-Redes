"""Inicio local: recibe recursos del repositorio o paquete y abre Vue vía APILocal.

Comprueba archivos, compila Vue cuando cambia y reutiliza la API identificada.
Posee solo el servidor que crea; el botón de Vue, Enter o señales solicitan su cierre.
No mide Internet ni solicita permisos del router.
"""

import hashlib
from http.client import HTTPConnection, HTTPException
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
from threading import Event, Thread
import time
import webbrowser

from backend.entorno_aplicacion import (empaquetada, raiz_recursos, archivo_bloqueo, bloquear)

RAIZ = raiz_recursos()
APLICACION = 'sistema-de-redes'


class ErrorInicio(Exception):
    """Problema de inicio con explicación dirigida a la persona."""


def identidad(raiz=RAIZ):
    """Identifica esta instalación sin publicar su ruta personal."""
    if empaquetada():
        return hashlib.sha256(b'sistema-de-redes-paquete-v1').hexdigest()
    return hashlib.sha256(str(raiz.resolve()).encode()).hexdigest()


def consultar_inicio(puerto=8000, raiz=RAIZ):
    """Consulta únicamente loopback; None significa conexión rechazada, no sin Internet."""
    conexion = HTTPConnection('127.0.0.1', puerto, timeout=1)
    try:
        conexion.request('GET', '/api/v1/inicio')
        respuesta = conexion.getresponse()
        datos = json.loads(respuesta.read(8193))
        if (respuesta.status != 200 or not isinstance(datos, dict)
                or datos.get('aplicacion') != APLICACION or datos.get('version_inicio') != 1
                or datos.get('instalacion') != identidad(raiz)
                or not isinstance(datos.get('monitoreo'), dict)
                or type(datos.get('dashboard')) is not bool):
            raise ValueError()
        return datos
    except ConnectionRefusedError:
        return None
    except (OSError, HTTPException, ValueError, RecursionError) as error:
        raise ErrorInicio(f'El puerto local {puerto} está ocupado o no responde como esta aplicación. '
                          'Revisa la ventana del servicio que ya está abierto. Si es una versión anterior, '
                          'ciérrala tú cuando termines y vuelve a abrir la aplicación. '
                          'No se detuvo ningún servicio ajeno. Esto no indica una caída de Internet.') from error
    finally:
        conexion.close()


def comprobar_lista(datos):
    """Rechaza API detenida o dashboard ausente, aunque HTTP responda."""
    if not datos.get('dashboard'):
        raise ErrorInicio('La API está abierta, pero le falta el dashboard preparado. '
                          'Cierra su ventana cuando termines y vuelve a abrir la aplicación.')
    if datos.get('monitoreo', {}).get('estado') != 'activo':
        raise ErrorInicio('El servicio local responde, pero su recolección se detuvo. '
                          'Revisa su ventana y vuelve a abrir la aplicación después de cerrarlo. '
                          'Esto no demuestra que Internet haya fallado.')


class _Recursos(HTMLParser):
    """Obtiene los archivos locales que necesita el HTML compilado de Vue."""
    def __init__(self):
        super().__init__()
        self.rutas = []

    def handle_starttag(self, tag, attrs):
        valores = dict(attrs)
        ruta = valores.get('src') if tag == 'script' else valores.get('href') if tag == 'link' else None
        if ruta:
            self.rutas.append(ruta)


def dashboard_valido(directorio):
    """Comprueba HTML y recursos dentro de dist, sin exponer fuentes ni enlaces externos."""
    try:
        directorio = Path(directorio).resolve()
        parser = _Recursos()
        parser.feed((directorio / 'index.html').read_text(encoding='utf-8'))
        return bool(parser.rutas) and all(
            ruta.startswith('/') and (directorio / ruta.lstrip('/')).resolve().is_relative_to(directorio)
            and (directorio / ruta.lstrip('/')).is_file() for ruta in parser.rutas)
    except (OSError, UnicodeError):
        return False


def preparar_dashboard(raiz=RAIZ):
    """Valida el paquete; en desarrollo recompila fuentes cambiadas sin descargar."""
    if empaquetada():
        dist = raiz / 'frontend/dist'
        if not dashboard_valido(dist):
            raise ErrorInicio('La aplicación está incompleta: faltan archivos de la pantalla. '
                              'Vuelve a instalar una copia completa. No se inició la recolección.')
        return dist
    frontend = raiz / 'frontend'
    archivos = [frontend / nombre for nombre in ('package.json', 'package-lock.json', 'index.html', 'vite.config.js')]
    archivos += sorted(p for carpeta in ('src', 'public') for p in (frontend / carpeta).rglob('*') if p.is_file())
    try:
        huella = hashlib.sha256(b''.join(str(p.relative_to(frontend)).encode() + p.read_bytes() for p in archivos)).hexdigest()
    except OSError:
        raise ErrorInicio('Faltan archivos del dashboard. Recupera la carpeta completa del proyecto y vuelve a abrirlo.') from None
    dist = frontend / 'dist'
    sello = dist / '.inicio-huella'
    try:
        huella_anterior = sello.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        huella_anterior = None
    if dashboard_valido(dist) and huella_anterior == huella:
        return dist
    npm = shutil.which('npm')
    if npm is None:
        candidatos = [Path('/opt/homebrew/bin/npm'), Path('/usr/local/bin/npm')]
        candidatos += sorted((Path.home() / '.nvm/versions/node').glob('*/bin/npm'), reverse=True)
        npm = next((str(p) for p in candidatos if p.is_file()), None)
    if not npm or not (frontend / 'node_modules/vite/bin/vite.js').is_file():
        raise ErrorInicio('Falta preparar las herramientas del dashboard. Pide a quien prepara la instalación '
                          'que instale Node compatible con frontend/package.json y ejecute npm --prefix frontend ci. '
                          'Después vuelve a abrir este archivo. No se descargó nada automáticamente.')
    print('Preparando la pantalla; la primera apertura puede tardar unos segundos.', flush=True)
    entorno = dict(os.environ, PATH=str(Path(npm).parent) + os.pathsep + os.environ.get('PATH', ''))
    try:
        resultado = subprocess.run([npm, '--prefix', str(frontend), 'run', 'build'], env=entorno,
                                   cwd=raiz, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise ErrorInicio('No se pudo preparar la pantalla a tiempo. Revisa la instalación de Node y vuelve a intentarlo.') from None
    if resultado.returncode or not dashboard_valido(dist):
        raise ErrorInicio('No se pudo preparar el dashboard. Pide revisar las dependencias y ejecutar '
                          'npm --prefix frontend run build para ver el detalle técnico. No se inició la recolección.')
    sello.write_text(huella)
    return dist


def abrir_dashboard(puerto):
    """Abre solo la URL local verificada; ofrece la dirección si macOS no abre el navegador."""
    url = f'http://127.0.0.1:{puerto}/'
    print(f'Aplicación lista: {url}\nEsto no confirma acceso a Internet; consulta el dashboard.', flush=True)
    try:
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/open', url], check=True, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif not webbrowser.open(url):
            raise OSError('Navegador no disponible')
    except (OSError, subprocess.SubprocessError):
        print(f'No se pudo abrir el navegador. Abre esta dirección: {url}', flush=True)
        if empaquetada():
            from backend.paquete import mostrar_error
            mostrar_error(f'La aplicación está iniciada. Abre en tu navegador: {url}')


def ejecutar(raiz=RAIZ, puerto=8000, *, crear_api=None, abrir=abrir_dashboard, esperar_cierre=None,
             consola=True):
    """Serializa aperturas, reutiliza instancias y mantiene la propiedad del servidor creado."""
    from backend.api import APILocal
    from backend.configuracion import ConfiguracionBackend
    from backend.router import MonitoreoRouter

    parada = Event()
    anteriores = {}
    app = None
    hilo = None
    errores = []
    bloqueo = archivo_bloqueo(identidad(raiz))
    descriptor = os.open(bloqueo, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'r+b') as archivo:
        try:
            for senal in (signal.SIGINT, signal.SIGTERM, *([signal.SIGHUP] if hasattr(signal, 'SIGHUP') else [])):
                anteriores[senal] = signal.signal(senal, lambda *_: parada.set())
            limite = time.monotonic() + 140
            while True:
                if parada.is_set():
                    return
                try:
                    bloquear(archivo)
                    break
                except BlockingIOError:
                    datos = consultar_inicio(puerto, raiz)
                    if datos:
                        comprobar_lista(datos)
                        abrir(puerto)
                        print('Se reutilizó la aplicación abierta. Puedes usar «Cerrar aplicación» si aparece en la pantalla.', flush=True)
                        return
                    if time.monotonic() >= limite:
                        raise ErrorInicio('Otra ventana sigue preparando la aplicación. Revisa esa ventana antes de reintentar.')
                    parada.wait(.2)
            datos = consultar_inicio(puerto, raiz) if puerto else None
            if datos:
                comprobar_lista(datos)
                abrir(puerto)
                print('Servicio existente reutilizado; su cierre corresponde a la ventana que lo inició.', flush=True)
                return
            dist = preparar_dashboard(raiz)
            if parada.is_set():
                return
            config = ConfiguracionBackend(puerto_api=puerto)
            app = (crear_api(config, dist) if crear_api else
                   APILocal(config, router=MonitoreoRouter(), dashboard=dist))
            app.solicitar_cierre = parada.set

            def servir():
                try:
                    app.servir()
                except Exception:
                    errores.append(True)

            hilo = Thread(target=servir, name='aplicacion-local')
            hilo.start()
            limite = time.monotonic() + 15
            while not parada.is_set():
                if errores or not hilo.is_alive():
                    raise ErrorInicio('El servicio local no pudo iniciar. Puede que otro programa haya ocupado '
                                      'el puerto; revisa las ventanas abiertas y vuelve a intentarlo.')
                if app.preparada.is_set():
                    datos = consultar_inicio(app.puerto, raiz)
                    if datos:
                        comprobar_lista(datos)
                        abrir(app.puerto)
                        break
                if time.monotonic() >= limite:
                    raise ErrorInicio('El servicio no respondió a tiempo. No se puede mostrar la aplicación como lista.')
                parada.wait(.1)
            print('Mantén esta ventana abierta. Cerrar la pestaña no detiene las mediciones.\n'
                  'Usa «Cerrar aplicación» en el dashboard para terminar. También puedes pulsar Enter aquí.', flush=True)
            if esperar_cierre:
                esperar_cierre(app, parada)
            else:
                while not parada.is_set():
                    if not hilo.is_alive() or app.estado()['estado'] != 'activo':
                        raise ErrorInicio('La recolección local se detuvo. Vuelve a abrir la aplicación. '
                                          'Este fallo no demuestra una caída de Internet.')
                    if not consola or sys.stdin is None:
                        parada.wait(.5)
                    elif select.select([sys.stdin], [], [], .5)[0]:
                        sys.stdin.readline()
                        break
        finally:
            if app is not None:
                print('Cerrando las tareas de esta ventana; espera a que terminen…', flush=True)
                app.detener()
                if hilo is not None:
                    hilo.join()
                print('Aplicación cerrada. Las mediciones temporales ya no se conservan.', flush=True)
            for senal, anterior in anteriores.items():
                signal.signal(senal, anterior)


def main():
    """Convierte fallos esperables en instrucciones sin un traceback para principiantes."""
    try:
        if sys.version_info[:2] != (3, 14):
            raise ErrorInicio('Esta copia necesita su entorno Python 3.14. Pide reparar la carpeta .venv.')
        ejecutar()
    except ImportError:
        print('Faltan módulos del backend. Recupera la carpeta completa del proyecto '
              'y pide revisar su entorno Python 3.14.', flush=True)
        return 1
    except (ErrorInicio, OSError) as error:
        print(f'No se pudo abrir la aplicación.\n{error}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
