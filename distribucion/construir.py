"""Construye una entrega local por SO a partir de una lista limitada de fuentes.

Entradas: Python de construcción, npm y repositorio. Salidas: app y contenedor
en dist/entregas; no publica, firma con identidad ni copia datos de la vivienda.
Windows requiere Inno Setup (ISCC); Linux produce un tar con instalador de usuario.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile

RAIZ = Path(__file__).resolve().parents[1]
NOMBRE = 'Sistema de Redes'


def copiar_fuentes(destino):
    """Solo módulos Python y recursos compilados públicos; rechaza enlaces."""
    backend = destino / 'backend'
    backend.mkdir(parents=True)
    for archivo in sorted((RAIZ / 'backend').glob('*.py')):
        if archivo.is_symlink():
            raise ValueError('No se permiten enlaces en las fuentes del paquete.')
        shutil.copyfile(archivo, backend / archivo.name)
    dist = RAIZ / 'frontend/dist'
    for archivo in sorted(dist.rglob('*')):
        if archivo.is_symlink():
            raise ValueError('No se permiten enlaces en el dashboard.')
        if not archivo.is_file():
            continue
        relativa = archivo.relative_to(dist)
        if relativa == Path('index.html') or (relativa.parts[0] == 'assets' and archivo.suffix in {
                '.js', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2'}):
            salida = destino / 'frontend/dist' / relativa
            salida.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archivo, salida)
    shutil.copyfile(RAIZ / 'distribucion/entrada.py', destino / 'entrada.py')


def licencias(destino):
    """Conserva avisos de los componentes redistribuidos, sin copiar node_modules."""
    destino.mkdir()
    python = next((p for p in (Path(sys.base_prefix) / 'LICENSE.txt',
                              Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt') if p.is_file()), None)
    if python is None:
        raise RuntimeError('Falta LICENSE.txt del runtime Python; no entregar sin sus avisos.')
    shutil.copyfile(python, destino / 'Python.txt')
    shutil.copyfile(RAIZ / 'frontend/node_modules/vue/LICENSE', destino / 'Vue.txt')
    for nombre in ('certifi', 'pyinstaller'):
        dist = importlib.metadata.distribution(nombre)
        for ruta in dist.files or []:
            if 'license' in str(ruta).lower() or 'copying' in str(ruta).lower():
                archivo = Path(dist.locate_file(ruta))
                if archivo.is_file():
                    shutil.copyfile(archivo, destino / f'{nombre}-{archivo.name}.txt')
    if platform.system() == 'Darwin':
        # Recupera avisos de bibliotecas del Python constructor, no de datos locales.
        extensiones = list((Path(sysconfig.get_path('stdlib')) / 'lib-dynload').glob('*.so'))
        dependencias = subprocess.run(['otool', '-L', *map(str, extensiones)],
                                     check=True, capture_output=True, text=True).stdout
        for linea in dependencias.splitlines():
            if not linea.startswith('\t'):
                continue
            ruta = linea.strip().split(' (')[0]
            if not ruta.startswith('/') or ruta.startswith(('/usr/lib/', '/System/')):
                continue
            for padre in Path(ruta).resolve().parents:
                avisos = [p for patron in ('LICENSE*', 'COPYING*', 'COPYRIGHT*') for p in padre.glob(patron) if p.is_file()]
                if avisos:
                    for aviso in avisos:
                        shutil.copyfile(aviso, destino / f'{padre.parent.name}-{padre.name}-{aviso.name}.txt')
                    break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida', type=Path, default=RAIZ / 'dist/entregas')
    opciones = parser.parse_args()
    if sys.version_info[:2] != (3, 14):
        parser.error('Construir con Python 3.14, según pyproject.toml.')
    sistema = platform.system()
    if sistema not in ('Darwin', 'Windows', 'Linux'):
        parser.error('Sistema de construcción no previsto.')
    etiqueta = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}[sistema]
    salida = opciones.salida.resolve() / f'{etiqueta}-{platform.machine()}'
    salida.mkdir(parents=True, exist_ok=False)
    npm = shutil.which('npm')
    if not npm:
        parser.error('npm es necesario solo en el equipo que construye el paquete.')
    subprocess.run([npm, '--prefix', str(RAIZ / 'frontend'), 'run', 'build'], check=True)
    with tempfile.TemporaryDirectory(prefix='redes-construccion-') as temporal:
        trabajo = Path(temporal)
        fuente = trabajo / 'fuentes'
        copiar_fuentes(fuente)
        licencias(fuente / 'licencias')
        env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(trabajo / 'cache'))
        comando = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
                   '--name', NOMBRE, '--paths', str(fuente), '--distpath', str(salida),
                   '--workpath', str(trabajo / 'build'), '--specpath', str(trabajo),
                   '--add-data', f'{fuente / "frontend/dist"}:frontend/dist',
                   '--add-data', f'{fuente / "licencias"}:licencias', '--collect-data', 'certifi',
                   '--hidden-import', 'certifi']
        if sistema == 'Darwin':
            comando += ['--windowed', '--osx-bundle-identifier', 'local.sistema.redes']
        elif sistema == 'Windows':
            # Consola permite obtener diagnósticos; el acceso directo usa python-free exe.
            comando += ['--console']
        subprocess.run(comando + [str(fuente / 'entrada.py')], cwd=fuente, env=env, check=True)
    if sistema == 'Darwin':
        app = salida / f'{NOMBRE}.app'
        # LaunchServices permite una segunda invocación que reutiliza la API verificada.
        info = app / 'Contents/Info.plist'
        datos = plistlib.loads(info.read_bytes())
        datos.update(CFBundleShortVersionString='0.1.0', CFBundleVersion='1',
                     LSUIElement=True, NSLocalNetworkUsageDescription='Observa la red doméstica desde esta computadora.')
        info.write_bytes(plistlib.dumps(datos))
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
        ejecutable = app / f'Contents/MacOS/{NOMBRE}'
    else:
        ejecutable = salida / NOMBRE / (NOMBRE + ('.exe' if sistema == 'Windows' else ''))
    subprocess.run([str(ejecutable), '--autoprueba', '--resultado', str(salida / 'autoprueba.json')], check=True)
    if sistema == 'Darwin':
        with tempfile.TemporaryDirectory(prefix='redes-dmg-') as temporal:
            contenido = Path(temporal)
            subprocess.run(['ditto', str(app), str(contenido / app.name)], check=True)
            (contenido / 'Applications').symlink_to('/Applications')
            subprocess.run(['hdiutil', 'create', '-volname', NOMBRE, '-srcfolder', str(contenido),
                            '-ov', '-format', 'UDZO', str(salida / 'Sistema-de-Redes-prueba.dmg')], check=True)
    elif sistema == 'Windows':
        compilador = shutil.which('ISCC')
        if not compilador:
            raise RuntimeError('App creada; falta Inno Setup ISCC para crear el instalador de Windows.')
        subprocess.run([compilador, f'/DOrigen={salida / NOMBRE}', f'/DSalida={salida}',
                        str(RAIZ / 'distribucion/windows/instalador.iss')], check=True)
    else:
        carpeta = salida / NOMBRE
        shutil.copyfile(RAIZ / 'distribucion/linux/instalar.sh', carpeta / 'instalar.sh')
        (carpeta / 'instalar.sh').chmod(0o755)
        shutil.make_archive(str(salida / 'Sistema-de-Redes-experimental'), 'gztar', salida, NOMBRE)
    archivos = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in salida.iterdir()
                if p.is_file() and p.suffix in ('.dmg', '.exe', '.gz')}
    manifiesto = {'version': '0.1.0', 'sistema_construccion': sistema, 'arquitectura': platform.machine(),
                  'version_sistema': platform.platform(), 'python': platform.python_version(),
                  'tipo': 'prueba local; no distribución final', 'developer_id': False,
                  'notarizada': False, 'otra_computadora_verificada': False, 'sha256': archivos,
                  'recoleccion_windows_linux': 'pendiente de adaptación y validación',
                  'herramientas': {n: importlib.metadata.version(n) for n in ('pyinstaller', 'certifi')}}
    (salida / 'manifiesto.json').write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Entrega local de prueba: {salida}')


if __name__ == '__main__':
    main()
