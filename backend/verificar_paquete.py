"""Diagnóstico reproducible del paquete con HTTP loopback y recolector inerte.

Sin datos de vivienda ni router: comprueba recursos, TLS, reutilización y cierre.
Devuelve evidencia JSON; no certifica recolección real ni compatibilidad del SO.
"""

from contextlib import redirect_stdout
from dataclasses import replace
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import platform
import ssl
import sys
import tempfile
from threading import Event
from unittest.mock import patch
from uuid import uuid4


def verificar():
    from backend.api import APILocal
    from backend.inicio import RAIZ, ejecutar, preparar_dashboard
    from backend.web import ejecutar_comprobacion

    dist = preparar_dashboard(RAIZ)
    aperturas, instancias = [], []

    class RecolectorInerte:
        def __init__(self, config):
            self.id_ejecucion = str(uuid4())
            self.consulta = None
            self.parada = Event()

        def ejecutar(self, **opciones):
            self.parada.wait(30)

        def detener(self):
            self.parada.set()

    def crear(config, dashboard):
        config = replace(config, busqueda_activa=False, conectividad_activa=False, web_activa=False)
        app = APILocal(config, crear_coordinador=RecolectorInerte, dashboard=dashboard)
        instancias.append(app)
        return app

    def pedir(puerto, metodo, ruta, cuerpo=None, cabeceras=None):
        conexion = HTTPConnection('127.0.0.1', puerto, timeout=3)
        try:
            conexion.request(metodo, ruta, body=cuerpo, headers=cabeceras or {})
            respuesta = conexion.getresponse()
            return respuesta.status, respuesta.read()
        finally:
            conexion.close()

    def exigir(condicion, detalle):
        if not condicion:
            raise RuntimeError(detalle)

    def cerrar(app, parada):
        ejecutar(RAIZ, app.puerto, crear_api=crear, abrir=aperturas.append, consola=False)
        exigir(len(instancias) == 1 and len(aperturas) == 2, 'Instancia duplicada')
        exigir(pedir(app.puerto, 'GET', '/')[0] == 200, 'HTML no disponible')
        exigir(pedir(app.puerto, 'GET', '/', cabeceras={'Host': 'ajeno.example'})[0] == 403, 'Host no protegido')
        exigir(pedir(app.puerto, 'GET', '/', cabeceras={'Origin': 'https://ajeno.example'})[0] == 403, 'Origin no protegido')
        exigir(pedir(app.puerto, 'GET', '/assets/../../backend/paquete.py')[0] == 404, 'Recursos expuestos')
        exigir(pedir(app.puerto, 'POST', '/api/v1/cierre', '{}', {'Content-Type': 'application/json'})[0] != 202,
               'Cierre sin confirmación')
        cuerpo = json.dumps({'confirmado': True, 'id_ejecucion': app.estado()['id_ejecucion']})
        exigir(pedir(app.puerto, 'POST', '/api/v1/cierre', cuerpo, {
            'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{app.puerto}',
            'X-Red-Accion': 'cerrar-aplicacion'})[0] == 202, 'Cierre rechazado')
        exigir(parada.wait(3), 'Cierre no recibido')

    with tempfile.TemporaryDirectory(prefix='redes-verificacion-') as temporal, \
            patch('backend.inicio.archivo_bloqueo', return_value=Path(temporal) / 'inicio.lock'), \
            redirect_stdout(io.StringIO()):
        ejecutar(RAIZ, 0, crear_api=crear, abrir=aperturas.append, esperar_cierre=cerrar, consola=False)
    exigir(instancias[0].estado()['estado'] == 'detenido', 'Servicio sin cerrar')
    tls = ssl.create_default_context()
    exigir(tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED and bool(tls.get_ca_certs()), 'TLS incompleto')
    trabajador = 'pendiente: reloj Windows sin adaptar'
    if sys.platform != 'win32':
        dato = ejecutar_comprobacion('dns', '127.0.0.1', 5)
        exigir(dato['estado'] == 'correcto' and '127.0.0.1' in dato['direcciones'], 'Trabajador no disponible')
        trabajador = 'correcto con IPv4 loopback, sin Internet'
    return {'correcto': True, 'sistema': platform.system(), 'version_sistema': platform.release(),
            'arquitectura': platform.machine(), 'python': platform.python_version(),
            'dashboard': True, 'instancias_creadas': len(instancias), 'aperturas': len(aperturas),
            'host_origin': 'protegidos', 'cierre': 'verificado', 'certificados_publicos': True,
            'trabajador': trabajador, 'recoleccion_real': 'no probada',
            'otra_computadora': 'no verificada', 'distribucion_firmada': False}
