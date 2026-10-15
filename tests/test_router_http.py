"""Regresión del parámetro dinámico requerido por user_data.json."""
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from backend.router_http import consulta_router
from backend.router import leer_router


class ConsultaTests(TestCase):
    def test_milisegundos_dinamicos_y_token_codificado(self):
        with patch('backend.router_http.time.time_ns', side_effect=[1234567890000000, 1234567895000000]):
            self.assertEqual(consulta_router('a+b'), '_=1234567890&csrf_token=a%2Bb')
            self.assertEqual(consulta_router('a+b'), '_=1234567895&csrf_token=a%2Bb')

    def test_todas_las_lecturas_incluyen_marca_de_tiempo(self):
        from backend.router import _RUTAS
        for ruta in _RUTAS:
            with self.subTest(ruta=ruta):
                c = Mock()
                r = c.getresponse.return_value
                r.status = 200
                r.read1.side_effect = [b'[]', b'']
                with patch('backend.router.HTTPConnection', return_value=c):
                    leer_router('192.168.50.1', ruta, 'session_id=artificial', 'token')
                query = urlsplit(c.request.call_args.args[1]).query
                self.assertTrue(query.startswith('_='))
                parametros = parse_qs(query)
                self.assertGreater(int(parametros['_'][0]), 0)
                self.assertEqual(parametros['csrf_token'], ['token'])
