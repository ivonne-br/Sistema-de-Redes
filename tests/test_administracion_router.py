"""Prueba permisos, cambios y resultados con adaptador/HTTP sintéticos.

Entradas: configuraciones artificiales, reloj y fallos controlados. Salidas:
aserciones sobre envío único, aislamiento y secretos; nunca contacta el router.
"""
from copy import deepcopy
from http.client import HTTPConnection
import json
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.administracion_router import AdministracionRouter, mismos_ajustes
from backend.router_adaptadores import Sercomm, PERFIL, identificar, solicitar
from backend.router import MonitoreoRouter
from backend.api import _ServidorLocal


def wifi():
    campos = {'wifi_network_onoff': '1', 'wifi_ssid': 'Red de prueba', 'wifi_password': 'ClaveOriginal1',
              'wifi_protection': 'wpa2', 'encryption_technique': 'aes', 'wifi_channel': 'auto', 'wifi_obss': '1',
              'wifi_broadcast_ssid': '1', 'block_wireless_bridging': '0', 'wireless_multicast': '1',
              'wifi_number_of_wifi_devices': '0'}
    return campos | {k + '_5g': v for k, v in campos.items()}


class Adaptador:
    def __init__(self):
        self.config = {'wifi': wifi(), 'bloqueo': {'activo': '0', 'lista': []}}
        self.envios = 0
        self.perder = False
        self.aplicar = True
        self.aceptar = True
        self.fallar_lectura = False

    def comprobar(self):
        return 'usuario_sintetico'

    def leer(self, tipo):
        if self.fallar_lectura:
            raise ValueError('Fallo simulado')
        return deepcopy(self.config[tipo])

    def escribir(self, tipo, esperado, usuario):
        self.envios += 1
        if self.aplicar:
            self.config[tipo] = deepcopy(esperado)
        if self.perder:
            raise OSError('Respuesta perdida')
        return self.aceptar


