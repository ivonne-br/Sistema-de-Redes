"""Comprueba JSON Sercomm sintético y su entrada CLI sin conectarse al router.

Entradas: listas válidas, incompletas y ambiguas. Salidas: enteros exactos,
estados originales y errores sin secretos a través de backend.router_json.
"""

import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from backend.router_json import interpretar_json_router
from backend.__main__ import main


def equipo(**cambios):
    return dict(host_name='Consola de prueba', mac_address='02:00:00:00:00:01',
                ip_address='192.0.2.2', type='DHCP', interface='LAN4',
                status='601046', expires_in='0h 7m 42s', conn_type='Ethernet') | cambios


def wan(**cambios):
    return dict(interface='WAN_PRUEBA', description='pppoe',
                receivedbytes='118000000001', transmittedbytes='6000000001') | cambios


def leer(filas, fuente='dhcp-json'):
    return interpretar_json_router(json.dumps(filas), fuente)


class PruebasJSONRouter(unittest.TestCase):
    def test_estados_originales_y_desconocidos(self):
        for codigo, etiqueta in [('601045', 'Activo'), ('601046', 'Inactivo'), ('otro', None)]:
            with self.subTest(codigo=codigo):
                resultado = leer([equipo(status=codigo)])
                e = resultado['equipos'][0]
                self.assertEqual(e['codigo_estado_original'], codigo)
                self.assertEqual(e['estado_original'], etiqueta)
                self.assertIsNone(resultado['momento_captura'])
                self.assertIsNone(resultado['contexto_red'])
                self.assertEqual(resultado['recuento_filas_interpretadas']['estado_desconocido'],
                                 int(etiqueta is None))

    def test_bytes_exactos_y_familia_explicita(self):
        for fuente, familia in [('wan-ipv4-json', 'IPv4'), ('wan-ipv6-json', 'IPv6')]:
            r = leer([wan(receivedbytes=str(2**64 - 1), transmittedbytes='0')], fuente)
            self.assertEqual(r['wan'][0]['bytes_rx'], 2**64 - 1)
            self.assertEqual(r['wan'][0]['bytes_tx'], 0)
            self.assertEqual(r['wan'][0]['familia_ip'], familia)
            self.assertIsNone(r['wan'][0]['inicio_acumulacion'])

    def test_contadores_incompletos_o_invalidos_no_son_cero(self):
        for valor in [None, True, 12, '-1', '1.5', 'NaN', str(2**64), '9' * 5000]:
            with self.subTest(valor=str(valor)[:20]):
                r = leer([wan(receivedbytes=valor)], 'wan-ipv4-json')
                self.assertEqual(r['wan'], [])
                self.assertEqual(r['estado'], 'sin_datos_utilizables')

    def test_lista_vacia_difiere_de_error(self):
        self.assertEqual(leer([])['recuento_filas_interpretadas']['total'], 0)
        r = leer([equipo(ip_address='999.1.1.1')])
        self.assertIsNone(r['recuento_filas_interpretadas'])
        r = leer([equipo(), equipo(ip_address='invalida')])
        self.assertEqual(r['estado'], 'lectura_parcial')
        self.assertEqual(len(r['equipos']), 1)

    def test_no_propaga_campos_extra_ni_errores_privados(self):
        r = leer([equipo(cookie='SECRETO'), equipo(ip_address='SECRETO')])
        self.assertNotIn('SECRETO', json.dumps(r))

    def test_duplicados_ambiguos_se_excluyen(self):
        self.assertEqual(leer([equipo(), equipo(status='601045')])['equipos'], [])
        self.assertEqual(leer([wan(), wan(receivedbytes='1')], 'wan-ipv4-json')['wan'], [])

    def test_rechaza_documentos_ambiguos_y_no_listas(self):
        for texto in ['{}', 'null', '[] []', '[NaN]', '[{"status":"a","status":"b"}]',
                      '<html>SECRETO</html>', 'x' * 1_000_001]:
            with self.subTest(texto=texto[:30]), self.assertRaises(ValueError):
                interpretar_json_router(texto, 'dhcp-json')

    def test_cli_json_y_error_sin_revelar_entrada(self):
        salida = io.StringIO()
        with (patch('sys.argv', ['backend', 'interpretar-router', '--desde-stdin',
                                '--formato', 'wan-ipv4-json']),
              patch('sys.stdin', io.StringIO(json.dumps([wan()]))),
              patch('backend.__main__.APILocal') as api,
              redirect_stdout(salida)):
            main()
        api.assert_not_called()
        self.assertEqual(json.loads(salida.getvalue())['wan'][0]['bytes_rx'], 118000000001)
        errores = io.StringIO()
        with (patch('sys.argv', ['backend', 'interpretar-router', '--desde-stdin',
                                '--formato', 'dhcp-json']),
              patch('sys.stdin', io.StringIO('SECRETO')), redirect_stderr(errores),
              self.assertRaises(SystemExit) as salida_error):
            main()
        self.assertEqual(salida_error.exception.code, 2)
        self.assertNotIn('SECRETO', errores.getvalue())
