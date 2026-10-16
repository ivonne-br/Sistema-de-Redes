"""Verifica RF-24 con HTTP loopback y fuentes falsas: entradas controladas,
arranque/reutilización/cierre y errores; no consulta la red ni abre un navegador.
"""

from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import signal
import select
import socket
import subprocess
import sys
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from backend.api import APILocal
from backend.configuracion import ConfiguracionBackend
from backend.coordinador import CoordinadorARP
from backend.inicio import (APLICACION, ErrorInicio, RAIZ, comprobar_lista,
                            consultar_inicio, dashboard_valido, ejecutar, identidad,
                            preparar_dashboard, abrir_dashboard)
from test_coordinador import contexto, lectura


class PruebasInicio(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.dist = self.raiz / 'frontend/dist'
        (self.dist / 'assets').mkdir(parents=True)
        (self.dist / 'index.html').write_text('<html><script src="/assets/app.js"></script></html>')
        (self.dist / 'assets/app.js').write_text('console.log("prueba")')
        self.fuente = Mock(return_value=lectura())
        self.fabricas = []

    def crear_api(self, config, dist):
        config = replace(config, busqueda_activa=False, conectividad_activa=False, web_activa=False)
        c = CoordinadorARP(config, consultar_arp=self.fuente, consultar_contexto=Mock(return_value=contexto()))
        app = APILocal(config, crear_coordinador=Mock(return_value=c), dashboard=dist)
        self.fabricas.append(app)
        return app

    @contextmanager
    def api(self):
        app = self.crear_api(ConfiguracionBackend(puerto_api=0), self.dist)
        hilo = Thread(target=app.servir)
        hilo.start()
        try:
            self.assertTrue(app.preparada.wait(3))
            yield app
        finally:
            app.detener()
            hilo.join(4)
            self.assertFalse(hilo.is_alive())

    def pedir(self, puerto, ruta, headers=None):
        c = HTTPConnection('127.0.0.1', puerto, timeout=2)
        try:
            c.request('GET', ruta, headers=headers or {})
            r = c.getresponse()
            return r.status, r.getheader('Content-Type'), r.read()
        finally:
            c.close()

    def pedir_cierre(self, app, *, confirmado=True, identificador=None, origen=True, cabecera=True):
        """Envía una confirmación controlada, sin navegador ni permisos del router."""
        headers = {'Content-Type': 'application/json'}
        if origen:
            headers['Origin'] = f'http://127.0.0.1:{app.puerto}' if origen is True else origen
        if cabecera:
            headers['X-Red-Accion'] = 'cerrar-aplicacion'
        cuerpo = json.dumps({'confirmado': confirmado, 'id_ejecucion': identificador or app.estado()['id_ejecucion']})
        c = HTTPConnection('127.0.0.1', app.puerto, timeout=2)
        try:
            c.request('POST', '/api/v1/cierre', body=cuerpo, headers=headers)
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()

    def test_cierre_desde_pantalla_detiene_el_servicio_del_iniciador(self):
        def cierre(app, parada):
            estado = json.loads(self.pedir(app.puerto, '/api/v1/estado')[2])
            self.assertTrue(estado['cierre_disponible'])
            codigo, datos = self.pedir_cierre(app)
            self.assertEqual(codigo, 202)
            self.assertEqual(datos['estado'], 'cierre_solicitado')
            self.assertTrue(parada.wait(2))
        with patch('backend.inicio.preparar_dashboard', return_value=self.dist), \
                patch('backend.api.identidad', return_value=identidad(self.raiz)), redirect_stdout(io.StringIO()):
            ejecutar(self.raiz, 0, crear_api=self.crear_api, abrir=Mock(), esperar_cierre=cierre)
        self.assertEqual(self.fabricas[0].estado()['estado'], 'detenido')

    def test_cierre_no_puede_detener_un_servicio_iniciado_por_separado(self):
        with self.api() as app:
            self.assertFalse(json.loads(self.pedir(app.puerto, '/api/v1/estado')[2])['cierre_disponible'])
            self.assertEqual(self.pedir_cierre(app)[0], 403)
            self.assertEqual(app.estado()['estado'], 'activo')

    def test_cierre_rechaza_confirmacion_ausente_origen_ajeno_y_pagina_antigua(self):
        with self.api() as app:
            app.solicitar_cierre = Mock()
            self.assertEqual(self.pedir_cierre(app, confirmado=False)[0], 400)
            self.assertEqual(self.pedir_cierre(app, confirmado=1)[0], 400)
            self.assertEqual(self.pedir_cierre(app, origen=False)[0], 400)
            self.assertEqual(self.pedir_cierre(app, origen='https://ajeno.example')[0], 403)
            self.assertEqual(self.pedir_cierre(app, cabecera=False)[0], 400)
            self.assertEqual(self.pedir_cierre(app, identificador='ejecucion-anterior')[0], 409)
            self.assertEqual(self.pedir(app.puerto, '/api/v1/cierre')[0], 404)
            app.solicitar_cierre.assert_not_called()
            self.assertEqual(app.estado()['estado'], 'activo')

    def test_arranque_apertura_repetida_y_cierre_solo_del_dueno(self):
        abrir = Mock()
        def cierre(app, parada):
            cantidad = self.fuente.call_count
            ejecutar(self.raiz, app.puerto, crear_api=self.crear_api, abrir=abrir)
            self.assertEqual(len(self.fabricas), 1)
            self.assertEqual(self.fuente.call_count, cantidad)
            self.assertEqual(app.estado()['estado'], 'activo')
            self.assertEqual(self.pedir(app.puerto, '/')[0], 200)
        with patch('backend.inicio.preparar_dashboard', return_value=self.dist), \
                patch('backend.api.identidad', return_value=identidad(self.raiz)), redirect_stdout(io.StringIO()):
            ejecutar(self.raiz, 0, crear_api=self.crear_api, abrir=abrir, esperar_cierre=cierre)
        self.assertEqual(abrir.call_count, 2)
        self.assertEqual(self.fabricas[0].estado()['estado'], 'detenido')

    def test_reutiliza_api_de_desarrollo_sin_cerrarla(self):
        with self.api() as app, patch('backend.inicio.preparar_dashboard') as preparar, redirect_stdout(io.StringIO()):
            abrir = Mock()
            ejecutar(RAIZ, app.puerto, crear_api=Mock(side_effect=AssertionError()), abrir=abrir)
            preparar.assert_not_called()
            abrir.assert_called_once_with(app.puerto)
            self.assertEqual(app.estado()['estado'], 'activo')

    def test_api_identificada_y_recursos_protegidos(self):
        with self.api() as app:
            datos = consultar_inicio(app.puerto)
            self.assertEqual(datos['aplicacion'], APLICACION)
            comprobar_lista(datos)
            self.assertEqual(self.pedir(app.puerto, '/assets/app.js')[0], 200)
            for ruta in ('/../README.md', '/assets/../../README.md', '/assets/%2e%2e/config.json', '/assets/falta.js', '/api/no-existe'):
                self.assertEqual(self.pedir(app.puerto, ruta)[0], 404)
            for ruta in ('/', '/assets/app.js', '/api/v1/inicio'):
                self.assertEqual(self.pedir(app.puerto, ruta, {'Host': 'evil.example'})[0], 403)
                self.assertEqual(self.pedir(app.puerto, ruta, {'Origin': 'https://evil.example'})[0], 403)
            fuera = self.raiz / 'secreto.js'
            fuera.write_text('no publicar')
            (self.dist / 'assets/enlace.js').symlink_to(fuera)
            self.assertEqual(self.pedir(app.puerto, '/assets/enlace.js')[0], 404)

    def test_no_disponible_no_se_confunde_con_internet(self):
        with patch('backend.inicio.HTTPConnection') as conexion:
            conexion.return_value.request.side_effect = ConnectionRefusedError()
            self.assertIsNone(consultar_inicio(12345))
            conexion.return_value.request.side_effect = TimeoutError()
            with self.assertRaisesRegex(ErrorInicio, 'no responde'):
                consultar_inicio(12345)

    def test_dos_procesos_reutilizan_y_enter_cierra_solo_el_propietario(self):
        codigo = '''
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, 'tests')
from test_inicio import PruebasInicio
from backend.inicio import ejecutar, identidad
p = PruebasInicio()
p.setUp()
raiz = Path(sys.argv[1])
with patch('backend.inicio.preparar_dashboard', return_value=raiz / 'frontend/dist'), patch('backend.api.identidad', return_value=identidad(raiz)):
    ejecutar(raiz, 0, crear_api=p.crear_api, abrir=lambda puerto: print('LISTA', puerto, flush=True))
p.doCleanups()
'''
        proceso = subprocess.Popen([sys.executable, '-B', '-c', codigo, str(self.raiz)],
                                   cwd=RAIZ, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(select.select([proceso.stdout], [], [], 5)[0])
            linea = proceso.stdout.readline()
            self.assertTrue(linea.startswith('LISTA '), linea)
            puerto = int(linea.split()[1])
            abrir = Mock()
            with redirect_stdout(io.StringIO()):
                ejecutar(self.raiz, puerto, crear_api=Mock(side_effect=AssertionError()), abrir=abrir)
            abrir.assert_called_once_with(puerto)
            self.assertIsNone(proceso.poll())
            self.assertEqual(self.pedir(puerto, '/')[0], 200)
            salida, error = proceso.communicate('\n', timeout=5)
            self.assertEqual(proceso.returncode, 0, error)
            self.assertIn('Aplicación cerrada', salida)
        finally:
            if proceso.poll() is None:
                proceso.terminate()
                proceso.communicate(timeout=5)

    def test_servicio_ajeno_no_crea_recolector(self):
        class Ajeno(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"version_esquema":1}')
            def log_message(self, *_):
                pass
        servidor = ThreadingHTTPServer(('127.0.0.1', 0), Ajeno)
        hilo = Thread(target=servidor.serve_forever)
        hilo.start()
        try:
            crear = Mock()
            with self.assertRaisesRegex(ErrorInicio, 'ocupado'), patch('backend.inicio.preparar_dashboard') as preparar:
                ejecutar(self.raiz, servidor.server_port, crear_api=crear)
            crear.assert_not_called()
            preparar.assert_not_called()
            self.assertEqual(self.pedir(servidor.server_port, '/')[0], 200)
        finally:
            servidor.shutdown()
            servidor.server_close()
            hilo.join(3)

    def test_api_otra_instalacion_no_se_reutiliza(self):
        with self.api() as app:
            with self.assertRaises(ErrorInicio):
                consultar_inicio(app.puerto, self.raiz)

    def test_dashboard_incompleto_o_api_detenida_no_listos(self):
        with self.assertRaisesRegex(ErrorInicio, 'dashboard'):
            comprobar_lista({'dashboard': False})
        with self.assertRaisesRegex(ErrorInicio, 'recolección'):
            comprobar_lista({'dashboard': True, 'monitoreo': {'estado': 'detenido'}})
        (self.dist / 'assets/app.js').unlink()
        self.assertFalse(dashboard_valido(self.dist))

    def test_fallo_de_arranque_no_abre_y_limpia(self):
        app = Mock()
        app.servir.side_effect = RuntimeError('fallo controlado')
        abrir = Mock()
        with patch('backend.inicio.preparar_dashboard', return_value=self.dist), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ErrorInicio, 'no pudo iniciar'):
                ejecutar(self.raiz, 0, crear_api=lambda *_: app, abrir=abrir)
        abrir.assert_not_called()
        app.detener.assert_called_once()

    def test_api_que_no_se_prepara_agota_plazo_sin_abrir(self):
        fin = Event()
        app = Mock()
        app.preparada = Event()
        app.servir.side_effect = lambda: fin.wait(3)
        app.detener.side_effect = fin.set
        abrir = Mock()
        with patch('backend.inicio.preparar_dashboard', return_value=self.dist), \
                patch('backend.inicio.time.monotonic', side_effect=[0, 0, 20]), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ErrorInicio, 'a tiempo'):
                ejecutar(self.raiz, 0, crear_api=lambda *_: app, abrir=abrir)
        abrir.assert_not_called()
        self.assertTrue(fin.is_set())

    def test_arranque_en_puerto_libre_no_cero(self):
        with socket.socket() as reserva:
            reserva.bind(('127.0.0.1', 0))
            puerto = reserva.getsockname()[1]
        with patch('backend.inicio.preparar_dashboard', return_value=self.dist), \
                patch('backend.api.identidad', return_value=identidad(self.raiz)), redirect_stdout(io.StringIO()):
            abrir = Mock()
            ejecutar(self.raiz, puerto, crear_api=self.crear_api, abrir=abrir, esperar_cierre=lambda *_: None)
        abrir.assert_called_once_with(puerto)

    def test_senal_solicita_cierre_y_restaura_manejador(self):
        anterior = signal.getsignal(signal.SIGTERM)
        def cierre(app, parada):
            signal.raise_signal(signal.SIGTERM)
            self.assertTrue(parada.is_set())
        with patch('backend.inicio.preparar_dashboard', return_value=self.dist), \
                patch('backend.api.identidad', return_value=identidad(self.raiz)), redirect_stdout(io.StringIO()):
            ejecutar(self.raiz, 0, crear_api=self.crear_api, abrir=Mock(), esperar_cierre=cierre)
        self.assertEqual(signal.getsignal(signal.SIGTERM), anterior)
        self.assertEqual(self.fabricas[0].estado()['estado'], 'detenido')

    def preparar_fuentes(self):
        for nombre in ('package.json', 'package-lock.json', 'index.html', 'vite.config.js'):
            (self.raiz / 'frontend' / nombre).write_text('contenido')
        (self.raiz / 'frontend/node_modules/vite/bin').mkdir(parents=True)
        (self.raiz / 'frontend/node_modules/vite/bin/vite.js').write_text('')

    def test_compila_una_vez_y_recompila_si_cambia_fuente(self):
        self.preparar_fuentes()
        with patch('backend.inicio.shutil.which', return_value='/local/bin/npm'), \
                patch('backend.inicio.subprocess.run', return_value=Mock(returncode=0)) as construir, redirect_stdout(io.StringIO()):
            preparar_dashboard(self.raiz)
            preparar_dashboard(self.raiz)
            self.assertEqual(construir.call_count, 1)
            (self.raiz / 'frontend/index.html').write_text('cambio')
            preparar_dashboard(self.raiz)
            self.assertEqual(construir.call_count, 2)
            self.assertNotIn('ci', construir.call_args.args[0])

    def test_archivos_y_dependencias_faltantes(self):
        with self.assertRaisesRegex(ErrorInicio, 'Faltan archivos'):
            preparar_dashboard(self.raiz)
        self.preparar_fuentes()
        (self.raiz / 'frontend/node_modules/vite/bin/vite.js').unlink()
        with self.assertRaisesRegex(ErrorInicio, 'Falta preparar'):
            preparar_dashboard(self.raiz)

    def test_error_y_timeout_de_compilacion(self):
        self.preparar_fuentes()
        with patch('backend.inicio.shutil.which', return_value='/local/bin/npm'), redirect_stdout(io.StringIO()):
            with patch('backend.inicio.subprocess.run', return_value=Mock(returncode=1)):
                with self.assertRaisesRegex(ErrorInicio, 'No se pudo preparar'):
                    preparar_dashboard(self.raiz)
            with patch('backend.inicio.subprocess.run', side_effect=subprocess.TimeoutExpired('npm', 120)):
                with self.assertRaisesRegex(ErrorInicio, 'a tiempo'):
                    preparar_dashboard(self.raiz)

    def test_navegador_fallido_ofrece_url(self):
        salida = io.StringIO()
        with patch('backend.inicio.subprocess.run', side_effect=OSError()), redirect_stdout(salida):
            abrir_dashboard(12345)
        self.assertIn('http://127.0.0.1:12345/', salida.getvalue())
        self.assertIn('No se pudo abrir el navegador', salida.getvalue())