class Administracion(unittest.TestCase):
    def setUp(self):
        self.t = 0
        self.sesion = {'vence': 1800}
        self.servicio = AdministracionRouter(lambda: self.t)
        self.router = Adaptador()
        self.actuar('autorizar', {'confirmado': True})

    def actuar(self, accion, datos=None, propias=('02:00:00:00:00:02',)):
        return self.servicio.actuar(self.sesion, self.router, accion, datos or {}, propias)

    def preparar(self, operacion='nombre', **kw):
        return self.actuar('preparar', {'operacion': operacion, **(kw or {'banda': '2.4', 'valor': 'Nuevo nombre'})})

    def confirmar(self, plan):
        return self.actuar('confirmar', {'id': plan['id'], 'confirmado': True})

    def test_lectura_no_concede_administracion_y_caduca(self):
        self.actuar('finalizar')
        with self.assertRaises(PermissionError):
            self.preparar()
        with self.assertRaises(ValueError):
            self.actuar('autorizar', {'confirmado': False})
        self.actuar('autorizar', {'confirmado': True})
        self.t = 300
        with self.assertRaises(PermissionError):
            self.preparar()
        self.assertEqual(self.router.envios, 0)
        self.assertNotIn('administracion', self.sesion)

    def test_cambio_preserva_otra_banda_y_no_duplica(self):
        antes = deepcopy(self.router.config['wifi'])
        plan = self.preparar()
        self.assertEqual(self.router.envios, 0)
        r = self.confirmar(plan)
        self.assertEqual(r['estado'], 'verificado')
        antes['wifi_ssid'] = 'Nuevo nombre'
        self.assertEqual(self.router.config['wifi'], antes)
        self.assertEqual(self.confirmar(plan), r)
        self.assertEqual(self.router.envios, 1)

    def test_secreto_no_sale_en_consulta_plan_estado_ni_resultado(self):
        secreto = 'NuevaClavePrueba123'
        consulta = self.actuar('consultar')
        p = self.preparar('password', banda='5', valor=secreto)
        resultado = self.confirmar(p)
        for r in (consulta, p, resultado, self.servicio.estado(self.sesion)):
            self.assertNotIn(secreto, json.dumps(r))
            self.assertNotIn('ClaveOriginal1', json.dumps(r))
        self.assertEqual(self.router.config['wifi']['wifi_password_5g'], secreto)

    def test_confirmacion_caduca_cancela_y_no_admite_otro_id(self):
        p = self.preparar()
        with self.assertRaises(ValueError):
            self.confirmar({'id': 'otro'})
        self.t = 60
        with self.assertRaises(ValueError):
            self.confirmar(p)
        p = self.preparar()
        self.actuar('cancelar')
        with self.assertRaises(ValueError):
            self.confirmar(p)
        self.assertEqual(self.router.envios, 0)

    def test_cambio_externo_cancela_sin_sobrescribir(self):
        p = self.preparar()
        self.router.config['wifi']['wifi_channel_5g'] = '44'
        with self.assertRaisesRegex(ValueError, 'cambió'):
            self.confirmar(p)
        self.assertEqual(self.router.envios, 0)

    def test_respuesta_perdida_se_verifica_sin_reenviar(self):
        p = self.preparar()
        self.router.perder = True
        self.assertEqual(self.confirmar(p)['estado'], 'verificado')
        self.assertEqual(self.router.envios, 1)

    def test_incierto_y_aceptado_no_son_exito(self):
        for perder, estado in ((True, 'incierto'), (False, 'aceptado_sin_verificar')):
            with self.subTest(estado=estado):
                self.setUp()
                p = self.preparar()
                self.router.perder = perder
                self.router.aplicar = False
                self.assertEqual(self.confirmar(p)['estado'], estado)
                self.assertEqual(self.actuar('verificar')['estado'], estado)
                with self.assertRaises(ValueError):
                    self.preparar()
                self.assertEqual(self.router.envios, 1)

    def test_bloqueo_preserva_reglas_y_desbloquea_sin_equipo_presente(self):
        original = {'macfilter_name': 'Otro', 'macfilter_mac': '02:00:00:00:00:03'}
        self.router.config['bloqueo'] = {'activo': '1', 'lista': [original]}
        p = self.preparar('bloquear', mac='02:00:00:00:00:04')
        self.confirmar(p)
        self.assertIn(original, self.router.config['bloqueo']['lista'])
        p = self.preparar('desbloquear', mac='02:00:00:00:00:04')
        self.confirmar(p)
        self.assertEqual(self.router.config['bloqueo']['lista'], [original])

    def test_compara_reglas_sin_confundir_orden_o_mayusculas_con_otro_cambio(self):
        a = {'activo': '1', 'lista': [{'macfilter_name': 'A', 'macfilter_mac': '02:AB:00:00:00:01'},
                                    {'macfilter_name': 'B', 'macfilter_mac': '02:00:00:00:00:02'}]}
        b = deepcopy(a)
        b['lista'].reverse()
        b['lista'][1]['macfilter_mac'] = '02:ab:00:00:00:01'
        self.assertTrue(mismos_ajustes('bloqueo', a, b))
        b['activo'] = '0'
        self.assertFalse(mismos_ajustes('bloqueo', a, b))

    def test_no_bloquea_recolector_ni_activa_reglas_ajenas(self):
        with self.assertRaisesRegex(ValueError, 'computadora'):
            self.preparar('bloquear', mac='02:00:00:00:00:02')
        with self.assertRaises(ValueError):
            self.actuar('preparar', {'operacion': 'bloquear', 'mac': '02:00:00:00:00:04'}, propias=())
        self.router.config['bloqueo']['lista'] = [{'macfilter_name': 'Otro', 'macfilter_mac': '02:00:00:00:00:03'}]
        with self.assertRaisesRegex(ValueError, 'inactivas'):
            self.preparar('bloquear', mac='02:00:00:00:00:04')
        self.assertEqual(self.router.envios, 0)

    def test_valida_clave_nombre_y_mac(self):
        for datos in ({'operacion': 'password', 'banda': '5', 'valor': 'corta'},
                      {'operacion': 'nombre', 'banda': '5', 'valor': 'x' * 33},
                      {'operacion': 'bloquear', 'mac': 'FF:FF:FF:FF:FF:FF'}):
            with self.assertRaises(ValueError):
                self.actuar('preparar', datos)


