"""Contextos, reloj y sondas artificiales verifican métricas, historial acotado y ciclo de vida sin red real; se consulta el mismo contrato que sirve la API."""

from threading import Event, Thread
import unittest
from unittest.mock import Mock

from backend.conectividad import MonitoreoConectividad, resumir_serie
from backend.configuracion import ConfiguracionBackend, ConfiguracionMemoria, interpretar_configuracion
from test_coordinador import contexto, CONTEXTO, OTRO


def respuesta(rtt=10):
    return {'estado': 'respuesta_valida', 'rtt_ms': rtt}


class PruebasConectividad(unittest.TestCase):
    def crear(self, **opciones):
        self.tiempo = 0
        self.fuente = Mock(return_value=contexto())
        self.sonda = Mock(return_value=respuesta())
        self.config = ConfiguracionBackend(**opciones)
        return MonitoreoConectividad(self.config, consultar_contexto=self.fuente,
                                    sonda=self.sonda, reloj=lambda: self.tiempo, esperar=lambda _: False)

    def test_metricas_y_silencios_no_son_errores(self):
        muestras = [respuesta(10), respuesta(20), respuesta(30)] + [{'estado': 'sin_respuesta'}] * 2
        dato = resumir_serie(muestras, 5)
        self.assertEqual(dato['perdida_observada_pct'], 40)
        self.assertEqual(dato['rtt_ms'], dict(muestras=3, minimo=10, promedio=20, maximo=30))
        self.assertEqual(dato['calidad'], 'completa')
        dato = resumir_serie([{'estado': 'sin_respuesta'}] * 5, 5)
        self.assertEqual(dato['perdida_observada_pct'], 100)
        self.assertIsNone(dato['rtt_ms']['promedio'])

    def test_errores_omisiones_y_cero(self):
        for muestras in ([respuesta(0), {'estado': 'error_recoleccion'}], [respuesta(0)], []):
            dato = resumir_serie(muestras, 2)
            self.assertIsNone(dato['perdida_observada_pct'])
            self.assertEqual(dato['omitidas'], 2 - len(muestras))
        self.assertEqual(resumir_serie([respuesta(0)], 1)['rtt_ms']['promedio'], 0)

    def test_dos_destinos_cinco_sondas_y_consultas_sin_nuevas_sondas(self):
        monitor = self.crear()
        monitor.ciclo()
        self.assertEqual(self.sonda.call_count, 10)
        for _ in range(3):
            dato = monitor.estado()
        self.assertEqual(self.sonda.call_count, 10)
        self.assertEqual([d['ipv4'] for d in dato['destinos']], ['192.0.2.1', '1.1.1.1'])
        self.assertTrue(all(d['respuestas'] == 5 for d in dato['destinos']))
        dato['destinos'][0]['respuestas'] = 999
        self.assertEqual(monitor.estado()['destinos'][0]['respuestas'], 5)

    def test_errores_conservan_fecha_y_edad_anterior_sin_rejuvenecer(self):
        monitor = self.crear()
        monitor.ciclo()
        anterior = monitor.estado()['destinos'][0]['fin']
        self.tiempo = 40
        self.sonda.side_effect = OSError('fallo simulado')
        monitor.ciclo()
        self.tiempo = 50
        fila = monitor.estado()['destinos'][0]
        self.assertEqual(fila['errores'], 5)
        self.assertIsNone(fila['perdida_observada_pct'])
        self.assertEqual(fila['antiguedad_s'], 10)
        self.assertEqual(fila['anterior_completa']['antiguedad_s'], 50)
        self.assertEqual(fila['anterior_completa']['fin'], anterior)
        self.sonda.side_effect = None
        monitor.ciclo()
        self.assertEqual(monitor.estado()['destinos'][0]['calidad'], 'completa')

    def test_antiguedad_retencion_y_capacidad(self):
        monitor = self.crear(memoria=ConfiguracionMemoria(capacidad=2, retencion_s=600))
        for instante in (0, 1, 2):
            self.tiempo = instante
            monitor.ciclo()
        self.assertEqual(monitor.estado()['series_conservadas'], 2)
        self.tiempo = 92
        self.assertEqual(monitor.estado()['destinos'][0]['vigencia'], 'desactualizado')
        self.tiempo = 602
        self.assertEqual(monitor.estado()['destinos'], [])

    def test_contextos_a_b_a_no_mezclan_historial(self):
        monitor = self.crear()
        ids = []
        for red in (CONTEXTO, OTRO, CONTEXTO):
            self.fuente.return_value = contexto(red)
            monitor.ciclo()
            dato = monitor.estado()
            ids.append(dato['id_contexto'])
            self.assertEqual(dato['series_conservadas'], 1)
        self.assertEqual(len(set(ids)), 3)

    def test_cambio_durante_serie_descarta_resultados(self):
        monitor = self.crear()
        self.fuente.side_effect = [contexto(), contexto(OTRO)]
        monitor.ciclo()
        self.assertEqual(self.sonda.call_count, 2)
        self.assertEqual(monitor.estado()['estado'], 'sin_contexto')
        self.assertEqual(monitor.estado()['destinos'], [])

    def test_contexto_no_disponible_no_envia_y_recuperacion_nuevo_tramo(self):
        monitor = self.crear()
        monitor.ciclo()
        antes = monitor.estado()['id_contexto']
        self.sonda.reset_mock()
        self.fuente.return_value = contexto(None)
        monitor.ciclo()
        self.sonda.assert_not_called()
        self.assertEqual(monitor.estado()['destinos'], [])
        self.fuente.return_value = contexto()
        monitor.ciclo()
        self.assertNotEqual(antes, monitor.estado()['id_contexto'])

    def test_sin_gateway_omite_router_pero_mide_externo(self):
        monitor = self.crear()
        red = dict(CONTEXTO, gateway=None)
        self.fuente.return_value = contexto(red)
        monitor.ciclo()
        filas = monitor.estado()['destinos']
        self.assertEqual(filas[0]['omitidas'], 5)
        self.assertEqual(filas[1]['respuestas'], 5)

    def test_parada_interrumpe_rondas_y_registra_omisiones(self):
        monitor = self.crear()
        def esperar(_):
            monitor.detener()
            return True
        monitor._esperar = esperar
        monitor.ciclo()
        self.assertEqual(self.sonda.call_count, 2)
        self.assertTrue(all(d['omitidas'] == 4 for d in monitor.estado()['destinos']))
        monitor.ciclo()
        self.assertEqual(self.sonda.call_count, 2)

    def test_no_superpone_ciclos_y_consulta_no_bloquea(self):
        monitor = self.crear(muestras_conectividad=1)
        entrar, liberar = Event(), Event()
        def medir(*_):
            entrar.set()
            liberar.wait(2)
            return respuesta()
        self.sonda.side_effect = medir
        hilo = Thread(target=monitor.ciclo)
        hilo.start()
        try:
            self.assertTrue(entrar.wait(1))
            self.assertEqual(monitor.estado()['estado'], 'midiendo')
            with self.assertRaises(RuntimeError):
                monitor.ciclo()
        finally:
            liberar.set()
            hilo.join(3)
        self.assertFalse(hilo.is_alive())

    def test_programacion_espera_tras_serie_y_parada(self):
        monitor = self.crear(muestras_conectividad=2)
        pausas = []
        def esperar(segundos):
            pausas.append((segundos, self.sonda.call_count))
            if segundos == 30:
                monitor.detener()
                return True
            return False
        monitor._esperar = esperar
        monitor.ejecutar()
        self.assertEqual(pausas, [(1, 2), (30, 4)])
        self.assertEqual(monitor.estado()['estado'], 'detenido')

    def test_rtt_invalido_es_error_no_perdida(self):
        monitor = self.crear(muestras_conectividad=1)
        for valor in (None, True, -1, float('nan'), float('inf')):
            self.sonda.return_value = respuesta(valor)
            monitor.ciclo()
            self.assertTrue(all(d['errores'] == 1 for d in monitor.estado()['destinos']))

    def test_configuracion_rechaza_destinos_y_limites_invalidos(self):
        self.assertEqual(interpretar_configuracion('{}').destinos_externos, ('1.1.1.1',))
        self.assertEqual(interpretar_configuracion('{"destinos_externos":[]}').destinos_externos, ())
        for campo, valores in {
            'muestras_conectividad': [0, 21, True, 1.5],
            'intervalo_conectividad_s': [0, True, float('nan'), float('inf')],
            'conectividad_activa': [1, None],
            'destinos_externos': [('192.168.0.1',), ('224.0.0.1',), ('1.1.1.1', '1.1.1.1'), (True,), ('example.com',)],
        }.items():
            for valor in valores:
                with self.subTest(campo=campo, valor=valor), self.assertRaises((ValueError, TypeError)):
                    ConfiguracionBackend(**{campo: valor})
        with self.assertRaises(ValueError):
            interpretar_configuracion('{"destinos_externos":"1.1.1.1"}')

    def test_historial_estable_copias_y_fallo_no_borra_serie_anterior(self):
        m = self.crear()
        m.ciclo()
        primera = m.estado()['historial'][0]
        self.tiempo = 30
        self.sonda.side_effect = OSError('fallo simulado')
        m.ciclo()
        dato = m.estado()
        self.assertEqual(len(dato['historial']), 2)
        self.assertEqual(dato['historial'][0]['id_serie'], primera['id_serie'])
        self.assertEqual(dato['historial'][0]['destinos'][0]['respuestas'], 5)
        self.assertEqual(dato['historial'][1]['destinos'][0]['errores'], 5)
        self.assertEqual(dato['historial'][0]['antiguedad_s'], 30)
        self.assertNotIn('fin_monotonico', repr(dato['historial']))
        dato['historial'][0]['destinos'][0]['respuestas'] = 999
        self.assertEqual(m.estado()['historial'][0]['destinos'][0]['respuestas'], 5)
        self.assertEqual(self.sonda.call_count, 20)

    def test_historial_capacidad_caducidad_y_contextos_no_se_mezclan(self):
        m = self.crear(memoria=ConfiguracionMemoria(capacidad=2, retencion_s=60))
        for instante in (0, 10, 20):
            self.tiempo = instante
            m.ciclo()
        dato = m.estado()
        self.assertEqual(len(dato['historial']), 2)
        self.assertEqual(dato['historial'][0]['antiguedad_s'], 10)
        self.tiempo = 70
        self.assertEqual(len(m.estado()['historial']), 1)
        self.fuente.return_value = contexto(OTRO)
        m.ciclo()
        otro = m.estado()
        self.assertEqual(len(otro['historial']), 1)
        self.assertNotEqual(otro['id_contexto'], dato['id_contexto'])
        self.fuente.return_value = contexto()
        m.ciclo()
        self.assertEqual(len(m.estado()['historial']), 1)
        self.assertNotEqual(m.estado()['id_contexto'], dato['id_contexto'])
        self.tiempo = 130
        self.assertEqual(m.estado()['historial'], [])
