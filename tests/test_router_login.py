"""Protocolo de login con respuestas artificiales; sin credenciales reales ni red."""
import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock, patch
from http.client import BadStatusLine
from urllib.parse import parse_qs
from backend.router_login import iniciar_sesion
from backend.router import ErrorRouter, MonitoreoRouter
from backend.router_http import cabeceras_router


class LoginTests(unittest.TestCase):
    def test_http_malformado_no_se_confunde_con_credenciales_invalidas(self):
        conexion = Mock()
        conexion.getresponse.side_effect = BadStatusLine('UNKNOWN 400 Bad Request')
        with patch('backend.router_login.HTTPConnection', return_value=conexion):
            with self.assertRaisesRegex(ErrorRouter, '^http_invalido_router$') as fallo:
                iniciar_sesion('192.168.50.1', 'prueba', 'artificial', lambda: True)
        self.assertEqual(fallo.exception.etapa, 'pagina_login')
        self.assertEqual(conexion.request.call_count, 1)
        self.assertEqual(conexion.request.call_args.args[0], 'GET')
        conexion.close.assert_called_once()

    def ejecutar(self, resultado='"1"', ocupado='0', espera='0', vigente=lambda: True):
        paginas = [
            ('Sercomm js/login.js var csrf_token="inicial";', []),
            ('$.getJSON csrf_token statussupportwan_wan_statistics.json', []),
            (json.dumps([{'encryption_key': 'reto', 'delay_time': espera}]), []),
            (ocupado, []), (resultado, [('Set-Cookie', 'session_id=artificial; Path=/; HttpOnly')]),
            ('var csrf_token="nuevo";', [])]
        conexiones = []
        for contenido, headers in paginas:
            c = Mock(); r = c.getresponse.return_value
            r.status = 200; r.read1.side_effect = [contenido.encode(), b'']; r.getheaders.return_value = headers
            conexiones.append(c)
        with patch('backend.router_login.HTTPConnection', side_effect=conexiones):
            salida = iniciar_sesion('192.168.50.1', 'a b', 'contraseña', vigente)
        return salida, conexiones

    def test_protocolo_y_hash_utf8(self):
        (cookie, csrf), c = self.ejecutar()
        self.assertIn('session_id=artificial', cookie)
        self.assertEqual(csrf, 'nuevo')
        self.assertEqual(c[3].request.call_args.args[2], 'chk_sys_busy=')
        self.assertIn('login_uid=', c[3].request.call_args.args[3]['Cookie'])
        metodo, ruta, cuerpo, headers = c[4].request.call_args.args
        self.assertEqual(metodo, 'POST'); self.assertTrue(ruta.startswith('/data/login.json?'))
        for conexion in c[1:5]:
            query = conexion.request.call_args.args[1].split('?', 1)[1]
            self.assertTrue(query.startswith('_='))
            self.assertTrue(parse_qs(query)['_'][0].isdigit())
            self.assertEqual(parse_qs(query)['csrf_token'], ['inicial'])
        self.assertTrue(all(x.request.call_args.args[3]['Accept-Language'] == 'es-MX,es;q=0.9' for x in c))
        for conexion in c:
            for nombre, valor in cabeceras_router().items():
                self.assertEqual(conexion.request.call_args.args[3][nombre], valor)
        campos = parse_qs(cuerpo)
        self.assertEqual(campos['LoginName'], ['a%20b'])
        primero = hmac.new(b'$1$SERCOMM$', 'contraseña'.encode(), hashlib.sha256).hexdigest()
        esperado = hmac.new(b'reto', primero.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(campos['LoginPWD'], [esperado])
        self.assertNotIn('contraseña', cuerpo)
        self.assertTrue(all(x.close.called for x in c))

    def test_rechazos_sin_reintentar(self):
        for kwargs, estado in [({'resultado': '"3"'}, 'password_rechazada'),
                               ({'ocupado': '1'}, 'router_ocupado'),
                               ({'espera': '10'}, 'login_en_espera'),
                               ({'vigente': lambda: False}, 'contexto_cambiado')]:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ErrorRouter, estado):
                self.ejecutar(**kwargs)

    def test_credenciales_descartadas_tras_un_intento(self):
        red = {'estado': 'contexto_correcto', 'contexto': {'interfaz': 'en0',
            'ipv4_local': '192.168.50.2/24', 'gateway': '192.168.50.1', 'subred': '192.168.50.0/24'}}
        login = Mock(side_effect=ErrorRouter('autorizacion_rechazada'))
        m = MonitoreoRouter(consultar_contexto=lambda: red, login=login)
        m.ciclo()
        clave = m.autorizar({'usuario': 'prueba', 'password': 'artificial',
                            'confirmado': True, 'id_contexto': m.estado()['id_contexto']})
        self.assertNotIn('artificial', json.dumps(m.estado(clave)))
        m.ciclo(); m.ciclo()
        self.assertEqual(login.call_count, 1)
        self.assertIsNone(m._sesion)
        self.assertEqual(m.estado()['estado'], 'autorizacion_rechazada')