class Contrato(unittest.TestCase):
    def test_perfil_y_permiso_del_router(self):
        respuestas = {'/data/statussupportstatus.json': json.dumps([PERFIL]),
                      '/data/user_data.json': '[{"username":"prueba","usermode":"admin"}]'}
        adaptador = Sercomm(lambda ruta: respuestas[ruta])
        self.assertEqual(adaptador.comprobar(), 'prueba')
        respuestas['/data/user_data.json'] = '[{"username":"prueba","usermode":"guest"}]'
        with self.assertRaises(PermissionError):
            adaptador.comprobar()
        respuestas['/data/statussupportstatus.json'] = '[{"sys_model_name":"otro"}]'
        with self.assertRaises(ValueError):
            adaptador.comprobar()

    def test_no_convierte_lista_permitidos_en_bloqueados(self):
        adaptador = Sercomm(lambda r: '[{"mac_filtering":"1","access_listed":"1","wifi_disabled":"0"}]' if r.endswith('filter.json') else '[]')
        with self.assertRaises(ValueError):
            adaptador.leer('bloqueo')

    def test_carga_completa_y_envio_del_contrato(self):
        llamadas = []
        def pedir(ruta, campos=None):
            llamadas.append((ruta, campos))
            if campos is None:
                return json.dumps([wifi() | {'wifi_now_channel': '6'}])
            return '0' if ruta.endswith('reset.json') else '1'
        a = Sercomm(pedir)
        config = a.leer('wifi')
        self.assertEqual(config, wifi())
        self.assertTrue(a.escribir('wifi', config, 'prueba'))
        self.assertEqual(llamadas[-1], ('/data/wifi_general.json', wifi()))
        self.assertEqual(llamadas[-2][1], {'loginUserChkLoginTimeout': 'prueba'})

    def test_identificacion_sin_credenciales_y_sin_inferir_proveedor(self):
        with patch('backend.router_adaptadores.solicitar', side_effect=[
            'Sercomm js/login.js var csrf_token="artificial";',
            '$.getJSON csrf_token statussupportwan_wan_statistics.json statussupportwan_ipv6wan_statistics.json']):
            self.assertEqual(identificar('192.168.50.1')['adaptador'], 'sercomm')
        with patch('backend.router_adaptadores.solicitar', return_value='Infinitum Telmex'):
            self.assertIsNone(identificar('192.168.50.1')['adaptador'])

    def test_transporte_no_admite_destino_externo_o_permiso_retirado(self):
        with patch('backend.router_adaptadores.HTTPConnection') as conexion:
            for gateway, ruta, vigente in [('8.8.8.8', '/login.html', lambda: True),
                                          ('192.168.50.1', '/login.html', lambda: False),
                                          ('192.168.50.1', '/reiniciar', lambda: True)]:
                with self.assertRaises((PermissionError, ValueError)):
                    solicitar(gateway, ruta, vigente=vigente)
            conexion.assert_not_called()

    def test_transporte_codifica_campos_y_no_sigue_redirecciones(self):
        conexion = Mock()
        respuesta = conexion.getresponse.return_value
        respuesta.status = 200
        respuesta.read1.side_effect = [b'1', b'']
        with patch('backend.router_adaptadores.HTTPConnection', return_value=conexion):
            self.assertEqual(solicitar('192.168.50.1', '/data/wifi_general.json',
                                      'session_id=artificial', 'csrf-artificial', {'wifi_ssid': 'Casa & juegos'}), '1')
        args = conexion.request.call_args.args
        self.assertEqual(args[0], 'POST')
        self.assertEqual(args[2], 'wifi_ssid=Casa%20%26%20juegos')
        respuesta.status = 302
        with patch('backend.router_adaptadores.HTTPConnection', return_value=conexion), self.assertRaises(ValueError):
            solicitar('192.168.50.1', '/login.html')
        self.assertEqual(conexion.request.call_count, 2)

    def test_ocupacion_no_envia_configuracion_y_clave_oculta_no_se_reenvia(self):
        pedir = Mock(return_value='1')
        self.assertFalse(Sercomm(pedir).escribir('wifi', wifi(), 'prueba'))
        pedir.assert_called_once_with('/data/reset.json', {'chk_sys_busy': 'prueba'})
        for valor in ('********', "Clave'NoCompatible"):
            config = wifi() | {'wifi_password': valor}
            with self.assertRaises(ValueError):
                Sercomm(lambda ruta: json.dumps([config])).leer('wifi')

    def test_expiracion_entre_peticiones_impide_envio_de_ajustes(self):
        tiempo = [0]
        red = {'estado': 'contexto_correcto', 'contexto': {'interfaz': 'en0', 'ipv4_local': '192.168.50.2/24',
                'subred': '192.168.50.0/24', 'gateway': '192.168.50.1'}}
        envios = []
        def transporte(gateway, ruta, cookie, csrf, campos, vigente):
            if campos is not None:
                envios.append(ruta)
                tiempo[0] = 301
                if not vigente():
                    raise PermissionError()
            if ruta.endswith('statussupportstatus.json'):
                return json.dumps([PERFIL])
            if ruta.endswith('user_data.json'):
                return '[{"username":"prueba","usermode":"admin"}]'
            return json.dumps([wifi()])
        m = MonitoreoRouter(consultar_contexto=lambda: red, reloj=lambda: tiempo[0],
                            identificar_router=lambda g: {'adaptador': 'sercomm'}, transporte_admin=transporte)
        m.ciclo()
        clave = m.autorizar({'id_contexto': m.estado()['id_contexto'], 'confirmado': True,
                            'cookie': 'session_id=artificial', 'csrf': 'artificial'})
        m._sesion['verificada'] = True
        m.administrar(clave, 'autorizar', {'confirmado': True})
        p = m.administrar(clave, 'preparar', {'operacion': 'nombre', 'banda': '2.4', 'valor': 'Nuevo'})
        m.administrar(clave, 'confirmar', {'id': p['id'], 'confirmado': True})
        self.assertEqual(envios, ['/data/reset.json'])
        self.assertFalse(m.estado(clave)['administracion']['autorizada'])

    def test_monitor_limpia_secretos_administrativos_sin_consultas_de_la_interfaz(self):
        m = MonitoreoRouter(reloj=lambda: 301)
        sesion = {'clave': 'artificial', 'vence': 1800,
                  'administracion': {'vence': 300, 'plan': {'despues': {'wifi_password': 'secreto'}}}}
        m._sesion = sesion
        m._expirar()
        self.assertNotIn('administracion', sesion)
        self.assertIs(m._sesion, sesion)

    def test_cambio_de_contexto_retira_admin_y_no_contacta_router(self):
        red = {'estado': 'contexto_correcto', 'contexto': {'interfaz': 'en0', 'ipv4_local': '192.168.50.2/24',
                'subred': '192.168.50.0/24', 'gateway': '192.168.50.1'}}
        transporte = Mock()
        m = MonitoreoRouter(consultar_contexto=lambda: red, identificar_router=lambda g: {'adaptador': 'sercomm'}, transporte_admin=transporte)
        m.ciclo()
        clave = m.autorizar({'id_contexto': m.estado()['id_contexto'], 'confirmado': True, 'cookie': 'session_id=artificial', 'csrf': 'artificial'})
        m._sesion['verificada'] = True
        m._sesion['administracion'] = {'vence': 999999999}
        red['estado'] = 'sin_contexto'
        with self.assertRaises(PermissionError):
            m.administrar(clave, 'confirmar', {'id': 'artificial', 'confirmado': True})
        transporte.assert_not_called()
        self.assertIsNone(m._sesion)


