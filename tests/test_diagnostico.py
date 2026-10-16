"""Verifica diagnóstico automático con capturas sintéticas y permisos explícitos.

Cubre coincidencias, falta de cobertura, cambio de red, errores y ausencia de
tráfico individual sin consultar routers ni ejecutar nuevas mediciones.
"""
from copy import deepcopy
import unittest
from backend.diagnostico import diagnosticar_conexion, diagnosticar_trafico
from test_analisis import capturas_recorrido, captura_tiempos


def escenario():
    web, _ = capturas_recorrido()
    conexion = captura_tiempos()
    router = {'autorizada': True, 'estado': 'lectura_correcta',
              'contexto': deepcopy(conexion['contexto']), 'series': []}
    for edad in range(10, 600, 20):
        router['series'].append({'antiguedad_s': edad, 'intervalo_s': 20,
            'motivo': 'intervalo_valido', 'fuente': 'wan', 'familia_ip': 'IPv4', 'interfaz': 'prueba',
            'bytes_recibidos': str(2000000 if edad < 300 else 1000000), 'bytes_enviados': '0'})
    return router, conexion, web


class PruebasDiagnostico(unittest.TestCase):
    def test_automatico_sin_incidente_marcado_ni_salud_absoluta(self):
        _, conexion, web = escenario()
        r = diagnosticar_conexion(web, conexion)
        self.assertIn('No se capturó', r['diagnostico']['falta'])
        self.assertIn('otro equipo', r['diagnostico']['comprobar'])
        self.assertNotIn('marca el momento', str(r))

    def test_coincidencia_aporta_evidencia_y_no_causa(self):
        router, conexion, web = escenario()
        original = deepcopy((router, conexion, web))
        r = diagnosticar_trafico(router, conexion, web)
        self.assertEqual(r['estado'], 'comparable')
        c = r['comparaciones'][0]
        self.assertGreater(c['reciente']['mbps'], c['anterior']['mbps'])
        self.assertIn('aumentó', c['mensaje'])
        self.assertIn('pausarla temporalmente', c['orientacion'])
        self.assertIn('no confirma la causa', c['comprobar'])
        self.assertIn('No disponible', r['consumo_individual'])
        self.assertEqual((router, conexion, web), original)

    def test_insuficiente_no_une_redes_datos_antiguos_o_errores(self):
        for caso in ('red', 'antiguo', 'error_router', 'web', 'conexion', 'cobertura'):
            with self.subTest(caso=caso):
                router, conexion, web = escenario()
                if caso == 'red': router['contexto']['gateway'] = '192.168.50.254'
                if caso == 'antiguo': router['series'] = router['series'][2:]
                if caso == 'error_router': router['estado'] = 'error_fuente'
                if caso == 'web': web['resultados'][0]['antiguedad_s'] = 120
                if caso == 'conexion': conexion['estado'] = 'detenido'
                if caso == 'cobertura': router['series'] = router['series'][:4]
                self.assertEqual(diagnosticar_trafico(router, conexion, web)['estado'], 'insuficiente')

    def test_sin_permiso_no_hay_resultado_privado(self):
        router, conexion, web = escenario()
        router['autorizada'] = False
        self.assertIsNone(diagnosticar_trafico(router, conexion, web))
        self.assertNotIn('wan', str(diagnosticar_conexion(web, conexion)))

    def test_fallos_web_y_trafico_sin_empeorar_rtt(self):
        router, conexion, web = escenario()
        for s in conexion['historial']:
            for f in s['destinos']: f['rtt_ms']['promedio'] = 20
        web['historial'][1]['resultados'][0]['estado'] = 'tiempo_agotado'
        r = diagnosticar_trafico(router, conexion, web)['comparaciones'][0]
        self.assertIn('aumentó', r['mensaje'])
        self.assertEqual(r['acceso']['reciente']['no_correctos'], 1)

    def test_disminucion_no_se_presenta_como_recuperacion(self):
        router, conexion, web = escenario()
        for p in router['series']: p['bytes_recibidos'] = '100'
        r = diagnosticar_trafico(router, conexion, web)['comparaciones'][0]
        self.assertIn('No observamos un aumento conjunto', r['mensaje'])
        self.assertIn('no descarta problemas breves', r['orientacion'])
