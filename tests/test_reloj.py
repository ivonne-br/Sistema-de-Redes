"""Simula reposo y cambios de calendario sin suspender el Mac ni consultar la red.

Controla el reloj del sistema usado por defecto; verifica selección de plataforma,
edades, retención y continuidad ARP en los módulos que alimentan la API.
"""

import unittest
from unittest.mock import Mock, patch

from backend.busqueda import BusquedaLocal
from backend.conectividad import MonitoreoConectividad
from backend.coordinador import CoordinadorARP
from backend.memoria import MemoriaObservaciones
from backend.reloj import tiempo_continuo
from backend.web import MonitoreoWeb, comprobar
from test_coordinador import contexto, lectura
from test_memoria import observacion
from test_presencia import tabla, A, GATEWAY


class PruebasSeleccionReloj(unittest.TestCase):
    def test_macos_usa_raw_y_linux_boottime(self):
        for plataforma, nombre in [('darwin', 'CLOCK_MONOTONIC_RAW'), ('linux', 'CLOCK_BOOTTIME')]:
            with self.subTest(plataforma=plataforma), patch('backend.reloj.sys.platform', plataforma), \
                    patch('backend.reloj.time.' + nombre, 123, create=True), \
                    patch('backend.reloj.time.clock_gettime', return_value=456) as leer:
                self.assertEqual(tiempo_continuo(), 456)
                leer.assert_called_once_with(123)

    def test_sistema_no_soportado_no_sustituye_por_calendario(self):
        with patch('backend.reloj.sys.platform', 'desconocido'), self.assertRaises(RuntimeError):
            tiempo_continuo()

    def test_error_del_reloj_no_se_oculta(self):
        with patch('backend.reloj.time.clock_gettime', side_effect=OSError('reloj inaccesible')):
            with self.assertRaises(OSError):
                tiempo_continuo()


class PruebasReposo(unittest.TestCase):
    def setUp(self):
        self.ahora = 1000.0
        self.clock = patch('backend.reloj.time.clock_gettime', side_effect=lambda _: self.ahora)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_memoria_predeterminada_expira_en_frontera_600(self):
        memoria = MemoriaObservaciones()
        memoria.guardar(observacion())
        self.ahora += 599
        self.assertEqual(len(memoria.historial()), 1)
        self.ahora += 1
        self.assertEqual(memoria.historial(), [])

    def test_coordinador_comparte_reloj_y_no_renueva_fecha(self):
        monitor = CoordinadorARP(consultar_contexto=Mock(return_value=contexto()),
                                 consultar_arp=Mock(return_value=lectura()))
        monitor.ejecutar(ciclos=1)
        antes = monitor.memoria.ultima()
        self.ahora += 120
        with patch('backend.reloj.time.time', return_value=-999999):
            datos = monitor.memoria.instantanea_temporal(id_ejecucion=monitor.id_ejecucion)
        self.assertEqual(datos[0]['antiguedad_s'], 120)
        self.assertEqual(datos[0]['observacion'], antes)
        self.ahora += 480
        self.assertIsNone(monitor.memoria.ultima())

    def test_pausa_rompe_racha_arp_sin_inventar_ausencia(self):
        monitor = CoordinadorARP(consultar_contexto=Mock(return_value=contexto()),
                                 consultar_arp=Mock(side_effect=[tabla(A)] + [tabla(GATEWAY)] * 3))
        for ciclo, instante in enumerate((1000, 1005, 1010, 1130), 1):
            self.ahora = instante
            monitor._observar(ciclo)
        presencia = monitor.consultar_resumen()['presencia']
        self.assertEqual(presencia['asociaciones'][0]['ausencias_consecutivas'], 1)
        self.assertEqual([e['tipo'] for e in presencia['eventos_en_memoria']], ['referencia_inicial'])

    def test_icmp_envejece_expira_y_reanuda_sin_rellenar_pausa(self):
        sonda = Mock(return_value={'estado': 'respuesta_valida', 'rtt_ms': 5})
        monitor = MonitoreoConectividad(consultar_contexto=Mock(return_value=contexto()),
                                        sonda=sonda, esperar=lambda _: False)
        monitor.ciclo()
        fin = monitor.estado()['destinos'][0]['fin']
        self.ahora += 120
        dato = monitor.estado()['destinos'][0]
        self.assertEqual((dato['antiguedad_s'], dato['vigencia'], dato['fin']), (120, 'desactualizado', fin))
        self.ahora += 480
        self.assertEqual(monitor.estado()['historial'], [])
        self.assertEqual(monitor.estado()['resumen_ventana'], [])
        self.assertEqual(sonda.call_count, 10)
        monitor.ciclo()
        estado = monitor.estado()
        self.assertEqual(estado['series_conservadas'], 1)
        self.assertEqual(estado['resumen_ventana'][0]['realizadas'], 5)
        self.assertEqual(estado['resumen_ventana'][0]['sin_respuesta'], 0)

    def test_web_envejece_expira_y_reanuda_sin_intentos_ficticios(self):
        sonda = Mock(return_value={'estado': 'correcto', 'duracion_ms': 1,
                                  'codigo_http': None, 'direcciones': []})
        monitor = MonitoreoWeb(consultar_contexto=Mock(return_value=contexto()), sonda=sonda)
        monitor.ciclo()
        fin = monitor.estado()['resultados'][0]['fin']
        self.ahora += 180
        dato = monitor.estado()['resultados'][0]
        self.assertEqual((dato['antiguedad_s'], dato['vigencia'], dato['fin']), (180, 'desactualizado', fin))
        self.ahora += 420
        self.assertEqual(monitor.estado()['historial'], [])
        self.assertEqual(monitor.estado()['resultados'], [])
        self.assertEqual(sonda.call_count, 2)
        monitor.ciclo()
        self.assertEqual(monitor.estado()['resumen_ventana'][0]['intentos'], 1)

    def test_busqueda_no_mantiene_respuesta_reciente_tras_reposo(self):
        actual = {'id_contexto': 'A', 'contexto': {'ipv4_local': '192.168.0.2/30',
                  'gateway': None}, 'entradas': []}
        monitor = BusquedaLocal(lambda: actual, sonda=Mock(return_value={'estado': 'respuesta_valida'}))
        monitor.barrer()
        antes = monitor.estado(id_contexto='A')['resultados'][0]
        self.ahora += 180
        despues = monitor.estado(id_contexto='A')['resultados'][0]
        self.assertEqual(despues['antiguedad_s'], 180)
        self.assertEqual(despues['vigencia'], 'desactualizado')
        self.assertEqual(despues['fin_comprobacion'], antes['fin_comprobacion'])

    def test_duracion_web_incluye_tiempo_transcurrido(self):
        def resolver(*_):
            self.ahora += 3
            return [(None, None, None, None, ('192.0.2.1', 0))]
        with patch('backend.web.socket.getaddrinfo', side_effect=resolver):
            self.assertEqual(comprobar('dns', 'ejemplo.test', 8)['duracion_ms'], 3000)