class APIAdministracion(unittest.TestCase):
    def test_origen_cabecera_sesion_y_cuerpo(self):
        monitor = Mock()
        monitor.administrar.return_value = {'autorizada': True}
        servidor = _ServidorLocal(('127.0.0.1', 0), SimpleNamespace(router=monitor))
        hilo = Thread(target=servidor.serve_forever); hilo.start()
        try:
            puerto = servidor.server_port
            def enviar(extra, cuerpo='{}'):
                c = HTTPConnection('127.0.0.1', puerto, timeout=3)
                c.request('POST', '/api/v1/router/administracion/consultar', cuerpo,
                          {'Content-Type': 'application/json', **extra})
                r = c.getresponse(); estado = r.status; r.read(); c.close(); return estado
            self.assertEqual(enviar({}), 400)
            self.assertEqual(enviar({'Origin': 'https://ajeno.example', 'X-Red-Accion': 'administrar-router'}), 403)
            cabeceras = {'Origin': f'http://127.0.0.1:{puerto}', 'X-Red-Accion': 'administrar-router', 'Cookie': 'red_router=permiso'}
            self.assertEqual(enviar(cabeceras, '{"sobrante":true}'), 400)
            monitor.administrar.assert_not_called()
            self.assertEqual(enviar(cabeceras), 200)
            monitor.administrar.assert_called_once_with('permiso', 'consultar', {})
            monitor.administrar.side_effect = PermissionError()
            self.assertEqual(enviar(cabeceras), 401)
        finally:
            servidor.shutdown(); hilo.join(); servidor.server_close()
