"""Lectores independientes y consultas concurrentes sin iniciar recolección."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from backend.__main__ import main
from backend.configuracion import ConfiguracionBackend
from backend.consulta import ConsultaARP
from backend.coordinador import CoordinadorARP
from backend.memoria import MemoriaObservaciones
from test_coordinador import Tiempo, contexto, lectura, CONTEXTO, OTRO


class PruebasConsultaARP(unittest.TestCase):
    def crear(self):
        self.tiempo = Tiempo()
        self.arp = Mock(return_value=lectura())
        self.contexto = Mock(return_value=contexto())
        self.c = CoordinadorARP(reloj=self.tiempo.reloj, parada=self.tiempo,
                                consultar_arp=self.arp, consultar_contexto=self.contexto)
        return self.c.consulta

    def test_lectores_vacios_no_arrancan_capturas(self):
        consulta = self.crear()
        otro = ConsultaARP(self.c.memoria, id_ejecucion=self.c.id_ejecucion)
        for lector in (consulta, otro):
            for _ in range(3):
                self.assertIsNone(lector.resumen()['vecinos']['cantidad'])
                self.assertEqual(lector.calidad()['vigencia'], 'no_disponible')
        self.arp.assert_not_called()
        self.contexto.assert_not_called()
        self.c.ejecutar(ciclos=1)
        self.arp.assert_called_once()

    def test_lector_se_construye_sin_coordinador_y_valida_dependencias(self):
        memoria = MemoriaObservaciones()
        consulta = ConsultaARP(memoria, id_ejecucion='ejecucion-local')
        self.assertEqual(consulta.resumen()['presencia']['asociaciones'], [])
        with self.assertRaises(TypeError):
            ConsultaARP(None, id_ejecucion='x')
        with self.assertRaises(TypeError):
            ConsultaARP(memoria, id_ejecucion='x', configuracion={})
        for identificador in (None, '', ' ', 1):
            with self.assertRaises(ValueError):
                ConsultaARP(memoria, id_ejecucion=identificador)

    def test_varios_lectores_comparten_datos_sin_mutarlos_ni_renovar_fechas(self):
        consulta = self.crear()
        self.c.ejecutar(ciclos=1)
        otro = ConsultaARP(self.c.memoria, id_ejecucion=self.c.id_ejecucion)
        antes = consulta.resumen()
        with ThreadPoolExecutor(max_workers=4) as pool:
            resultados = list(pool.map(lambda _: otro.resumen(), range(12)))
        self.assertTrue(all(r == antes for r in resultados))
        resultados[0]['presencia']['asociaciones'][0]['mac'] = 'modificada'
        resultados[0]['vecinos']['cantidad'] = 900
        self.assertEqual(consulta.resumen(), antes)
        self.tiempo.ahora += 90
        despues = otro.resumen()
        self.assertEqual(despues['calidad']['vigencia'], 'desactualizado')
        self.assertEqual(despues['vecinos']['fin_captura'], antes['vecinos']['fin_captura'])
        self.tiempo.ahora += 510
        self.assertIsNone(consulta.resumen()['vecinos']['cantidad'])
        self.arp.assert_called_once()
        self.contexto.assert_called_once()

    def test_consultar_durante_lectura_lenta_no_espera_ni_ve_datos_incompletos(self):
        consulta = self.crear()
        entrando, liberar = Event(), Event()
        finales, errores = [], []
        llamadas = 0

        def leer():
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                entrando.set()
                if not liberar.wait(3):
                    raise RuntimeError('La prueba no liberó la fuente.')
                return lectura('error_recoleccion')
            return lectura()

        def ejecutar():
            try:
                finales.append(self.c.ejecutar(ciclos=2))
            except Exception as error:
                errores.append(error)

        self.arp.side_effect = leer
        hilo = Thread(target=ejecutar)
        hilo.start()
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            self.assertTrue(entrando.wait(2))
            resultados = [pool.submit(consulta.resumen) for _ in range(4)]
            for futuro in resultados:
                dato = futuro.result(timeout=1)
                self.assertEqual(dato['calidad']['estado_ultimo_intento'], 'observacion_correcta')
                self.assertEqual(dato['vecinos']['cantidad'], 1)
                self.assertEqual(dato['presencia']['id_ultimo_intento'], dato['calidad']['id_ultimo_intento'])
            self.assertEqual(self.arp.call_count, 2)
        finally:
            liberar.set()
            hilo.join(3)
            pool.shutdown(wait=True)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(errores, [])
        self.assertEqual(finales[0]['ciclos_completados'], 2)
        self.assertEqual(consulta.resumen()['calidad']['estado_ultimo_intento'], 'error_recoleccion')
        self.assertFalse(consulta.resumen()['vecinos']['es_ultimo_intento'])
        self.assertEqual(self.arp.call_count, 2)

    def test_filtra_ejecucion_y_contexto_sin_reclasificar(self):
        consulta = self.crear()
        self.contexto.side_effect = [contexto(CONTEXTO), contexto(OTRO), contexto(CONTEXTO)]
        self.c.ejecutar(ciclos=3)
        primero = self.c.memoria.historial()[0]
        resumen = consulta.resumen(id_contexto=primero['id_contexto'])
        self.assertFalse(resumen['calidad']['es_contexto_actual'])
        self.assertEqual(resumen['vecinos']['id_observacion'], primero['id_observacion'])
        otra = ConsultaARP(self.c.memoria, id_ejecucion='otra-ejecucion')
        self.assertIsNone(otra.resumen()['vecinos']['cantidad'])
        self.assertEqual(otra.resumen()['presencia']['eventos_en_memoria'], [])
        self.assertEqual(self.arp.call_count, 3)

    def test_compatibilidad_y_una_sola_instantanea_para_resumen(self):
        consulta = self.crear()
        self.c.ejecutar(ciclos=1)
        self.assertEqual(consulta.resumen(), self.c.consultar_resumen())
        self.assertEqual(consulta.calidad(), self.c.consultar_calidad())
        with patch.object(self.c.memoria, 'instantanea_temporal',
                          wraps=self.c.memoria.instantanea_temporal) as copia:
            consulta.resumen()
        copia.assert_called_once_with(id_ejecucion=self.c.id_ejecucion)
        for valor in ('', ' ', 2, False):
            with self.assertRaises(ValueError):
                consulta.resumen(id_contexto=valor)

    def test_cli_usa_lector_sin_delegados_del_coordinador(self):
        self.crear()
        salida = io.StringIO()
        with patch('backend.__main__.CoordinadorARP', return_value=self.c), \
             patch.object(self.c, 'consultar_resumen', side_effect=AssertionError('Usar el lector')), \
             patch('sys.argv', ['backend', 'monitorear-arp', '--ciclos', '1']), \
             redirect_stdout(salida), redirect_stderr(io.StringIO()):
            main()
        lineas = [json.loads(linea) for linea in salida.getvalue().splitlines()]
        self.assertEqual([d['tipo'] for d in lineas], ['observacion_arp', 'fin_monitoreo_arp'])
        self.assertEqual(lineas[0]['vecinos']['cantidad'], 1)
        self.arp.assert_called_once()
