"""El diagnóstico revela estados, nunca contenido de sesión."""
from http.client import BadStatusLine
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from backend.router_diagnostico import consultar, variantes


class DiagnosticoTests(TestCase):
    def test_variantes_controladas(self):
        opciones = variantes('login_uid=x; session_id=artificial', 'token-artificial', '192.168.50.1')
        self.assertEqual(len(opciones), 5)
        self.assertNotIn('_', parse_qs(opciones[0][1]))
        self.assertIn('_', parse_qs(opciones[1][1]))
        self.assertTrue(opciones[2][2]['Cookie'].startswith('session_id='))
        self.assertNotIn('X-Requested-With', opciones[3][2])

    def test_salida_no_revela_contenido(self):
        c = Mock()
        r = c.getresponse.return_value
        r.status = 200
        r.read1.side_effect = [b'[{"username":"privado","token":"secreto"}]', b'']
        with patch('backend.router_diagnostico.HTTPConnection', return_value=c):
            self.assertEqual(consultar('192.168.50.1', 'csrf_token=artificial', {}),
                             'HTTP 200; sesión validada')
        c.close.assert_called_once()

    def test_error_remoto_solo_muestra_codigo(self):
        c = Mock()
        c.getresponse.side_effect = BadStatusLine('UNKNOWN 400 secreto')
        with patch('backend.router_diagnostico.HTTPConnection', return_value=c):
            self.assertEqual(consultar('192.168.50.1', '', {}), 'HTTP malformado; código 400')
