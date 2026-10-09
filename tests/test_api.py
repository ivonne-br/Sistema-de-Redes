"""HTTP en loopback con fuentes artificiales; ninguna sonda ni consulta ARP real."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from http.client import HTTPConnection
import io
import json
import logging
import signal
import socket
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from backend.__main__ import main
from backend.api import APILocal
from backend.configuracion import ConfiguracionBackend, interpretar_configuracion
from backend.coordinador import CoordinadorARP
from test_coordinador import contexto, lectura


class PruebasAPI(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger('pruebas.api')
        self.logger.handlers = [logging.NullHandler()]
        self.logger.propagate = False

    @contextmanager
    def servicio(self, *, arp=None, esperar_muestra=True):
        config = ConfiguracionBackend(puerto_api=0, intervalo_arp_s=60)
        fuente = arp if arp is not None else Mock(return_value=lectura())
        fuente_contexto = Mock(return_value=contexto())
        c = CoordinadorARP(config, consultar_arp=fuente, consultar_contexto=fuente_contexto)
        guardada = Event()
        guardar_original = c.memoria.guardar
        def guardar(*args, **kwargs):
            guardar_original(*args, **kwargs)
            guardada.set()
        c.memoria.guardar = Mock(side_effect=guardar)
        app = APILocal(config, crear_coordinador=Mock(return_value=c), logger=self.logger)
        errores = []
        def ejecutar():
            try:
                app.servir()
            except Exception as error:
                errores.append(error)
                app.preparada.set()
        hilo = Thread(target=ejecutar)
        hilo.start()
        try:
            self.assertTrue(app.preparada.wait(3))
            if errores:
                raise errores[0]
            if esperar_muestra:
                self.assertTrue(guardada.wait(2))
            yield app, c, fuente, fuente_contexto
        finally:
            app.detener()
            hilo.join(4)
            self.assertFalse(hilo.is_alive())
        self.assertEqual(errores, [])

    def pedir(self, app, ruta='/api/v1/arp/resumen', *, metodo='GET', headers=None):
        conexion = HTTPConnection('127.0.0.1', app.puerto, timeout=2)
        try:
            conexion.request(metodo, ruta, headers=headers or {})
            respuesta = conexion.getresponse()
            cuerpo = respuesta.read()
            return respuesta.status, dict(respuesta.getheaders()), json.loads(cuerpo) if cuerpo else None
        finally:
            conexion.close()

    def test_get_estado_resumen_calidad_y_peticiones_no_crean_recolectores(self):
        with self.servicio() as (app, c, arp, fuente_contexto):
            for ruta in ('/api/v1/estado', '/api/v1/arp/resumen', '/api/v1/arp/calidad'):
                codigo, headers, dato = self.pedir(app, ruta)
                self.assertEqual(codigo, 200)
                self.assertEqual(dato['version_esquema'], 1)
                self.assertEqual(dato['monitoreo']['id_ejecucion'], c.id_ejecucion)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertIn('application/json', headers['Content-Type'])
            with ThreadPoolExecutor(max_workers=4) as pool:
                respuestas = list(pool.map(lambda _: self.pedir(app), range(12)))
            self.assertTrue(all(r[0] == 200 for r in respuestas))
            self.assertEqual(arp.call_count, 1)
            self.assertEqual(fuente_contexto.call_count, 1)
            app._crear_coordinador.assert_called_once()
            self.assertEqual(respuestas[-1][2]['datos']['vecinos']['cantidad'], 1)
        self.assertEqual(app.estado()['estado'], 'detenido')
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', app.puerto), timeout=.2)

    def test_errores_http_y_solo_lectura(self):
        with self.servicio() as (app, c, arp, _):
            for metodo in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'):
                codigo, headers, dato = self.pedir(app, metodo=metodo)
                self.assertEqual(codigo, 405)
                self.assertEqual(headers['Allow'], 'GET')
                if metodo != 'HEAD':
                    self.assertEqual(dato['error']['codigo'], 'metodo_no_permitido')
            self.assertEqual(self.pedir(app, '/no-existe')[0], 404)
            for query in ('id_contexto=no', 'id_contexto=', 'otro=1', 'id_contexto=a&id_contexto=b'):
                self.assertEqual(self.pedir(app, '/api/v1/arp/resumen?' + query)[0], 400)
            self.assertEqual(self.pedir(app, '/api/v1/arp/resumen?id_contexto=00000000-0000-0000-0000-000000000000')[0], 404)
            self.assertEqual(arp.call_count, 1)

    def test_host_y_origen_externo_rechazados_sin_cors(self):
        with self.servicio() as (app, _, _, _):
            for headers in ({'Host': 'externo.test'}, {'Origin': 'https://externo.test'},
                            {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}):
                codigo, respuesta, _ = self.pedir(app, headers=headers)
                self.assertEqual(codigo, 403)
                self.assertNotIn('Access-Control-Allow-Origin', respuesta)
            self.assertEqual(self.pedir(app, headers={'Origin': f'http://127.0.0.1:{app.puerto}'})[0], 200)

    def test_segunda_api_en_mismo_proceso_no_crea_otro_monitor(self):
        with self.servicio() as (app, _, _, _):
            fabrica = Mock()
            segunda = APILocal(ConfiguracionBackend(puerto_api=0), crear_coordinador=fabrica)
            with self.assertRaises(RuntimeError):
                segunda.servir()
            fabrica.assert_not_called()
            self.assertEqual(self.pedir(app, '/api/v1/estado')[2]['monitoreo']['estado'], 'activo')

    def test_puerto_ocupado_no_inicia_recoleccion_y_libera_guardia(self):
        with socket.socket() as ocupado:
            ocupado.bind(('127.0.0.1', 0))
            ocupado.listen()
            fabrica = Mock()
            app = APILocal(ConfiguracionBackend(puerto_api=ocupado.getsockname()[1]), crear_coordinador=fabrica)
            with self.assertRaises(OSError):
                app.servir()
            fabrica.assert_not_called()
        with self.servicio() as (app, _, _, _):
            self.assertEqual(self.pedir(app, '/api/v1/estado')[0], 200)

    def test_lectura_bloqueada_no_bloquea_http_y_parada_termina_ciclo(self):
        entrar, liberar = Event(), Event()
        def leer():
            entrar.set()
            if not liberar.wait(3):
                raise RuntimeError('Fuente de prueba sin liberar.')
            return lectura()
        fuente = Mock(side_effect=leer)
        with self.servicio(arp=fuente, esperar_muestra=False) as (app, c, _, _):
            try:
                self.assertTrue(entrar.wait(1))
                codigo, _, dato = self.pedir(app)
                self.assertEqual(codigo, 200)
                self.assertIsNone(dato['datos']['vecinos']['cantidad'])
                app.detener()
            finally:
                liberar.set()
        self.assertEqual(len(c.memoria.historial()), 1)
        fuente.assert_called_once()

    def test_error_de_fuente_devuelve_200_con_calidad_fallida(self):
        with self.servicio(arp=Mock(return_value=lectura('error_recoleccion'))) as (app, _, _, _):
            codigo, _, dato = self.pedir(app)
            self.assertEqual(codigo, 200)
            self.assertEqual(dato['datos']['calidad']['calidad_fuente'], 'error_fuente')
            self.assertIsNone(dato['datos']['vecinos']['cantidad'])

    def test_excepcion_monitor_visible_y_error_consulta_sin_detalle_privado(self):
        with self.servicio(arp=Mock(side_effect=RuntimeError('dato-privado')), esperar_muestra=False) as (app, _, _, _):
            codigo, _, dato = self.pedir(app, '/api/v1/estado')
            self.assertEqual(codigo, 200)
            self.assertEqual(dato['monitoreo']['estado'], 'error')
            self.assertNotIn('dato-privado', json.dumps(dato))
            with patch.object(app.consulta, 'resumen', side_effect=RuntimeError('dato-privado')):
                codigo, _, dato = self.pedir(app)
            self.assertEqual(codigo, 500)
            self.assertNotIn('dato-privado', json.dumps(dato))

    def test_cli_senales_restauradas_y_json_inicio(self):
        for senal in (signal.SIGINT, signal.SIGTERM):
            app = APILocal(ConfiguracionBackend(puerto_api=0), logger=self.logger,
                           crear_coordinador=lambda conf: CoordinadorARP(conf,
                               consultar_contexto=Mock(return_value=contexto()),
                               consultar_arp=Mock(return_value=lectura())))
            original = app.servir
            def servir(*, al_iniciar):
                def inicio(api):
                    al_iniciar(api)
                    signal.raise_signal(senal)
                original(al_iniciar=inicio)
            anteriores = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
            salida = io.StringIO()
            with patch('sys.argv', ['backend', 'servir-api', '--puerto', '0']), \
                 patch('backend.__main__.APILocal', return_value=app), \
                 patch.object(app, 'servir', side_effect=servir), \
                 redirect_stdout(salida), redirect_stderr(io.StringIO()):
                main()
            self.assertEqual(json.loads(salida.getvalue())['url'], f'http://127.0.0.1:{app.puerto}')
            self.assertEqual(app.estado()['estado'], 'detenido')
            self.assertEqual({s: signal.getsignal(s) for s in anteriores}, anteriores)

    def test_configuracion_y_cli_rechazan_puerto_antes_de_iniciar(self):
        self.assertEqual(interpretar_configuracion('{"puerto_api":0}').puerto_api, 0)
        for valor in (True, None, -1, 65536, 1.5, '8000'):
            with self.assertRaises((TypeError, ValueError)):
                ConfiguracionBackend(puerto_api=valor)
        with patch('sys.argv', ['backend', 'servir-api', '--puerto', '-1']), \
             patch('backend.__main__.APILocal') as fabrica, redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 2)
        fabrica.assert_not_called()

    def test_filtro_contexto_existente_y_direccion_loopback(self):
        with self.servicio() as (app, c, _, _):
            identificador = c.memoria.ultima()['id_contexto']
            codigo, _, dato = self.pedir(app, '/api/v1/arp/resumen?id_contexto=' + identificador)
            self.assertEqual(codigo, 200)
            self.assertEqual(dato['datos']['calidad']['id_contexto'], identificador)
            self.assertEqual(self.pedir(app, '/api/v1/estado?id_contexto=' + identificador)[0], 400)
        with patch('backend.api._ServidorLocal', side_effect=OSError('prueba')) as servidor:
            with self.assertRaises(OSError):
                APILocal(ConfiguracionBackend(puerto_api=0)).servir()
        self.assertEqual(servidor.call_args.args[0], ('127.0.0.1', 0))

    def test_error_arranque_libera_puerto_y_guardia_sin_dejar_monitor(self):
        config = ConfiguracionBackend(puerto_api=0)
        app = APILocal(config, crear_coordinador=Mock(side_effect=RuntimeError('fallo de inicio')))
        with self.assertRaises(RuntimeError):
            app.servir()
        with socket.socket() as prueba:
            prueba.bind(('127.0.0.1', app.puerto))
        with self.servicio() as (otra, _, _, _):
            self.assertEqual(self.pedir(otra, '/api/v1/estado')[0], 200)
