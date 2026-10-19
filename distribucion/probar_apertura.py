"""Comprueba apertura real macOS y cierra solo la instancia creada por esta prueba.

Entrada: .app y salida JSON. Abre navegador y monitoreo normal (solo lectura sin
autorización administrativa). Si el puerto está ocupado, no abre ni cierra nada.
"""

import argparse
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import time


def consultar():
    conexion = HTTPConnection('127.0.0.1', 8000, timeout=2)
    try:
        conexion.request('GET', '/api/v1/inicio')
        respuesta = conexion.getresponse()
        if respuesta.status != 200:
            raise RuntimeError('El puerto está ocupado por otro servicio; no se modifica.')
        return json.loads(respuesta.read(8192))
    except ConnectionRefusedError:
        return None
    finally:
        conexion.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--resultado', type=Path, required=True)
    opciones = parser.parse_args()
    if consultar() is not None:
        raise RuntimeError('Hay un servicio abierto; no se modifica ni se detiene.')
    identificador = None
    esperado = hashlib.sha256(b'sistema-de-redes-paquete-v1').hexdigest()
    resultado = {}
    try:
        subprocess.run(['/usr/bin/open', str(opciones.app.resolve())], check=True)
        limite = time.monotonic() + 25
        while time.monotonic() < limite:
            dato = consultar()
            if dato:
                if dato.get('instalacion') != esperado:
                    raise RuntimeError('Respondió otra instalación; no se cierra.')
                identificador = dato['monitoreo']['id_ejecucion']
                if dato['dashboard'] and dato['monitoreo']['estado'] == 'activo':
                    break
            time.sleep(.2)
        else:
            raise RuntimeError('La aplicación no estuvo disponible a tiempo.')
        subprocess.run(['/usr/bin/open', str(opciones.app.resolve())], check=True)
        time.sleep(2)
        segundo = consultar()
        if segundo['monitoreo']['id_ejecucion'] != identificador:
            raise RuntimeError('Cambió la instancia durante la reapertura.')
        resultado.update(apertura_desde_macos=True, reapertura_misma_instancia=True,
                         dashboard_disponible=True, internet_funcionando='no inferido',
                         recoleccion_real='iniciada; exactitud de métricas no validada')
    finally:
        if identificador:
            actual = consultar()
            if actual and actual.get('instalacion') == esperado and actual['monitoreo']['id_ejecucion'] == identificador:
                conexion = HTTPConnection('127.0.0.1', 8000, timeout=3)
                try:
                    conexion.request('POST', '/api/v1/cierre', json.dumps({
                        'confirmado': True, 'id_ejecucion': identificador}), {
                            'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:8000',
                            'X-Red-Accion': 'cerrar-aplicacion'})
                    respuesta = conexion.getresponse()
                    respuesta.read()
                    if respuesta.status != 202:
                        raise RuntimeError('La instancia no aceptó el cierre.')
                finally:
                    conexion.close()
                limite = time.monotonic() + 35
                while time.monotonic() < limite:
                    if consultar() is None:
                        resultado['cierre_instancia_propia'] = True
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('La instancia aún no terminó; no se forzó ningún cierre.')
    opciones.resultado.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
