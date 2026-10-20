"""Valida recolección, tasas, contextos y permisos con router/reloj sintéticos.

Entradas: respuestas HTTP simuladas, cambios de red y fallos. Salidas: memoria
privada del monitor y rutas API; ninguna prueba contacta un router doméstico.
"""

from copy import deepcopy
from http.client import HTTPConnection
import json
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.router import MonitoreoRouter, ErrorRouter, leer_router
from backend.api import _ServidorLocal
from backend.router_http import cabeceras_router


def contexto():
    return {'estado': 'contexto_correcto', 'contexto': {
        'interfaz': 'en0', 'ipv4_local': '192.168.50.2/24',
        'subred': '192.168.50.0/24', 'gateway': '192.168.50.1'}}


class PruebasRouter(unittest.TestCase):
    def setUp(self):
        self.t = 0
        self.red = contexto()
        self.rx, self.tx = 1000, 500
        self.fallo = None
        self.llamadas = []
        self.monitor = MonitoreoRouter(identificar_router=lambda g: {'adaptador': 'sercomm', 'nombre': 'Simulado'}, consultar_contexto=lambda: deepcopy(self.red),
                                      leer=self.leer, reloj=lambda: self.t)
        self.monitor.ciclo()
        self.datos = {'cookie': 'session_id=secreto_sintetico', 'csrf': 'token_sintetico',
                      'id_contexto': self.monitor.estado()['id_contexto'], 'confirmado': True}
        self.clave = self.monitor.autorizar(self.datos)

    def leer(self, gateway, ruta, cookie, csrf):
        self.llamadas.append((gateway, ruta))
        if ruta.endswith('.js'):
            return '$.getJSON csrf_token statussupportwan_wan_statistics.json statussupportwan_ipv6wan_statistics.json'
        if ruta.endswith('user_data.json'):
            return '[{"username":"usuario_sintetico"}]'
        if self.fallo and self.fallo in ruta:
            raise ErrorRouter('error_lectura_router')
        if ruta.endswith('leases.json'):
            return json.dumps([{'host_name': 'Consola', 'mac_address': '02:00:00:00:00:01',
                'ip_address': '192.168.50.3', 'type': 'DHCP', 'interface': 'LAN4',
                'status': '601046', 'expires_in': '0m', 'conn_type': 'Ethernet'}])
        return json.dumps([{'interface': 'WAN_PRUEBA', 'description': 'pppoe',
                            'receivedbytes': str(self.rx), 'transmittedbytes': str(self.tx)}])

    def test_lectura_real_por_transporte_y_consulta_sin_recolectar(self):
        self.monitor.ciclo()
        n = len(self.llamadas)
        r = self.monitor.estado(self.clave)
        self.assertEqual(r['estado'], 'lectura_correcta')
        self.assertEqual(r['tablas']['dhcp-json']['equipos'][0]['estado_original'], 'Inactivo')
        self.assertEqual(len(self.llamadas), n)
        self.assertEqual(len(r['series']), 2)
        self.assertIsNone(r['series'][0]['bajada_mbps'])
        self.assertEqual(r['tablas']['wan-ipv4-json']['wan'][0]['bytes_rx'], '1000')
        self.assertTrue(all(g == '192.168.50.1' for g, _ in self.llamadas))
        for clave in (None, 'incorrecta', 'ñ'):
            self.assertEqual(self.monitor.estado(clave)['tablas'], {})
        self.assertNotIn('secreto_sintetico', json.dumps(r))
        self.assertNotIn('token_sintetico', json.dumps(r))

    def test_series_publican_edad_continua_solo_con_autorizacion(self):
        self.monitor.ciclo()
        self.t = 42
        lectura = self.monitor.estado(self.clave)
        self.assertEqual(lectura['series'][0]['antiguedad_s'], 42)
        self.assertNotIn('_t', lectura['series'][0])
        self.assertEqual(self.monitor.estado()['series'], [])

    def test_volumen_privado_con_ceros_huecos_y_reinicio(self):
        self.monitor.ciclo()
        r = self.monitor.estado(self.clave)['resumen_trafico'][0]
        self.assertIsNone(r['total_mb'])
        self.t = 5
        self.monitor.ciclo()
        r = self.monitor.estado(self.clave)['resumen_trafico'][0]
        self.assertEqual(r['total_mb'], 0)
        self.t = 10; self.rx += 2_000_000; self.tx += 1_000_000
        self.monitor.ciclo()
        estado = self.monitor.estado(self.clave)
        self.assertEqual(len(estado['resumen_trafico']), 2)
        r = estado['resumen_trafico'][0]
        self.assertEqual(r['total_mb'], 3)
        self.assertEqual(r['segundos_medidos'], 10)
        self.assertEqual(r['bytes_recibidos'], '2000000')
        self.assertEqual(estado['series'][-1]['bytes_enviados'], '1000000')
        self.t = 40; self.rx += 5_000_000
        self.monitor.ciclo()
        self.t = 45; self.rx = 0; self.tx = 0
        self.monitor.ciclo()
        r = self.monitor.estado(self.clave)['resumen_trafico'][0]
        self.assertEqual(r['total_mb'], 3)
        self.assertEqual(r['segundos_medidos'], 10)
        self.assertEqual(self.monitor.estado()['resumen_trafico'], [])

    def test_volumen_excluye_intervalo_que_cruza_inicio_y_no_redondea_bytes_grandes(self):
        from backend.router import resumir_trafico
        p = {'_t': 10, 'fecha': 'fecha', 'fuente': 'wan', 'familia_ip': 'IPv4',
             'interfaz': 'uno', 'intervalo_s': 5, 'motivo': 'intervalo_valido',
             'bytes_recibidos': 2**60 + 1, 'bytes_enviados': 2}
        r = resumir_trafico([p], 605)[0]
        self.assertEqual(r['bytes_recibidos'], str(2**60 + 1))
        r = resumir_trafico([p], 606)[0]
        self.assertIsNone(r['total_mb'])
        self.assertEqual(r['intervalos_excluidos'], 1)
        self.assertEqual(resumir_trafico([p], 610), [])

    def test_periodos_miden_solo_intervalos_completos_y_no_se_publican_al_invitado(self):
        self.monitor.ciclo()
        for t in range(5, 71, 5):
            self.t = t; self.rx += 1_000_000; self.tx += 500_000
            self.monitor.ciclo()
        n = len(self.llamadas)
        datos = self.monitor.estado(self.clave)
        corto = datos['trafico_por_periodo']['60'][0]
        largo = datos['trafico_por_periodo']['300'][0]
        self.assertEqual(corto['segundos_medidos'], 60)
        self.assertEqual(corto['segundos_sin_medicion'], 0)
        self.assertEqual(corto['total_mb'], 18)
        self.assertEqual(largo['total_mb'], 21)
        self.assertEqual(largo['segundos_sin_medicion'], 230)
        self.assertEqual(len(self.llamadas), n)
        self.assertEqual(self.monitor.estado()['trafico_por_periodo'], {})
        self.t = 100
        despues = self.monitor.estado(self.clave)['trafico_por_periodo']['60'][0]
        self.assertEqual(despues['segundos_medidos'], 30)
        self.assertEqual(despues['segundos_sin_medicion'], 30)
        self.assertEqual(despues['ultima_fecha'], corto['ultima_fecha'])
        self.red['contexto']['gateway'] = '192.168.50.254'
        self.monitor.ciclo()
        self.assertEqual(self.monitor.estado(self.clave)['trafico_por_periodo'], {})

    def test_tasas_reset_pausa_y_familias_separadas(self):
        self.monitor.ciclo()
        self.t = 5; self.rx += 10_000_000; self.tx += 1_000_000
        self.monitor.ciclo()
        p = self.monitor.estado(self.clave)['series'][-1]
        self.assertEqual(p['bajada_mbps'], 16)
        self.assertEqual(p['subida_mbps'], 1.6)
        self.assertEqual(p['familia_ip'], 'IPv6')
        self.t = 10; self.rx = 0
        self.monitor.ciclo()
        self.assertIsNone(self.monitor.estado(self.clave)['series'][-1]['bajada_mbps'])
        self.t = 100; self.rx = 999
        self.monitor.ciclo()
        self.assertIsNone(self.monitor.estado(self.clave)['series'][-1]['subida_mbps'])

    def test_fallo_conserva_fecha_y_recuperacion_no_puentea_hueco(self):
        self.monitor.ciclo()
        fecha = self.monitor.estado(self.clave)['tablas']['wan-ipv4-json']['fecha']
        self.t = 5; self.fallo = '_wan_statistics'
        self.monitor.ciclo()
        r = self.monitor.estado(self.clave)
        self.assertEqual(r['estado'], 'error_fuente')
        self.assertEqual(r['tablas']['wan-ipv4-json']['fecha'], fecha)
        self.assertEqual(r['tablas']['wan-ipv4-json']['ultimo_intento'], 'error')
        self.t = 10; self.fallo = None
        self.monitor.ciclo()
        self.assertIsNone(self.monitor.estado(self.clave)['series'][-2]['bajada_mbps'])

    def test_cambio_red_retira_datos_y_no_envia_sesion_a_otro_gateway(self):
        self.monitor.ciclo()
        n = len(self.llamadas)
        anterior = self.monitor.estado()['id_contexto']
        self.red['contexto']['gateway'] = '192.168.50.254'
        self.monitor.ciclo()
        self.assertEqual(len(self.llamadas), n)
        self.assertEqual(self.monitor.estado(self.clave)['tablas'], {})
        self.assertNotEqual(self.monitor.estado()['id_contexto'], anterior)
        with self.assertRaises(ValueError):
            self.monitor.autorizar(self.datos)

    def test_cambio_durante_lectura_descarta_respuesta(self):
        original = self.monitor._leer
        def cambiar(*args):
            r = original(*args)
            if args[1].endswith('leases.json'):
                self.red = {'estado': 'sin_ruta'}
            return r
        self.monitor._leer = cambiar
        self.monitor.ciclo()
        self.assertEqual(self.monitor.estado(self.clave)['tablas'], {})
        self.assertEqual(len(self.llamadas), 3)

    def test_sesion_caduca_y_revocacion_impide_consultar(self):
        self.monitor.ciclo()
        self.t = 1501
        self.assertTrue(self.monitor.estado(self.clave)['autorizada'])
        self.t = 1800
        self.assertFalse(self.monitor.estado(self.clave)['autorizada'])
        self.assertEqual(self.monitor.estado()['estado'], 'autorizacion_expirada')
        self.clave = self.monitor.autorizar(self.datos)
        with self.assertRaises(PermissionError):
            self.monitor.revocar('otra')
        self.monitor.revocar(self.clave)
        self.assertEqual(self.monitor.estado(self.clave)['series'], [])

    def test_no_confunde_login_vacio_con_cero_equipos(self):
        self.monitor._leer = lambda *args: self.leer(*args) if args[1].endswith('.js') else '[]'
        self.monitor.ciclo()
        self.assertEqual(self.monitor.estado()['estado'], 'autorizacion_rechazada')
        self.assertEqual(self.monitor.estado(self.clave)['tablas'], {})

    def test_retencion_y_copia_independiente(self):
        self.monitor.ciclo()
        r = self.monitor.estado(self.clave)
        r['tablas'].clear()
        self.assertTrue(self.monitor.estado(self.clave)['tablas'])
        self.t = 601
        self.assertEqual(self.monitor.estado(self.clave)['tablas'], {})
        self.assertEqual(self.monitor.estado(self.clave)['series'], [])

    def test_fallo_validacion_conserva_sesion_sin_repetir_login(self):
        self.monitor.ciclo()
        original = self.monitor._leer
        def fallar(gateway, ruta, cookie, csrf):
            if ruta == '/data/user_data.json':
                raise ErrorRouter('http_invalido_router')
            return original(gateway, ruta, cookie, csrf)
        self.monitor._leer = fallar
        self.t = 5
        self.monitor.ciclo()
        estado = self.monitor.estado(self.clave)
        self.assertTrue(estado['autorizada'])
        self.assertEqual(estado['etapa_error'], 'validacion_sesion')
        self.assertEqual(estado['tablas']['dhcp-json']['ultimo_intento'], 'error')
        self.monitor._leer = original
        self.t = 10
        self.monitor.ciclo()
        estado = self.monitor.estado(self.clave)
        self.assertEqual(estado['estado'], 'lectura_correcta')
        self.assertIsNone(estado['etapa_error'])
        self.assertIsNone(estado['series'][-1]['bajada_mbps'])

    def test_http_no_redirecciona_y_solo_admite_rutas_de_lectura(self):
        with patch('backend.router.HTTPConnection') as fabrica:
            fabrica.return_value.getresponse.return_value.status = 302
            with self.assertRaisesRegex(ErrorRouter, 'autorizacion_rechazada'):
                leer_router('192.168.50.1', '/data/user_data.json', 'session_id=x', 'csrf')
            self.assertEqual(fabrica.return_value.request.call_args.args[0], 'GET')
            headers = fabrica.return_value.request.call_args.kwargs['headers']
            for nombre, valor in cabeceras_router().items():
                self.assertEqual(headers[nombre], valor)
            fabrica.return_value.close.assert_called_once()
            fabrica.reset_mock()
            for destino, ruta in [('8.8.8.8', '/data/user_data.json'), ('192.168.50.1', '/reset')]:
                with self.assertRaises(ErrorRouter):
                    leer_router(destino, ruta, 'x', 'x')
            fabrica.assert_not_called()

    def test_api_privada_origen_autorizacion_y_retiro(self):
        self.monitor.revocar(self.clave)
        app = SimpleNamespace(router=self.monitor, logger=Mock(),
                              estado_web=lambda: {'estado': 'desactivada'},
                              estado_conectividad=lambda: {'estado': 'desactivada'})
        servidor = _ServidorLocal(('127.0.0.1', 0), app)
        hilo = Thread(target=servidor.serve_forever)
        hilo.start()
        def pedir(metodo='GET', ruta='/api/v1/router', datos=None, headers=None):
            c = HTTPConnection('127.0.0.1', servidor.server_port, timeout=2)
            try:
                cabeceras = {'Content-Type': 'application/json'} | (headers or {})
                c.request(metodo, ruta, body=json.dumps(datos) if datos is not None else None, headers=cabeceras)
                r = c.getresponse()
                pedir.cookie = r.getheader('Set-Cookie')
                return r.status, json.loads(r.read())
            finally:
                c.close()
        try:
            self.assertEqual(pedir('POST', '/api/v1/router/sesion', self.datos,
                                   {'Origin': 'https://externo.test'})[0], 403)
            status, cuerpo = pedir('POST', '/api/v1/router/sesion', self.datos)
            self.assertEqual(status, 201)
            clave = cuerpo['clave']
            self.monitor.ciclo()
            self.assertEqual(pedir()[1]['datos']['tablas'], {})
            autorizado = {'X-Router-Authorization': clave}
            self.assertTrue(pedir(headers=autorizado)[1]['datos']['tablas'])
            self.assertEqual(pedir('DELETE', '/api/v1/router/sesion')[0], 401)
            self.assertEqual(pedir('DELETE', '/api/v1/router/sesion', headers=autorizado)[0], 200)
            self.assertEqual(pedir(headers=autorizado)[1]['datos']['tablas'], {})
            status, cuerpo = pedir('POST', '/api/v1/router/sesion', self.datos,
                                   {'X-Router-Session': 'cookie'})
            self.assertEqual(status, 201)
            self.assertEqual(cuerpo, {'version_esquema': 1, 'sesion': 'cookie'})
            cookie = pedir.cookie
            self.assertIn('HttpOnly', cookie)
            self.assertIn('SameSite=Strict', cookie)
            self.assertIn('Path=/api/v1/router', cookie)
            self.assertNotIn('Max-Age', cookie)
            self.assertNotIn('Expires', cookie)
            cabecera_cookie = {'Cookie': cookie.split(';')[0]}
            self.monitor.ciclo()
            # Otra petición, sin clave JavaScript: representa recargar la página.
            self.assertTrue(pedir(headers=cabecera_cookie)[1]['datos']['tablas'])
            self.assertEqual(pedir()[1]['datos']['tablas'], {})
            self.assertEqual(pedir(headers={**cabecera_cookie, 'Origin': 'https://externo.test'})[0], 403)
            self.assertEqual(pedir('DELETE', '/api/v1/router/sesion', headers={**cabecera_cookie, 'Origin': 'https://externo.test'})[0], 403)
            self.assertFalse(pedir(headers={'Cookie': cabecera_cookie['Cookie'] + '; ' + cabecera_cookie['Cookie']})[1]['datos']['autorizada'])
            self.assertEqual(pedir('DELETE', '/api/v1/router/sesion', headers=cabecera_cookie)[0], 200)
            self.assertIn('Max-Age=0', pedir.cookie)
            self.assertFalse(pedir(headers=cabecera_cookie)[1]['datos']['autorizada'])
        finally:
            servidor.shutdown(); hilo.join(2); servidor.server_close()


