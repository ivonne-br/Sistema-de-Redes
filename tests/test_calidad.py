"""Antigüedad y calidad con reloj controlado; no consulta la red."""

import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import Mock, patch

from backend.__main__ import main
from backend.calidad import evaluar_calidad_arp
from backend.configuracion import ConfiguracionBackend, ConfiguracionMemoria, interpretar_configuracion
from backend.coordinador import CoordinadorARP
from backend.descubrimiento import observar_consulta_arp
from backend.memoria import MemoriaObservaciones
from test_coordinador import Tiempo, contexto, lectura, CONTEXTO, OTRO


class PruebasCalidadARP(unittest.TestCase):
    def crear(self, estados=('lectura_correcta',), contextos=None, *, retencion=600, capacidad=100):
        self.tiempo = Tiempo()
        self.arp = Mock(side_effect=[lectura(e) for e in estados])
        self.contexto = Mock(side_effect=[contexto(c) for c in contextos] if contextos else None,
                             return_value=contexto())
        self.c = CoordinadorARP(
            ConfiguracionBackend(memoria=ConfiguracionMemoria(capacidad, retencion)),
            reloj=self.tiempo.reloj, parada=self.tiempo,
            consultar_arp=self.arp, consultar_contexto=self.contexto,
        )
        self.c.ejecutar(ciclos=len(estados))
        return self.c.consultar_calidad()

    def test_sin_muestras_no_inventa_antiguedad(self):
        calidad = CoordinadorARP().consultar_calidad()
        self.assertEqual(calidad['vigencia'], 'no_disponible')
        self.assertEqual(calidad['calidad_fuente'], 'no_disponible')
        self.assertIsNone(calidad['antiguedad_s'])
        self.assertIsNone(calidad['es_contexto_actual'])

    def test_vigencia_cambia_sin_nuevas_consultas_y_frontera_exacta(self):
        calidad = self.crear()
        self.assertEqual(calidad['antiguedad_s'], 0)
        self.assertEqual(calidad['vigencia'], 'vigente')
        self.tiempo.ahora += 89.999
        self.assertEqual(self.c.consultar_calidad()['vigencia'], 'vigente')
        self.tiempo.ahora += .001
        calidad = self.c.consultar_calidad()
        self.assertEqual(calidad['vigencia'], 'desactualizado')
        self.assertAlmostEqual(calidad['antiguedad_s'], 90)
        self.arp.assert_called_once()
        self.contexto.assert_called_once()

    def test_fallo_conserva_dato_anterior_sin_renovarlo(self):
        calidad = self.crear(('lectura_correcta', 'error_recoleccion'))
        datos = self.c.memoria.historial()
        self.assertEqual(calidad['estado_ultimo_intento'], 'error_recoleccion')
        self.assertEqual(calidad['calidad_fuente'], 'error_fuente')
        self.assertEqual(calidad['id_ultimo_intento'], datos[1]['id_observacion'])
        self.assertEqual(calidad['id_ultima_utilizable'], datos[0]['id_observacion'])
        self.assertEqual(calidad['antiguedad_s'], 5)
        self.tiempo.ahora += 85
        calidad = self.c.consultar_calidad()
        self.assertEqual(calidad['vigencia'], 'desactualizado')
        self.assertEqual(calidad['calidad_fuente'], 'error_fuente')

    def test_sin_visibilidad_o_interpretacion_no_renueva_edad(self):
        for fallo in ('sin_datos_visibles', 'error_interpretacion'):
            calidad = self.crear(('lectura_correcta', fallo))
            self.assertEqual(calidad['antiguedad_s'], 5)
            self.assertEqual(calidad['estado_ultimo_intento'], fallo)
            self.assertEqual(calidad['calidad_fuente'], 'error_fuente')

    def test_solo_fallos_no_tienen_referencia_utilizable(self):
        for fallo in ('error_recoleccion', 'sin_datos_visibles', 'error_interpretacion'):
            calidad = self.crear((fallo,))
            self.assertIsNone(calidad['id_ultima_utilizable'])
            self.assertIsNone(calidad['antiguedad_s'])
            self.assertEqual(calidad['vigencia'], 'no_disponible')
            self.assertEqual(calidad['calidad_fuente'], 'error_fuente')

    def test_parcial_aporta_evidencia_sin_ocultar_su_calidad(self):
        calidad = self.crear(('lectura_correcta', 'lectura_parcial'))
        self.assertEqual(calidad['calidad_fuente'], 'parcial')
        self.assertEqual(calidad['estado_ultima_utilizable'], 'observacion_parcial')
        self.assertEqual(calidad['antiguedad_s'], 0)
        self.assertEqual(calidad['id_ultimo_intento'], calidad['id_ultima_utilizable'])

    def test_recuperacion_reemplaza_referencia_y_sigue_guardando_fallo(self):
        calidad = self.crear(('lectura_correcta', 'error_recoleccion', 'lectura_correcta'))
        self.assertEqual(calidad['calidad_fuente'], 'completa')
        self.assertEqual(calidad['antiguedad_s'], 0)
        self.assertEqual(len(self.c.memoria.historial()), 3)

    def test_regreso_a_no_reutiliza_lectura_de_tramo_anterior(self):
        calidad = self.crear(('lectura_correcta', 'lectura_correcta', 'error_recoleccion'),
                             (CONTEXTO, OTRO, CONTEXTO))
        self.assertIsNone(calidad['antiguedad_s'])
        self.assertEqual(calidad['calidad_fuente'], 'error_fuente')
        anterior = self.c.memoria.historial()[0]
        vieja = self.c.consultar_calidad(id_contexto=anterior['id_contexto'])
        self.assertEqual(vieja['antiguedad_s'], 10)
        self.assertFalse(vieja['es_contexto_actual'])
        self.assertTrue(calidad['es_contexto_actual'])

    def test_perdida_contexto_no_presenta_datos_previos_como_actuales(self):
        calidad = self.crear(('lectura_correcta', 'lectura_correcta'), (CONTEXTO, None))
        self.assertIsNone(calidad['id_contexto'])
        self.assertIsNone(calidad['id_ultima_utilizable'])
        self.assertEqual(calidad['estado_ultimo_intento'], 'error_contexto')

    def test_retencion_y_capacidad_quitan_la_referencia_utilizable(self):
        self.crear(retencion=10)
        self.tiempo.ahora += 10
        calidad = self.c.consultar_calidad()
        self.assertIsNone(calidad['antiguedad_s'])
        self.assertEqual(calidad['vigencia'], 'no_disponible')
        self.assertEqual(self.c.memoria.estadisticas()['descartadas_por_antiguedad'], 1)
        calidad = self.crear(('lectura_correcta', 'error_recoleccion'), capacidad=1)
        self.assertIsNone(calidad['id_ultima_utilizable'])
        self.assertEqual(calidad['calidad_fuente'], 'error_fuente')

    def test_procesamiento_lento_cuenta_desde_fin_consulta_no_desde_guardado(self):
        def construir(*args, **kwargs):
            resultado = observar_consulta_arp(*args, **kwargs)
            # La hora civil no participa en la cuenta.
            resultado['inicio_captura'] = '2099-01-01T00:00:00+00:00'
            resultado['fin_captura'] = '2099-01-01T00:00:01+00:00'
            self.tiempo.ahora += 7
            return resultado
        with patch('backend.coordinador.observar_consulta_arp', side_effect=construir):
            calidad = self.crear()
        self.assertEqual(calidad['antiguedad_s'], 7)
        self.assertEqual(calidad['referencia_antiguedad'], 'fin_consulta_arp')

    def test_memoria_sin_tiempo_conocido_no_certifica_captura(self):
        self.crear()
        memoria = MemoriaObservaciones(reloj=self.tiempo.reloj)
        memoria.guardar(self.c.memoria.ultima())
        registros = memoria.instantanea_temporal(id_ejecucion=self.c.id_ejecucion)
        calidad = evaluar_calidad_arp(registros, id_ejecucion=self.c.id_ejecucion, vigencia_s=90)
        self.assertIsNone(calidad['antiguedad_s'])
        self.assertEqual(calidad['vigencia'], 'no_disponible')

    def test_otra_ejecucion_no_aporta_datos_y_copias_no_mutan_memoria(self):
        self.crear()
        registros = self.c.memoria.instantanea_temporal(id_ejecucion=self.c.id_ejecucion)
        registros[0]['observacion']['estado'] = 'error_recoleccion'
        self.assertEqual(self.c.consultar_calidad()['calidad_fuente'], 'completa')
        self.assertEqual(self.c.memoria.instantanea_temporal(id_ejecucion='otra'), [])
        calidad = evaluar_calidad_arp(registros, id_ejecucion='otra', vigencia_s=90)
        self.assertEqual(calidad['calidad_fuente'], 'no_disponible')

    def test_validacion_vigencia_y_demora(self):
        self.assertEqual(interpretar_configuracion('{"vigencia_arp_s":30}').vigencia_arp_s, 30)
        for valor in (True, False, 0, -1, 1.5, None, '90'):
            with self.assertRaises((ValueError, TypeError)):
                ConfiguracionBackend(vigencia_arp_s=valor)
        self.crear()
        for valor in (True, -1, float('nan'), float('inf'), '1'):
            with self.assertRaises((ValueError, TypeError)):
                self.c.memoria.guardar(self.c.memoria.ultima(), demora_captura_s=valor)
        for valor in ('', ' ', 2, False):
            with self.assertRaises(ValueError):
                self.c.consultar_calidad(id_contexto=valor)

    def test_cli_emite_calidad_en_cada_linea_y_al_final(self):
        tiempo = Tiempo()
        c = CoordinadorARP(reloj=tiempo.reloj, parada=tiempo,
                           consultar_contexto=Mock(return_value=contexto()),
                           consultar_arp=Mock(side_effect=[lectura(), lectura('error_recoleccion')]))
        salida = io.StringIO()
        with patch('backend.__main__.CoordinadorARP', return_value=c), \
             patch('sys.argv', ['backend', 'monitorear-arp', '--ciclos', '2']), \
             redirect_stdout(salida), redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 1)
        registros = [json.loads(linea) for linea in salida.getvalue().splitlines()]
        self.assertEqual(registros[0]['calidad']['calidad_fuente'], 'completa')
        self.assertEqual(registros[1]['calidad']['calidad_fuente'], 'error_fuente')
        self.assertEqual(registros[1]['calidad']['antiguedad_s'], 5)
        self.assertEqual(registros[-1]['calidad'], registros[1]['calidad'])
        self.assertEqual(registros[0]['vecinos']['cantidad'], 1)
        self.assertTrue(registros[0]['vecinos']['es_ultimo_intento'])
        self.assertEqual(registros[1]['vecinos']['cantidad'], 1)
        self.assertFalse(registros[1]['vecinos']['es_ultimo_intento'])
        self.assertEqual(registros[-1]['vecinos'], registros[1]['vecinos'])
        self.assertEqual(registros[0]['presencia']['eventos_en_memoria'][0]['tipo'], 'referencia_inicial')
        self.assertEqual(registros[1]['presencia']['asociaciones'][0]['estado'], 'indeterminado')
        self.assertEqual(registros[-1]['presencia'], registros[1]['presencia'])


