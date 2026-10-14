"""Sondas y contexto simulados prueban DNS/HTTPS, plazos, recuentos e historial acotado por contexto sin servicios públicos.

También comprueba el trabajador real con localhost; la API se prueba en test_api.
"""
import json
import socket
import ssl
import subprocess
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from backend.configuracion import ConfiguracionBackend, interpretar_configuracion
from backend.web import MonitoreoWeb, comprobar, ejecutar_comprobacion
from test_coordinador import contexto, OTRO


def correcto():
    return {'estado': 'correcto', 'duracion_ms': 0, 'direcciones': ['192.0.2.3'], 'codigo_http': None}


class PruebasWeb(unittest.TestCase):
    def crear(self):
        self.tiempo = 0
        self.fuente = Mock(return_value=contexto())
        self.sonda = Mock(side_effect=lambda *args: correcto())
        return MonitoreoWeb(consultar_contexto=self.fuente, sonda=self.sonda, reloj=lambda: self.tiempo)

    def test_dns_sistema_deduplica_ipv4_y_no_inventa_servidor_dns(self):
        fila = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.3', 0))
        with patch('backend.web.socket.getaddrinfo', return_value=[fila, fila]) as resolver:
            dato = comprobar('dns', 'prueba.test', 2)
        self.assertEqual(dato['estado'], 'correcto')
        self.assertEqual(dato['direcciones'], ['192.0.2.3'])
        resolver.assert_called_once_with('prueba.test', None, socket.AF_INET, socket.SOCK_STREAM)

    def test_dns_error_y_lista_vacia(self):
        with patch('backend.web.socket.getaddrinfo', side_effect=socket.gaierror()):
            self.assertEqual(comprobar('dns', 'prueba.test', 1)['estado'], 'error_resolucion')
        with patch('backend.web.socket.getaddrinfo', return_value=[]):
            self.assertEqual(comprobar('dns', 'prueba.test', 1)['estado'], 'sin_direcciones')

    def test_https_certificado_validado_no_redirige_ni_descarga_cuerpo(self):
        for codigo, estado in ((204, 'correcto'), (302, 'http_inesperado'), (503, 'http_inesperado')):
            with patch('backend.web.HTTPSConnection') as fabrica:
                conexion = fabrica.return_value
                conexion.getresponse.return_value.status = codigo
                dato = comprobar('https', 'https://prueba.test/control', 2)
                self.assertEqual(dato['estado'], estado)
                self.assertEqual(dato['codigo_http'], codigo)
                conexion.request.assert_called_once()
                conexion.getresponse.return_value.read.assert_not_called()
                conexion.close.assert_called_once()
                tls = fabrica.call_args.kwargs['context']
                self.assertTrue(tls.check_hostname)
                self.assertEqual(tls.verify_mode, ssl.CERT_REQUIRED)

    def test_https_distingue_errores_y_cierra(self):
        for error, estado in ((socket.gaierror(), 'error_resolucion'),
                              (ssl.SSLCertVerificationError(), 'certificado_invalido'),
                              (ssl.SSLError(), 'error_tls'), (TimeoutError(), 'tiempo_agotado'),
                              (ConnectionRefusedError(), 'error_conexion')):
            with patch('backend.web.HTTPSConnection') as fabrica:
                fabrica.return_value.request.side_effect = error
                dato = comprobar('https', 'https://prueba.test/', 1)
                self.assertEqual(dato['estado'], estado)
                self.assertIsNone(dato['codigo_http'])
                fabrica.return_value.close.assert_called_once()

    def test_proceso_limite_y_fallo_no_son_cero_ms(self):
        for error, estado in ((subprocess.TimeoutExpired('prueba', 1), 'tiempo_agotado'),
                              (OSError(), 'error_medicion')):
            with patch('backend.web.subprocess.run', side_effect=error) as ejecutar:
                dato = ejecutar_comprobacion('dns', 'prueba.test', 1)
                self.assertEqual(dato['estado'], estado)
                self.assertIsNone(dato['duracion_ms'])
                self.assertEqual(ejecutar.call_args.kwargs['timeout'], 1)
        with patch('backend.web.subprocess.run', return_value=Mock(stdout='{}')):
            self.assertEqual(ejecutar_comprobacion('dns', 'prueba.test', 1)['estado'], 'error_medicion')

    def test_trabajador_real_resuelve_localhost_sin_destino_publico(self):
        dato = ejecutar_comprobacion('dns', 'localhost', 3)
        self.assertEqual(dato['estado'], 'correcto')
        self.assertIn('127.0.0.1', dato['direcciones'])

    def test_consultas_sin_sondas_copias_vigencia_retencion(self):
        m = self.crear()
        m.ciclo()
        self.assertEqual(self.sonda.call_count, 2)
        dato = m.estado()
        self.assertEqual({r['tipo'] for r in dato['resultados']}, {'dns', 'https'})
        dato['resultados'][0]['estado'] = 'cambiado'
        self.assertEqual(m.estado()['resultados'][0]['estado'], 'correcto')
        self.tiempo = 121
        self.assertEqual(m.estado()['resultados'][0]['vigencia'], 'desactualizado')
        self.tiempo = 600
        self.assertEqual(m.estado()['resultados'], [])
        self.assertEqual(self.sonda.call_count, 2)

    def test_fallo_dns_no_impide_https_y_recuperacion_reemplaza_resultados(self):
        m = self.crear()
        m.ciclo()
        self.tiempo = 10
        def medir(tipo, *args):
            if tipo == 'dns':
                raise OSError()
            return correcto()
        self.sonda.side_effect = medir
        m.ciclo()
        self.tiempo = 12
        dns, https = m.estado()['resultados']
        self.assertEqual(dns['estado'], 'error_medicion')
        self.assertEqual(dns['antiguedad_s'], 2)
        self.assertIsNone(dns['duracion_ms'])
        self.assertEqual(https['estado'], 'correcto')
        self.sonda.side_effect = lambda *args: correcto()
        m.ciclo()
        self.assertEqual(m.estado()['resultados'][0]['estado'], 'correcto')
        self.assertEqual(len(m.estado()['resultados']), 2)

    def test_contexto_cambiado_descarta_y_a_b_a_recibe_nuevo_id(self):
        m = self.crear()
        m.ciclo()
        a = m.estado()['id_contexto']
        self.fuente.side_effect = [contexto(), contexto(OTRO)]
        m.ciclo()
        self.assertEqual(m.estado()['estado'], 'sin_contexto')
        self.assertEqual(m.estado()['resultados'], [])
        self.fuente.side_effect = None
        m.ciclo()
        self.assertNotEqual(m.estado()['id_contexto'], a)
        self.fuente.return_value = {'estado': 'sin_ruta'}
        m.ciclo()
        self.assertEqual(m.estado()['resultados'], [])

    def test_no_solapa_y_parada_impide_otro_ciclo(self):
        m = self.crear()
        entro, salir = Event(), Event()
        def medir(*args):
            entro.set()
            salir.wait(2)
            return correcto()
        self.sonda.side_effect = medir
        hilo = Thread(target=m.ciclo)
        hilo.start()
        try:
            self.assertTrue(entro.wait(1))
            with self.assertRaises(RuntimeError):
                m.ciclo()
            m.detener()
        finally:
            salir.set()
            hilo.join(3)
        self.assertFalse(hilo.is_alive())
        m.ciclo()
        self.assertEqual(self.sonda.call_count, 2)
        self.assertEqual(m.estado()['estado'], 'detenido')

    def test_configuracion_destino_propio_y_rechazos(self):
        config = interpretar_configuracion(json.dumps({'nombre_dns': 'sonda.casa.test',
            'url_https': 'https://sonda.casa.test:8443/control', 'codigo_https_esperado': 200}))
        self.assertEqual(config.codigo_https_esperado, 200)
        for campo, valores in {
            'nombre_dns': ['', '1.1.1.1', '-mal.test', 'dos palabras', None],
            'url_https': ['http://prueba.test', 'https://u:p@prueba.test', 'https://prueba.test/#a',
                          'https://prueba.test:99999', 'https://prueba.test/\n', None],
            'intervalo_web_s': [True, 0, float('nan')], 'limite_web_s': [0, 31],
            'web_activa': [1], 'codigo_https_esperado': [True, 302],
        }.items():
            for valor in valores:
                with self.subTest(campo=campo, valor=valor), self.assertRaises((ValueError, TypeError)):
                    ConfiguracionBackend(**{campo: valor})

    def test_historial_estable_fallo_recuperacion_copias_y_fechas(self):
        m = self.crear()
        m.ciclo()
        primera = m.estado()['historial'][0]
        self.tiempo = 10
        self.sonda.side_effect = OSError()
        m.ciclo()
        self.tiempo = 20
        self.sonda.side_effect = lambda *args: correcto()
        m.ciclo()
        dato = m.estado()
        self.assertEqual([s['resultados'][0]['estado'] for s in dato['historial']],
                         ['correcto', 'error_medicion', 'correcto'])
        self.assertEqual(dato['historial'][0]['id_serie'], primera['id_serie'])
        self.assertEqual(dato['historial'][0]['resultados'][0]['fin'], primera['resultados'][0]['fin'])
        self.assertEqual(dato['historial'][0]['resultados'][0]['antiguedad_s'], 20)
        self.assertNotIn('_instante', repr(dato))
        dato['historial'][0]['resultados'][0]['estado'] = 'alterado'
        self.assertEqual(m.estado()['historial'][0]['resultados'][0]['estado'], 'correcto')
        self.assertEqual(self.sonda.call_count, 6)

    def test_historial_capacidad_retencion_contexto_y_reinicio(self):
        from backend.configuracion import ConfiguracionMemoria
        self.tiempo = 0
        fuente = Mock(return_value=contexto())
        config = ConfiguracionBackend(memoria=ConfiguracionMemoria(capacidad=2, retencion_s=60))
        m = MonitoreoWeb(config, consultar_contexto=fuente, sonda=lambda *args: correcto(), reloj=lambda: self.tiempo)
        for instante in (0, 10, 20):
            self.tiempo = instante
            m.ciclo()
        anterior = m.estado()
        self.assertEqual(len(anterior['historial']), 2)
        self.assertEqual(anterior['historial'][0]['antiguedad_s'], 10)
        self.tiempo = 70
        self.assertEqual(len(m.estado()['historial']), 1)
        fuente.return_value = contexto(OTRO)
        m.ciclo()
        self.assertEqual(len(m.estado()['historial']), 1)
        fuente.return_value = contexto()
        m.ciclo()
        self.assertEqual(len(m.estado()['historial']), 1)
        self.assertNotEqual(m.estado()['id_contexto'], anterior['id_contexto'])
        fuente.return_value = {'estado': 'sin_ruta'}
        m.ciclo()
        self.assertEqual(m.estado()['historial'], [])
        fuente.return_value = contexto()
        m.ciclo()
        self.assertEqual(len(m.estado()['historial']), 1)
        self.tiempo = 130
        self.assertEqual(m.estado()['historial'], [])
        self.assertEqual(MonitoreoWeb(config).estado()['historial'], [])

    def test_resumen_distingue_estados_y_recuperacion_por_destino(self):
        from backend.web import resumir_ventana
        def fila(tipo, destino, estado, fin):
            return {'tipo': tipo, 'destino': destino, 'estado': estado, 'fin': fin}
        historial = [
            {'resultados': [fila('dns', 'uno.test', 'tiempo_agotado', 'uno'),
                            fila('https', 'https://uno.test', 'certificado_invalido', 'uno')]},
            {'resultados': [fila('dns', 'uno.test', 'correcto', 'dos'),
                            fila('dns', 'otro.test', 'error_resolucion', 'dos')]},
        ]
        dns, https, otro = resumir_ventana(historial)
        self.assertEqual((dns['intentos'], dns['correctos'], dns['no_correctos']), (2, 1, 1))
        self.assertEqual(dns['por_estado'], {'tiempo_agotado': 1, 'correcto': 1})
        self.assertTrue(dns['correcto_posterior'])
        self.assertFalse(https['correcto_posterior'])
        self.assertFalse(otro['correcto_posterior'])
        self.assertEqual(resumir_ventana([]), [])

    def test_resumen_no_conserva_fallo_expirado_ni_contexto_anterior(self):
        m = self.crear()
        self.sonda.side_effect = OSError()
        m.ciclo()
        self.tiempo = 10
        self.sonda.side_effect = lambda *args: correcto()
        m.ciclo()
        self.assertTrue(m.estado()['resumen_ventana'][0]['correcto_posterior'])
        copia = m.estado()['resumen_ventana']
        copia[0]['por_estado']['correcto'] = 999
        self.assertEqual(m.estado()['resumen_ventana'][0]['por_estado']['correcto'], 1)
        self.tiempo = 600
        resumen = m.estado()['resumen_ventana'][0]
        self.assertEqual(resumen['intentos'], 1)
        self.assertFalse(resumen['correcto_posterior'])
        self.fuente.return_value = contexto(OTRO)
        m.ciclo()
        self.assertEqual(m.estado()['resumen_ventana'][0]['intentos'], 1)
        self.fuente.return_value = {'estado': 'sin_ruta'}
        m.ciclo()
        self.assertEqual(m.estado()['resumen_ventana'], [])
