"""Presencia contextual con datos sintéticos y reloj controlado."""

from copy import deepcopy
import unittest
from unittest.mock import Mock

from backend.arp import interpretar_tabla_arp
from backend.configuracion import ConfiguracionBackend, ConfiguracionMemoria, interpretar_configuracion
from backend.coordinador import CoordinadorARP
from backend.presencia import comparar_presencia_arp
from test_coordinador import Tiempo, contexto, lectura, CONTEXTO, OTRO

A = '? (192.0.2.20) at 2:0:0:0:0:20 on en0 [ethernet]\n'
B = '? (192.0.2.21) at 2:0:0:0:0:21 on en0 [ethernet]\n'
GATEWAY = '? (192.0.2.1) at 2:0:0:0:0:1 on en0 [ethernet]\n'
INCOMPLETA = '? (192.0.2.20) at (incomplete) on en0 [ethernet]\n'


def tabla(texto, parcial=False):
    dato = lectura('lectura_parcial' if parcial else 'lectura_correcta')
    dato.update(interpretar_tabla_arp(texto + ('incorrecto' if parcial else '')))
    return dato


class PruebasPresencia(unittest.TestCase):
    def ejecutar(self, datos, contextos=None, *, capacidad=100, ausencias=3):
        self.tiempo = Tiempo()
        self.arp = Mock(side_effect=datos)
        self.c = CoordinadorARP(
            ConfiguracionBackend(ausencias_arp=ausencias, memoria=ConfiguracionMemoria(capacidad, 600)),
            reloj=self.tiempo.reloj, parada=self.tiempo, consultar_arp=self.arp,
            consultar_contexto=Mock(side_effect=[contexto(c) for c in contextos] if contextos else None,
                                   return_value=contexto()),
        )
        self.c.ejecutar(ciclos=len(datos))
        return self.c.consultar_resumen()['presencia']

    def tipos(self, presencia):
        return [e['tipo'] for e in presencia['eventos_en_memoria']]

    def test_primera_carga_y_nueva_asociacion_sin_inventar_conexiones(self):
        p = self.ejecutar([tabla(A), tabla(A + B)])
        self.assertEqual(self.tipos(p), ['referencia_inicial', 'primera_observacion'])
        self.assertEqual([d['estado'] for d in p['asociaciones']], ['observado', 'observado'])
        self.assertEqual(p['asociaciones'][0]['antiguedad_s'], 0)
        self.assertEqual(p['unidad'], 'asociaciones_ipv4_mac_en_contexto')

    def test_ausencia_requiere_tres_ciclos_y_reaparicion_no_se_repite(self):
        p = self.ejecutar([tabla(A), tabla(GATEWAY), tabla(GATEWAY)])
        self.assertEqual(p['asociaciones'][0]['estado'], 'indeterminado')
        self.assertEqual(p['asociaciones'][0]['ausencias_consecutivas'], 2)
        p = self.ejecutar([tabla(A)] + [tabla(GATEWAY)] * 4 + [tabla(A), tabla(A)])
        self.assertEqual(self.tipos(p), ['referencia_inicial', 'ausencia_observada', 'reaparicion'])
        self.assertEqual([e['ciclo'] for e in p['eventos_en_memoria']], [1, 4, 6])
        self.assertEqual(p['asociaciones'][0]['ausencias_consecutivas'], 0)

    def test_regreso_antes_del_umbral_no_es_reaparicion_confirmada(self):
        p = self.ejecutar([tabla(A), tabla(GATEWAY), tabla(A)])
        self.assertEqual(self.tipos(p), ['referencia_inicial'])

    def test_fallos_parciales_e_incompletas_interrumpen_racha(self):
        interrupciones = [lectura('error_recoleccion'), lectura('sin_datos_visibles'),
                          lectura('error_interpretacion'), tabla(GATEWAY, parcial=True), tabla(INCOMPLETA)]
        for interrupcion in interrupciones:
            with self.subTest(estado=interrupcion['estado']):
                p = self.ejecutar([tabla(A), tabla(GATEWAY), tabla(GATEWAY),
                                  interrupcion, tabla(GATEWAY), tabla(GATEWAY)])
                self.assertEqual(self.tipos(p), ['referencia_inicial'])
                self.assertEqual(p['asociaciones'][0]['ausencias_consecutivas'], 2)
                self.assertEqual(p['asociaciones'][0]['estado'], 'indeterminado')

    def test_parcial_con_asociacion_renueva_evidencia_positiva(self):
        p = self.ejecutar([tabla(A), tabla(GATEWAY), tabla(A, parcial=True)])
        self.assertEqual(p['asociaciones'][0]['estado'], 'observado')
        self.assertEqual(p['asociaciones'][0]['ausencias_consecutivas'], 0)
        self.assertEqual(p['asociaciones'][0]['antiguedad_s'], 0)

    def test_fallo_despues_de_ausencia_no_confirma_estado_actual(self):
        p = self.ejecutar([tabla(A)] + [tabla(GATEWAY)] * 3 + [lectura('error_recoleccion')])
        self.assertEqual(p['asociaciones'][0]['estado'], 'indeterminado')
        self.assertEqual(p['asociaciones'][0]['ausencias_consecutivas'], 0)
        self.assertIn('ausencia_observada', self.tipos(p))

    def test_mac_compartida_y_cambio_de_mac_no_fusionan_asociaciones(self):
        misma_mac = B.replace('2:0:0:0:0:21', '2:0:0:0:0:20')
        p = self.ejecutar([tabla(A + A + misma_mac)])
        self.assertEqual(len(p['asociaciones']), 2)
        self.assertEqual(self.tipos(p), ['referencia_inicial', 'referencia_inicial'])
        p = self.ejecutar([tabla(A), tabla(A.replace('2:0:0:0:0:20', '2:0:0:0:0:30'))])
        self.assertEqual(len(p['asociaciones']), 2)
        self.assertEqual(self.tipos(p), ['referencia_inicial', 'primera_observacion'])

    def test_solo_incompleta_no_crea_identidad_y_gateway_no_se_incluye(self):
        p = self.ejecutar([tabla(INCOMPLETA + GATEWAY)])
        self.assertEqual(p['asociaciones'], [])
        self.assertEqual(p['eventos_en_memoria'], [])
        self.assertEqual(self.c.consultar_resumen()['vecinos']['cantidad'], 1)

    def test_contextos_a_b_a_y_perdida_no_mezclan_historia(self):
        for contextos in ([CONTEXTO, OTRO, CONTEXTO], [CONTEXTO, None, CONTEXTO]):
            p = self.ejecutar([tabla(A)] * 3, contextos)
            self.assertEqual(self.tipos(p), ['referencia_inicial'])
            self.assertEqual(p['eventos_en_memoria'][0]['ciclo'], 3)
            inicial = self.c.memoria.historial()[0]['id_contexto']
            vieja = self.c.consultar_resumen(id_contexto=inicial)
            self.assertFalse(vieja['calidad']['es_contexto_actual'])
            self.assertEqual(vieja['presencia']['eventos_en_memoria'][0]['ciclo'], 1)

    def test_retencion_capacidad_y_reinicio_no_inventan_reaparicion(self):
        p = self.ejecutar([tabla(A)] + [tabla(GATEWAY)] * 3 + [tabla(A)], capacidad=2)
        self.assertEqual(self.tipos(p), ['primera_observacion'])
        self.assertNotIn('reaparicion', self.tipos(p))
        self.tiempo.ahora += 600
        self.assertEqual(self.c.consultar_resumen()['presencia']['asociaciones'], [])
        self.assertEqual(CoordinadorARP().consultar_resumen()['presencia']['eventos_en_memoria'], [])

    def test_antiguedad_sin_nuevas_consultas_no_genera_eventos(self):
        p = self.ejecutar([tabla(A)])
        self.tiempo.ahora += 90
        despues = self.c.consultar_resumen()['presencia']
        self.assertEqual(despues['asociaciones'][0]['estado'], 'indeterminado')
        self.assertEqual(despues['eventos_en_memoria'], p['eventos_en_memoria'])
        self.arp.assert_called_once()

    def test_ids_estables_copias_y_ciclos_duplicados_no_inflan_ausencias(self):
        p = self.ejecutar([tabla(A), tabla(GATEWAY), tabla(GATEWAY)])
        self.assertEqual(p, self.c.consultar_resumen()['presencia'])
        registros = self.c.memoria.instantanea_temporal(id_ejecucion=self.c.id_ejecucion)
        original = deepcopy(registros)
        duplicado = deepcopy(registros[1])
        duplicado['observacion']['id_observacion'] = 'otro-id-mismo-ciclo'
        p2 = comparar_presencia_arp([registros[0], registros[1], duplicado, registros[1], registros[2]],
                                   id_ejecucion=self.c.id_ejecucion, id_contexto=p['id_contexto'])
        self.assertEqual(p2, p)
        self.assertEqual(registros, original)
        registros[2]['observacion']['ciclo'] = 5
        p3 = comparar_presencia_arp(registros, id_ejecucion=self.c.id_ejecucion, id_contexto=p['id_contexto'])
        self.assertEqual(p3['asociaciones'][0]['ausencias_consecutivas'], 1)

    def test_configuracion_umbral_y_validacion(self):
        self.assertEqual(interpretar_configuracion('{"ausencias_arp":2}').ausencias_arp, 2)
        for valor in (True, False, 0, -1, 1.5, '3', None):
            with self.assertRaises((ValueError, TypeError)):
                ConfiguracionBackend(ausencias_arp=valor)
        p = self.ejecutar([tabla(A), tabla(GATEWAY)], ausencias=1)
        self.assertEqual(p['asociaciones'][0]['estado'], 'no_observado_recientemente')

    def test_pausa_prolongada_interrumpe_racha_aunque_ciclos_sean_consecutivos(self):
        p = self.ejecutar([tabla(A), tabla(GATEWAY), tabla(GATEWAY)])
        registros = self.c.memoria.instantanea_temporal(id_ejecucion=self.c.id_ejecucion)
        registros[0]['antiguedad_s'] = 105
        registros[1]['antiguedad_s'] = 100
        registros[2]['antiguedad_s'] = 0
        resultado = comparar_presencia_arp(registros, id_ejecucion=self.c.id_ejecucion,
                                           id_contexto=p['id_contexto'], ausencias=2)
        self.assertEqual(resultado['asociaciones'][0]['ausencias_consecutivas'], 1)
        self.assertEqual(self.tipos(resultado), ['referencia_inicial'])
