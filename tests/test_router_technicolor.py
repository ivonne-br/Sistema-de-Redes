"""Valida acceso Technicolor y TLS con respuestas artificiales, sin router real.

Entradas: contrato observado, certificados y reloj simulados. Salidas: sesión e
inventario; comprueba que no salen credenciales si cambia la confianza o la red.
"""
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from backend.router import MonitoreoRouter, ErrorRouter
from backend.router_technicolor import (
    LecturaTechnicolor, LOGIN, MENU, IDENTIDAD, HOSTS, PERFIL,
    derivar, inventario, solicitar,
)


def fila(**cambios):
    return {'hostname': 'Equipo de prueba', 'physaddress': '02:00:00:00:00:01',
            'ipaddress': '192.168.50.3', 'active': 'true',
            'layer1interface': 'Device.WiFi.SSID.1', 'addresssource': 'DHCP', **cambios}


def respuesta(data):
    return json.dumps({'error': 'ok', 'data': data})


class PruebasTechnicolor(unittest.TestCase):
    def setUp(self):
        self.llamadas = []
        self.ocupado = False
        self.salt = 'sal-sintetica'
        self.perfil = dict(PERFIL)
        self.adaptador = LecturaTechnicolor(self.transporte)

    def transporte(self, gateway, ruta, acceso, campos=None, vigente=lambda: True):
        self.assertTrue(vigente())
        self.llamadas.append((ruta, campos))
        if ruta == '/':
            return 'Technicolor'
        if ruta == '/views/login.html':
            return 'seeksalthash saltwebui sjcl.misc.pbkdf2(pass,salt,1000,128)'
        if ruta == '/js/app/app.js':
            return 'X-CSRF-TOKEN api/v1/'
        if ruta == LOGIN:
            if self.ocupado:
                return '{"error":"error","message":"MSG_LOGIN_150"}'
            if campos['password'] == 'seeksalthash':
                return json.dumps({'error': 'ok', 'salt': self.salt, 'saltwebui': 'otra-sal'})
            return '{"error":"ok"}'
        if ruta == IDENTIDAD:
            return respuesta(self.perfil)
        if ruta == MENU:
            return respuesta({'login': {'user': 'usuario-prueba'}})
        if ruta == HOSTS:
            return respuesta({'hostTbl': [fila()]})
        self.fail('Ruta no prevista')

    def test_login_deriva_dos_veces_sin_expulsar_sesion(self):
        # Vector obtenido de la biblioteca SJCL del panel con valores artificiales.
        self.assertEqual(derivar('prueba-sintetica', 'sal-sintetica'),
                         '447ae2c65a2033e53d0ed3fcc18f92e7')
        acceso = self.adaptador.autenticar('192.168.50.1', 'prueba', 'prueba-sintetica', lambda: True, huella='a'*64)
        envios = [c for r, c in self.llamadas if r == LOGIN]
        self.assertEqual(len(envios), 2)
        self.assertEqual(envios[0]['logout'], 'false')
        self.assertEqual(envios[1]['password'], derivar(derivar('prueba-sintetica', self.salt), 'otra-sal'))
        self.assertNotIn('password', acceso)
        self.adaptador.verificar('192.168.50.1', acceso)
        self.adaptador.validar_sesion('192.168.50.1', acceso)
        self.assertEqual(self.adaptador.leer('192.168.50.1', 'technicolor-hosts', acceso)['equipos'][0]['estado_original'], 'Activo')

    def test_router_ocupado_no_reintenta_ni_expulsa(self):
        self.ocupado = True
        with self.assertRaisesRegex(ErrorRouter, 'router_ocupado'):
            self.adaptador.autenticar('192.168.50.1', 'prueba', 'secreto', lambda: True, huella='a'*64)
        self.assertEqual(sum(r == LOGIN for r, _ in self.llamadas), 1)

    def test_otro_panel_no_recibe_usuario_ni_password(self):
        pedir = Mock(return_value='<html>Otro fabricante</html>')
        with self.assertRaisesRegex(ErrorRouter, 'no_compatible'):
            LecturaTechnicolor(pedir).autenticar('192.168.50.1', 'prueba', 'secreto', lambda: True, huella='a'*64)
        self.assertTrue(all(c.args[3] is None for c in pedir.call_args_list))

    def test_firmware_distinto_no_habilita_fuentes(self):
        self.perfil['SoftwareVersion'] = 'otra-version'
        with self.assertRaisesRegex(ErrorRouter, 'no_compatible'):
            self.adaptador.verificar('192.168.50.1', {})

    def test_inventario_no_inventa_contadores_y_rechaza_ambiguedad(self):
        r = inventario(respuesta({'hostTbl': [fila(active='false', ipaddress='')]}))
        self.assertEqual(r['wan'], [])
        self.assertIsNone(r['equipos'][0]['ipv4'])
        self.assertEqual(r['equipos'][0]['estado_original'], 'Inactivo')
        for filas in ([fila(), fila()], [fila(physaddress='no-es-mac')], [fila(ipaddress='invalida')]):
            with self.assertRaises(ValueError):
                inventario(respuesta({'hostTbl': filas}))
        with self.assertRaises(ErrorRouter):
            inventario('{"error":"ok","data":{},"data":{"hostTbl":[]}}')

    def test_monitor_exige_huella_y_publica_solo_inventario(self):
        red = {'estado': 'contexto_correcto', 'contexto': {'interfaz': 'prueba',
               'ipv4_local': '192.168.50.2/24', 'gateway': '192.168.50.1', 'subred': '192.168.50.0/24'}}
        m = MonitoreoRouter(consultar_contexto=lambda: red,
             identificar_router=lambda g: {'adaptador': 'technicolor', 'huella_sha256': 'a'*64},
             adaptadores={'technicolor': self.adaptador})
        m.ciclo()
        body = {'id_contexto': m.estado()['id_contexto'], 'confirmado': True, 'usuario': 'prueba', 'password': 'secreto'}
        for pin in (None, 'b'*64):
            with self.assertRaises(ValueError):
                m.autorizar({**body, 'huella_confirmada': pin})
        clave = m.autorizar({**body, 'huella_confirmada': 'a'*64})
        m.ciclo()
        r = m.estado(clave)
        self.assertEqual(r['estado'], 'lectura_correcta')
        self.assertFalse(r['capacidades']['trafico'])
        self.assertFalse(r['capacidades']['administracion'])
        self.assertIn('technicolor-hosts', r['tablas'])
        self.assertNotIn('secreto', json.dumps(r))
        with self.assertRaises(PermissionError):
            m.administrar(clave, 'autorizar', {})

    def test_pin_se_verifica_antes_de_cualquier_peticion(self):
        c = Mock()
        c.sock.getpeercert.return_value = b'certificado-de-prueba'
        with patch('backend.router_technicolor._conexion', return_value=c):
            with self.assertRaisesRegex(ErrorRouter, 'certificado_router_cambiado'):
                solicitar('192.168.50.1', LOGIN, {'huella': 'a'*64}, {'password': 'secreto'})
        c.request.assert_not_called()
        c.close.assert_called_once()

    def test_transporte_pin_valido_cookie_y_contexto(self):
        c, r = Mock(), Mock()
        c.sock.getpeercert.return_value = b'certificado-de-prueba'
        c.getresponse.return_value = r
        r.status = 200
        r.read1.side_effect = [b'{"error":"ok"}', b'']
        r.getheaders.return_value = [('Set-Cookie', 'auth=token-sintetico; Path=/')]
        acceso = {'huella': hashlib.sha256(b'certificado-de-prueba').hexdigest()}
        with patch('backend.router_technicolor._conexion', return_value=c):
            self.assertEqual(solicitar('192.168.50.1', MENU, acceso), '{"error":"ok"}')
        self.assertEqual(acceso['cookies'], {'auth': 'token-sintetico'})
        c.reset_mock()
        with patch('backend.router_technicolor._conexion', return_value=c):
            with self.assertRaisesRegex(ErrorRouter, 'contexto_cambiado'):
                solicitar('192.168.50.1', LOGIN, acceso, {'password': 'secreto'}, Mock(side_effect=[True, False]))
        c.request.assert_not_called()
        for ruta in ('/api/v1/system/reboot', 'https://externo.invalid/'):
            with self.assertRaises(ErrorRouter):
                solicitar('192.168.50.1', ruta, acceso)
        with self.assertRaises(ErrorRouter):
            solicitar('192.168.50.1', HOSTS, acceso, {'cambiar': 'algo'})

    def test_api_local_acepta_huella_y_mantiene_proteccion_origen(self):
        from http.client import HTTPConnection
        from threading import Thread
        from types import SimpleNamespace
        from backend.api import _ServidorLocal
        red = {'estado': 'contexto_correcto', 'contexto': {'interfaz': 'prueba',
               'ipv4_local': '192.168.50.2/24', 'gateway': '192.168.50.1', 'subred': '192.168.50.0/24'}}
        m = MonitoreoRouter(consultar_contexto=lambda: red,
             identificar_router=lambda g: {'adaptador': 'technicolor', 'huella_sha256': 'a'*64},
             adaptadores={'technicolor': self.adaptador})
        m.ciclo()
        servidor = _ServidorLocal(('127.0.0.1', 0), SimpleNamespace(router=m, logger=Mock()))
        hilo = Thread(target=servidor.serve_forever)
        hilo.start()
        body = {'id_contexto': m.estado()['id_contexto'], 'confirmado': True,
                'usuario': 'prueba', 'password': 'secreto', 'huella_confirmada': 'a'*64}
        def pedir(origen):
            c = HTTPConnection('127.0.0.1', servidor.server_port, timeout=2)
            try:
                c.request('POST', '/api/v1/router/sesion', json.dumps(body),
                          {'Content-Type': 'application/json', 'Origin': origen})
                r = c.getresponse()
                return r.status, json.loads(r.read())
            finally:
                c.close()
        try:
            self.assertEqual(pedir('https://otro.test')[0], 403)
            status, resultado = pedir(f'http://127.0.0.1:{servidor.server_port}')
            self.assertEqual(status, 201)
            m.ciclo()
            self.assertEqual(m.estado(resultado['clave'])['estado'], 'lectura_correcta')
        finally:
            servidor.shutdown()
            hilo.join(timeout=3)
            servidor.server_close()

    def test_rechazo_informa_presencia_de_cookies_sin_exponer_valores(self):
        c, r = Mock(), Mock()
        c.sock.getpeercert.return_value = b'certificado-de-prueba'
        c.getresponse.return_value = r
        r.status = 401
        r.getheaders.return_value = [('Set-Cookie', 'auth=secreto-remoto; Path=/')]
        acceso = {'huella': hashlib.sha256(b'certificado-de-prueba').hexdigest(),
                  'cookies': {'PHPSESSID': 'secreto-local'}}
        with patch('backend.router_technicolor._conexion', return_value=c):
            with self.assertRaises(ErrorRouter) as fallo:
                solicitar('192.168.50.1', IDENTIDAD, acceso)
        traza = fallo.exception.diagnostico
        self.assertEqual(traza[0]['http'], 401)
        self.assertTrue(traza[0]['envia_sesion'])
        self.assertFalse(traza[0]['envia_csrf'])
        self.assertTrue(traza[0]['recibe_csrf'])
        self.assertNotIn('secreto', json.dumps(traza))
        r.read1.assert_not_called()


    def test_menu_autenticado_precede_al_perfil_protegido(self):
        original = self.transporte
        autenticado = False
        menu_preparado = False

        def pedir(gateway, ruta, acceso, campos=None, vigente=lambda: True):
            nonlocal autenticado, menu_preparado
            if ruta == LOGIN and campos['password'] != 'seeksalthash':
                autenticado = True
            if ruta == MENU and autenticado:
                menu_preparado = True
            if ruta == IDENTIDAD and not menu_preparado:
                raise ErrorRouter('autorizacion_rechazada')
            return original(gateway, ruta, acceso, campos, vigente)

        adaptador = LecturaTechnicolor(pedir)
        acceso = adaptador.autenticar('192.168.50.1', 'prueba', 'secreto', lambda: True, huella='a'*64)
        adaptador.verificar('192.168.50.1', acceso)
        self.assertTrue(menu_preparado)
        self.assertEqual(sum(r == LOGIN for r, _ in self.llamadas), 2)

    def test_ipv4_usa_el_campo_que_muestra_el_panel(self):
        r = inventario(respuesta({'hostTbl': [fila(ipv41='192.168.50.9', ipaddress='')]}))
        self.assertEqual(r['equipos'][0]['ipv4'], '192.168.50.9')
        r = inventario(respuesta({'hostTbl': [fila(ipv41='')]}))
        self.assertIsNone(r['equipos'][0]['ipv4'])

    def test_respuesta_lenta_permitida_y_plazo_total_acotado(self):
        c, r = Mock(), Mock()
        c.sock.getpeercert.return_value = b'certificado-de-prueba'
        c.getresponse.return_value = r
        r.status = 200
        r.getheaders.return_value = []
        acceso = {'huella': hashlib.sha256(b'certificado-de-prueba').hexdigest()}
        reloj = [0]
        def leer(n):
            reloj[0] += 6
            return b'{}' if reloj[0] == 6 else b''
        r.read1.side_effect = leer
        with patch('backend.router_technicolor._conexion', return_value=c), patch(
                'backend.router_technicolor.tiempo_continuo', side_effect=lambda: reloj[0]):
            self.assertEqual(solicitar('192.168.50.1', HOSTS, acceso), '{}')
            reloj[0] = 0
            def lento(n):
                reloj[0] += 31
                return b'{}'
            r.read1.side_effect = lento
            with self.assertRaisesRegex(ErrorRouter, 'tiempo_agotado_router') as fallo:
                solicitar('192.168.50.1', HOSTS, acceso)
            self.assertEqual(fallo.exception.diagnostico[0]['paso'], 'equipos')
        c.close.assert_called()

    def test_monitor_conserva_muestra_y_sesion_al_fallar_y_se_recupera(self):
        red = {'estado': 'contexto_correcto', 'contexto': {'interfaz': 'prueba',
               'ipv4_local': '192.168.50.2/24', 'gateway': '192.168.50.1', 'subred': '192.168.50.0/24'}}
        reloj = [0]
        original = self.adaptador.leer
        def lento(*args):
            reloj[0] += 18.2
            return original(*args)
        self.adaptador.leer = lento
        m = MonitoreoRouter(consultar_contexto=lambda: red, reloj=lambda: reloj[0],
             identificar_router=lambda g: {'adaptador': 'technicolor', 'huella_sha256': 'a'*64},
             adaptadores={'technicolor': self.adaptador})
        m.ciclo()
        clave = m.autorizar({'id_contexto': m.estado()['id_contexto'], 'confirmado': True,
                            'usuario': 'prueba', 'password': 'secreto', 'huella_confirmada': 'a'*64})
        m.ciclo()
        self.assertEqual(m.estado(clave)['estado'], 'lectura_correcta')
        fecha = m.estado(clave)['tablas']['technicolor-hosts']['fecha']
        self.adaptador.leer = Mock(side_effect=ErrorRouter('tiempo_agotado_router'))
        reloj[0] += 5
        m.ciclo()
        estado = m.estado(clave)
        self.assertTrue(estado['autorizada'])
        self.assertEqual(estado['tablas']['technicolor-hosts']['fecha'], fecha)
        self.assertEqual(estado['diagnostico_acceso'][0]['resultado'], 'tiempo_agotado_router')
        self.adaptador.leer = original
        m.ciclo()
        self.assertEqual(m.estado(clave)['estado'], 'lectura_correcta')
        self.assertEqual(m.estado(clave)['diagnostico_acceso'], [])
        self.assertEqual(sum(r == LOGIN for r, _ in self.llamadas), 2)

    def test_espera_real_observada_antes_de_recibir_la_tabla(self):
        # Reproduce la espera del navegador sin dormir ni consultar el router.
        for demora in (16.9, 17.4, 18.2):
            with self.subTest(demora=demora):
                c, r = Mock(), Mock()
                c.sock.getpeercert.return_value = b'certificado-de-prueba'
                r.status = 200
                r.getheaders.return_value = []
                r.read1.side_effect = [respuesta({'hostTbl': [fila()]}).encode(), b'']
                reloj = [0]
                def cabeceras():
                    reloj[0] += demora
                    return r
                c.getresponse.side_effect = cabeceras
                acceso = {'huella': hashlib.sha256(b'certificado-de-prueba').hexdigest()}
                with patch('backend.router_technicolor._conexion', return_value=c), patch(
                        'backend.router_technicolor.tiempo_continuo', side_effect=lambda: reloj[0]):
                    tabla = inventario(solicitar('192.168.50.1', HOSTS, acceso))
                self.assertEqual(len(tabla['equipos']), 1)
                self.assertEqual(c.timeout, 30)
                self.assertAlmostEqual(c.sock.settimeout.call_args.args[0], 30 - demora)

    def test_menu_conserva_plazo_corto(self):
        c = Mock()
        c.sock.getpeercert.return_value = b'certificado-de-prueba'
        c.getresponse.side_effect = TimeoutError()
        acceso = {'huella': hashlib.sha256(b'certificado-de-prueba').hexdigest()}
        with patch('backend.router_technicolor._conexion', return_value=c), patch(
                'backend.router_technicolor.tiempo_continuo', return_value=0):
            with self.assertRaises(ErrorRouter) as fallo:
                solicitar('192.168.50.1', MENU, acceso)
        self.assertEqual(c.timeout, 15)
        self.assertEqual(fallo.exception.diagnostico[0]['limite_s'], 15)
