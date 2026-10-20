"""Verifica una .app local movida, con HOME temporal y sin herramientas en PATH.

Entrada: .app macOS; salida: JSON de pruebas de empaquetado. Solo altera una copia
temporal; no abre navegador, consulta routers ni toca servidores de desarrollo.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def verificar(app):
    resultados = {}
    with tempfile.TemporaryDirectory(prefix='redes-entrega-') as temporal:
        raiz = Path(temporal)
        copia = raiz / 'carpeta con espacios/Sistema de Redes.app'
        copia.parent.mkdir()
        shutil.copytree(app, copia, symlinks=True)
        hogar = raiz / 'usuario sin desarrollo'
        hogar.mkdir()
        ejecutable = copia / 'Contents/MacOS/Sistema de Redes'
        entorno = {'HOME': str(hogar), 'PATH': '/usr/bin:/bin', 'TMPDIR': str(raiz),
                   'LANG': 'en_US.UTF-8'}

        def probar(correcto):
            proceso = subprocess.run([str(ejecutable), '--autoprueba'], cwd=hogar,
                                     env=entorno, capture_output=True, text=True, timeout=45)
            datos = json.loads(proceso.stdout)
            if (proceso.returncode == 0) != correcto or datos['correcto'] != correcto:
                raise RuntimeError('La copia no respondió como se esperaba: ' + proceso.stdout)
            return datos

        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(copia)], check=True)
        resultados['firma_local_adhoc_integra'] = True
        resultados['movida_sin_python_node_en_path'] = probar(True)
        recursos = copia / 'Contents/Resources'
        index = recursos / 'frontend/dist/index.html'
        index.rename(index.with_suffix('.apartado'))
        resultados['pantalla_ausente_rechazada'] = not probar(False)['correcto']
        index.with_suffix('.apartado').rename(index)
        certificado = recursos / 'certifi/cacert.pem'
        certificado.rename(certificado.with_suffix('.apartado'))
        resultados['certificados_ausentes_rechazados'] = not probar(False)['correcto']
        certificado.with_suffix('.apartado').rename(certificado)
        referencias = []
        for archivo in (copia / 'Contents/Frameworks').rglob('*'):
            if archivo.is_file() and not archivo.is_symlink():
                tipo = subprocess.run(['file', '-b', str(archivo)], capture_output=True, text=True, check=True).stdout
                if 'Mach-O' in tipo:
                    salida = subprocess.run(['otool', '-L', str(archivo)], capture_output=True, text=True, check=True).stdout
                    for linea in salida.splitlines()[1:]:
                        referencia = linea.strip().split(' (')[0]
                        if referencia.startswith('/') and not referencia.startswith(('/usr/lib/', '/System/Library/')):
                            referencias.append(referencia)
        if referencias:
            raise RuntimeError('Bibliotecas externas no incluidas: ' + repr(referencias))
        resultados['bibliotecas_sin_rutas_del_equipo_constructor'] = True
        resultados['no_certifica'] = ['otra computadora', 'Gatekeeper de descarga', 'recolección real', 'Windows', 'Linux']
    return resultados


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--resultado', type=Path, required=True)
    opciones = parser.parse_args()
    datos = verificar(opciones.app.resolve())
    opciones.resultado.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(datos, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