class PruebasResumenVecinos(unittest.TestCase):
    def ejecutar(self, lecturas, contextos=None, *, capacidad=100, retencion=600):
        self.tiempo = Tiempo()
        self.arp = Mock(side_effect=lecturas)
        self.contexto = Mock(side_effect=[contexto(c) for c in contextos] if contextos else None,
                             return_value=contexto())
        self.c = CoordinadorARP(
            ConfiguracionBackend(memoria=ConfiguracionMemoria(capacidad, retencion)),
            reloj=self.tiempo.reloj, parada=self.tiempo,
            consultar_arp=self.arp, consultar_contexto=self.contexto,
        )
        self.c.ejecutar(ciclos=len(lecturas))
        return self.c.consultar_resumen()

    def tabla(self, texto, *, parcial=False):
        from backend.arp import interpretar_tabla_arp
        dato = lectura('lectura_parcial' if parcial else 'lectura_correcta')
        dato.update(interpretar_tabla_arp(texto))
        return dato

    def test_clasificacion_existente_excluye_categorias_y_separa_incompletas(self):
        texto = '\n'.join([
            '? (192.0.2.20) at 2:0:0:0:0:20 on en0 [ethernet]',
            '? (192.0.2.21) at (incomplete) on en0 [ethernet]',
            '? (192.0.2.1) at (incomplete) on en0 [ethernet]',
            '? (192.0.2.10) at 2:0:0:0:0:10 on en0 [ethernet]',
            '? (192.0.2.255) at ff:ff:ff:ff:ff:ff on en0 [ethernet]',
            '? (224.0.0.1) at 1:0:5e:0:0:1 on en0 [ethernet]',
            '? (198.51.100.20) at 2:0:0:0:0:20 on en0 [ethernet]',
            '? (192.0.2.22) at 2:0:0:0:0:22 on en1 [ethernet]',
        ])
        resumen = self.ejecutar([self.tabla(texto)])
        vecinos = resumen['vecinos']
        self.assertEqual(vecinos['cantidad'], 2)
        self.assertEqual(vecinos['resolucion_mac'], {'resuelta': 1, 'incompleta': 1})
        self.assertEqual(vecinos['unidad'], 'filas_arp_categoria_vecino')
        self.assertEqual(vecinos['id_observacion'], resumen['calidad']['id_ultima_utilizable'])
        self.assertTrue(vecinos['es_ultimo_intento'])

    def test_no_fusiona_mac_ni_filas_repetidas_ni_suma_ciclos(self):
        linea = '? (192.0.2.20) at 2:0:0:0:0:20 on en0 [ethernet]\n'
        misma_mac = '? (192.0.2.21) at 2:0:0:0:0:20 on en0 [ethernet]\n'
        resumen = self.ejecutar([lectura(), self.tabla(linea * 2 + misma_mac)])
        self.assertEqual(resumen['vecinos']['cantidad'], 3)
        self.assertEqual(resumen['vecinos']['resolucion_mac']['resuelta'], 3)

    def test_cero_vecinos_es_diferente_de_fuente_sin_datos(self):
        gateway = '? (192.0.2.1) at 2:0:0:0:0:1 on en0 [ethernet]'
        resumen = self.ejecutar([self.tabla(gateway)])
        self.assertEqual(resumen['vecinos']['cantidad'], 0)
        self.assertEqual(resumen['calidad']['calidad_fuente'], 'completa')
        resumen = self.ejecutar([lectura('sin_datos_visibles')])
        self.assertIsNone(resumen['vecinos']['cantidad'])
        self.assertIsNone(resumen['vecinos']['resolucion_mac'])
        self.assertIsNone(resumen['vecinos']['fin_captura'])

    def test_fallo_conserva_recuento_y_fecha_anteriores_con_estado_actual(self):
        for estado in ('error_recoleccion', 'sin_datos_visibles', 'error_interpretacion'):
            resumen = self.ejecutar([lectura(), lectura(estado)])
            vecinos = resumen['vecinos']
            self.assertEqual(vecinos['cantidad'], 1)
            self.assertFalse(vecinos['es_ultimo_intento'])
            self.assertEqual(vecinos['fin_captura'], lectura()['fin_captura'])
            self.assertEqual(resumen['calidad']['estado_ultimo_intento'], estado)
            self.assertEqual(resumen['calidad']['antiguedad_s'], 5)

    def test_parcial_no_se_presenta_como_recuento_completo(self):
        resumen = self.ejecutar([lectura(), lectura('lectura_parcial')])
        self.assertEqual(resumen['vecinos']['cantidad'], 1)
        self.assertEqual(resumen['vecinos']['estado_observacion'], 'observacion_parcial')
        self.assertEqual(resumen['calidad']['calidad_fuente'], 'parcial')
        gateway = '? (192.0.2.1) at (incomplete) on en0 [ethernet]\nincorrecto'
        resumen = self.ejecutar([self.tabla(gateway, parcial=True)])
        self.assertEqual(resumen['vecinos']['cantidad'], 0)
        self.assertEqual(resumen['calidad']['calidad_fuente'], 'parcial')

    def test_envejecimiento_sin_recolectar_y_expiracion(self):
        self.ejecutar([lectura()], retencion=100)
        self.tiempo.ahora += 90
        resumen = self.c.consultar_resumen()
        self.assertEqual(resumen['vecinos']['cantidad'], 1)
        self.assertEqual(resumen['calidad']['vigencia'], 'desactualizado')
        self.tiempo.ahora += 10
        resumen = self.c.consultar_resumen()
        self.assertIsNone(resumen['vecinos']['cantidad'])
        self.assertEqual(resumen['calidad']['vigencia'], 'no_disponible')
        self.arp.assert_called_once()
        self.contexto.assert_called_once()

    def test_capacidad_y_contextos_no_recuperan_recuentos_incompatibles(self):
        resumen = self.ejecutar([lectura(), lectura('error_recoleccion')], capacidad=1)
        self.assertIsNone(resumen['vecinos']['cantidad'])
        resumen = self.ejecutar([lectura(), lectura(), lectura('error_recoleccion')],
                               [CONTEXTO, OTRO, CONTEXTO])
        self.assertIsNone(resumen['vecinos']['cantidad'])
        anterior = self.c.memoria.historial()[0]['id_contexto']
        resumen = self.c.consultar_resumen(id_contexto=anterior)
        self.assertEqual(resumen['vecinos']['cantidad'], 1)
        self.assertFalse(resumen['calidad']['es_contexto_actual'])
        resumen = self.ejecutar([lectura(), lectura()], [CONTEXTO, None])
        self.assertIsNone(resumen['vecinos']['cantidad'])

    def test_resumen_no_modifica_memoria_y_usa_una_sola_instantanea(self):
        self.ejecutar([lectura()])
        antes = self.c.memoria.historial()
        with patch.object(self.c.memoria, 'instantanea_temporal',
                          wraps=self.c.memoria.instantanea_temporal) as copiar:
            resumen = self.c.consultar_resumen()
        copiar.assert_called_once_with(id_ejecucion=self.c.id_ejecucion)
        resumen['vecinos']['cantidad'] = 100
        self.assertEqual(self.c.memoria.historial(), antes)
        self.assertEqual(self.c.consultar_resumen()['vecinos']['cantidad'], 1)
        self.assertIsNone(self.c.consultar_resumen(id_contexto='inexistente')['vecinos']['cantidad'])
        self.assertIsNone(CoordinadorARP().consultar_resumen()['vecinos']['cantidad'])