class PruebasMultiplesAdaptadores(unittest.TestCase):
    """Entradas sintéticas de otro contrato; salida común sin usar rutas Sercomm."""

    def test_lectura_independiente_y_cambio_de_red_retira_acceso(self):
        class AdaptadorPrueba:
            fuentes = ('clientes-prueba',)
            fuente_inventario = 'clientes-prueba'

            def autenticar(self, gateway, usuario, password, vigente):
                self.gateway = gateway
                assert vigente()
                return {'token_prueba': 'secreto-sintetico'}

            def verificar(self, gateway, acceso):
                assert acceso == {'token_prueba': 'secreto-sintetico'}

            validar_sesion = verificar

            def leer(self, gateway, fuente, acceso):
                self.verificar(gateway, acceso)
                return {'estado': 'lectura_correcta', 'equipos': [],
                        'recuento_filas_interpretadas': 0, 'wan': []}

        red = contexto()
        adaptador = AdaptadorPrueba()
        transporte_sercomm = Mock(side_effect=AssertionError('No usar Sercomm'))
        m = MonitoreoRouter(consultar_contexto=lambda: red, leer=transporte_sercomm,
                            login=transporte_sercomm, transporte_admin=transporte_sercomm,
                            identificar_router=lambda g: {'adaptador': 'prueba'},
                            adaptadores={'prueba': adaptador})
        m.ciclo()
        clave = m.autorizar({'id_contexto': m.estado()['id_contexto'], 'confirmado': True,
                            'usuario': 'prueba', 'password': 'solo-prueba'})
        m.ciclo()
        salida = m.estado(clave)
        self.assertEqual(salida['estado'], 'lectura_correcta')
        self.assertEqual(salida['capacidades'], {'lectura': True, 'administracion': False,
                                                'fuente_inventario': 'clientes-prueba', 'trafico': False})
        self.assertIn('clientes-prueba', salida['tablas'])
        self.assertNotIn('secreto-sintetico', json.dumps(salida))
        self.assertNotIn('password', m._sesion)
        with self.assertRaises(PermissionError):
            m.administrar(clave, 'autorizar', {})
        red['contexto']['gateway'] = '192.168.50.254'
        m.ciclo()
        self.assertFalse(m.estado(clave)['autorizada'])
        self.assertEqual(m.estado(clave)['tablas'], {})
        transporte_sercomm.assert_not_called()

    def test_identidad_sin_adaptador_registrado_no_recibe_credenciales(self):
        login = Mock()
        m = MonitoreoRouter(consultar_contexto=contexto, login=login,
                            identificar_router=lambda g: {'adaptador': 'sin-integracion'})
        m.ciclo()
        self.assertFalse(m.estado()['capacidades']['lectura'])
        with self.assertRaises(ValueError):
            m.autorizar({'id_contexto': m.estado()['id_contexto'], 'confirmado': True,
                         'usuario': 'prueba', 'password': 'solo-prueba'})
        login.assert_not_called()

    def test_identificacion_publica_no_confunde_proveedor_modelo_y_acceso(self):
        from backend.router_adaptadores import identificar
        with patch('backend.router_adaptadores.solicitar', side_effect=[
                ValueError(), '<title>Technicolor CGA4233TLV2</title>']) as pedir:
            identidad = identificar('192.168.50.1')
            self.assertEqual(identidad['estado'], 'lectura_pendiente')
            self.assertIsNone(identidad['adaptador'])
            self.assertEqual(pedir.call_args.args, ('192.168.50.1', '/'))
        for texto in ('izzi', 'Totalplay', 'Technicolor', 'CGA4233TLV2'):
            with patch('backend.router_adaptadores.solicitar', return_value=texto):
                self.assertEqual(identificar('192.168.50.1')['estado'], 'no_reconocido')
        with patch('backend.router_adaptadores.solicitar', side_effect=ValueError()):
            self.assertEqual(identificar('192.168.50.1')['estado'], 'sin_respuesta')
