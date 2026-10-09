"""Coordinación con fuentes y reloj controlados: ninguna consulta real de red."""

import io
import json
import signal
import unittest
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from threading import Event, Thread
from unittest.mock import Mock, patch

from backend.__main__ import main
from backend.arp import crear_contexto_arp, interpretar_tabla_arp
from backend.configuracion import ConfiguracionBackend, ConfiguracionMemoria, interpretar_configuracion
from backend.coordinador import CoordinadorARP

CONTEXTO = crear_contexto_arp('en0', '192.0.2.10/24', '192.0.2.1')
OTRO = crear_contexto_arp('en1', '198.51.100.10/24', '198.51.100.1')


def contexto(valor=CONTEXTO):
    return {'estado': 'contexto_correcto' if valor else 'sin_ruta',
            'contexto': deepcopy(valor), 'detalle': None if valor else 'Sin ruta.',
            'inicio': '2026-10-09T00:00:00+00:00', 'fin': '2026-10-09T00:00:01+00:00'}


def lectura(estado='lectura_correcta'):
    tabla = interpretar_tabla_arp('? (192.0.2.20) at 2:0:0:0:0:20 on en0 [ethernet]')
    if estado in ('error_recoleccion', 'sin_datos_visibles', 'error_interpretacion'):
        tabla['entradas'] = []
    if estado in ('lectura_parcial', 'error_interpretacion'):
        tabla['errores'] = [{'numero_registro': 2, 'detalle': 'Registro truncado.'}]
    return {**tabla, 'estado': estado, 'fuente': 'cache_arp_sysctl_macos',
            'inicio_captura': '2026-10-09T00:00:01+00:00',
            'fin_captura': '2026-10-09T00:00:02+00:00',
            'bytes_recibidos': None if estado == 'error_recoleccion' else 100,
            'detalle': 'Fallo de prueba.' if estado == 'error_recoleccion' else None}


class Tiempo:
    def __init__(self):
        self.ahora = 100.0
        self.parado = False
        self.esperas = []

    def reloj(self):
        return self.ahora

    def is_set(self):
        return self.parado

    def set(self):
        self.parado = True

    def wait(self, segundos):
        self.esperas.append(segundos)
        self.ahora += segundos
        return self.parado


class PruebasCoordinador(unittest.TestCase):
    def setUp(self):
        self.tiempo = Tiempo()
        self.contexto = Mock(return_value=contexto())
        self.arp = Mock(return_value=lectura())
        self.coordinador = CoordinadorARP(
            consultar_contexto=self.contexto, consultar_arp=self.arp,
            reloj=self.tiempo.reloj, parada=self.tiempo,
        )

    def test_ciclos_comparten_memoria_y_guardan_antes_de_emitir(self):
        emisiones = []

        def emitir(dato):
            self.assertEqual(self.coordinador.memoria.ultima(), dato)
            emisiones.append(deepcopy(dato))
            dato['entradas'].clear()  # La emisión no puede alterar lo almacenado.

        fin = self.coordinador.ejecutar(ciclos=3, emitir=emitir)
        self.assertEqual(self.contexto.call_count, 3)
        self.assertEqual(self.arp.call_count, 3)
        self.assertEqual(self.tiempo.esperas, [5, 5])
        self.assertEqual(fin['memoria']['conservadas'], 3)
        self.assertEqual(fin['ciclos_con_incidencias'], 0)
        self.assertEqual([d['ciclo'] for d in emisiones], [1, 2, 3])
        self.assertEqual(len({d['id_observacion'] for d in emisiones}), 3)
        self.assertEqual(len({d['id_contexto'] for d in emisiones}), 1)
        self.assertEqual(emisiones[0]['entradas'][0]['categoria'], 'vecino')
        self.assertEqual(len(self.coordinador.memoria.ultima()['entradas']), 1)

    def test_ciclo_lento_y_emision_lenta_no_acumulan_trabajo(self):
        inicios = []

        def consultar():
            inicios.append(self.tiempo.ahora)
            self.tiempo.ahora += 12
            return lectura()

        self.arp.side_effect = consultar
        self.coordinador.ejecutar(ciclos=3, emitir=lambda _: setattr(self.tiempo, 'ahora', self.tiempo.ahora + 2))
        self.assertEqual(inicios, [100, 119, 138])
        self.assertEqual(self.tiempo.esperas, [5, 5])

    def test_despertar_anticipado_respeta_plazo_monotonico(self):
        def esperar(segundos):
            self.tiempo.esperas.append(segundos)
            self.tiempo.ahora += min(2, segundos)
        self.tiempo.wait = esperar
        self.coordinador.ejecutar(ciclos=2)
        self.assertEqual(self.tiempo.esperas, [5, 3, 1])

    def test_parada_antes_del_inicio_no_inventa_intento(self):
        self.coordinador.detener()
        fin = self.coordinador.ejecutar()
        self.assertEqual(fin['ciclos_completados'], 0)
        self.assertEqual(fin['motivo'], 'detenido')
        self.contexto.assert_not_called()
        self.arp.assert_not_called()

    def test_parada_durante_espera(self):
        self.tiempo.wait = lambda _: self.coordinador.detener()
        fin = self.coordinador.ejecutar()
        self.assertEqual(fin['ciclos_completados'], 1)
        self.assertEqual(self.arp.call_count, 1)

    def test_parada_durante_consulta_termina_y_conserva_ciclo(self):
        def consultar():
            self.coordinador.detener()
            return lectura()
        self.arp.side_effect = consultar
        fin = self.coordinador.ejecutar()
        self.assertEqual(fin['ciclos_completados'], 1)
        self.assertEqual(self.coordinador.memoria.ultima()['estado'], 'observacion_correcta')
        self.assertEqual(self.tiempo.esperas, [])

    def test_rechaza_segunda_ejecucion_incluso_desde_un_ciclo(self):
        def emitir(_):
            with self.assertRaises(RuntimeError):
                self.coordinador.ejecutar(ciclos=1)
        self.coordinador.ejecutar(ciclos=1, emitir=emitir)
        with self.assertRaises(RuntimeError):
            self.coordinador.ejecutar(ciclos=1)
        self.assertEqual(self.arp.call_count, 1)

    def test_todos_los_estados_fallos_simultaneos_y_recuperacion(self):
        estados = ['lectura_correcta', 'error_recoleccion', 'sin_datos_visibles',
                   'lectura_parcial', 'error_interpretacion', 'lectura_correcta',
                   'error_recoleccion', 'lectura_correcta']
        self.arp.side_effect = [lectura(e) for e in estados]
        self.contexto.side_effect = [contexto() for _ in range(5)] + [contexto(None), contexto(None), contexto()]
        fin = self.coordinador.ejecutar(ciclos=8)
        historial = self.coordinador.memoria.historial()
        self.assertEqual([o['estado'] for o in historial], [
            'observacion_correcta', 'error_recoleccion', 'sin_datos_visibles',
            'observacion_parcial', 'error_interpretacion', 'error_contexto',
            'error_recoleccion', 'observacion_correcta'])
        self.assertEqual(fin['ciclos_con_incidencias'], 6)
        for indice in (1, 2, 6):
            self.assertIsNone(historial[indice]['resumen']['vecinos_candidatos'])
            self.assertEqual(historial[indice]['entradas'], [])
        self.assertEqual(historial[6]['consulta_contexto']['estado'], 'sin_ruta')
        self.assertEqual(historial[6]['consulta_arp']['detalle'], 'Fallo de prueba.')
        self.assertEqual(historial[3]['errores'][0]['numero_registro'], 2)
        self.assertNotEqual(historial[0]['id_contexto'], historial[-1]['id_contexto'])

    def test_ultimo_fallo_no_oculta_exito_ni_lo_reutiliza(self):
        self.arp.side_effect = [lectura(), lectura('error_recoleccion')]
        self.coordinador.ejecutar(ciclos=2)
        self.assertEqual(self.coordinador.memoria.ultima()['estado'], 'error_recoleccion')
        self.assertEqual(len(self.coordinador.memoria.historial()), 2)

    def test_cambios_a_b_a_y_perdida_contexto_separan_series(self):
        self.contexto.side_effect = [contexto(c) for c in (CONTEXTO, OTRO, CONTEXTO, None, CONTEXTO)]
        self.coordinador.ejecutar(ciclos=5)
        memoria = self.coordinador.memoria
        datos = memoria.historial()
        self.assertEqual(len({d['id_contexto'] for d in datos if d['contexto']}), 4)
        self.assertIsNone(datos[3]['id_contexto'])
        self.assertEqual(len(memoria.historial(contexto=CONTEXTO)), 3)
        self.assertEqual(memoria.historial(id_contexto=datos[2]['id_contexto']), [datos[2]])
        self.assertEqual(memoria.ultima(id_contexto=datos[0]['id_contexto']), datos[0])
        self.assertEqual(memoria.historial(id_contexto=None), [datos[3]])
        # Una observación v1 antigua sin id_contexto no pertenece a ese tramo.
        antigua = deepcopy(datos[0])
        antigua.pop('id_contexto')
        antigua['id_observacion'] = 'observacion-anterior'
        memoria.guardar(antigua)
        self.assertEqual(memoria.historial(id_contexto=None), [datos[3]])
        self.assertEqual(memoria.ultima(id_contexto=None), datos[3])

    def test_retencion_y_capacidad_se_aplican_durante_monitoreo(self):
        for limite, retencion, descartes in ((2, 600, 'descartadas_por_capacidad'), (10, 10, 'descartadas_por_antiguedad')):
            tiempo = Tiempo()
            c = CoordinadorARP(ConfiguracionBackend(memoria=ConfiguracionMemoria(limite, retencion)),
                               consultar_contexto=self.contexto, consultar_arp=self.arp,
                               reloj=tiempo.reloj, parada=tiempo)
            fin = c.ejecutar(ciclos=3)
            self.assertEqual(fin['memoria']['conservadas'], 2)
            self.assertEqual(fin['memoria'][descartes], 1)
            self.assertEqual([d['ciclo'] for d in c.memoria.historial()], [2, 3])

    def test_validacion_antes_de_consultar(self):
        for valor in (True, 0, -1, 1.5, '2'):
            with self.assertRaises(ValueError):
                self.coordinador.ejecutar(ciclos=valor)
        self.contexto.assert_not_called()
        for valor in (True, None, '5', 0, -1, float('inf'), float('nan'), 86401):
            with self.assertRaises((ValueError, TypeError)):
                ConfiguracionBackend(intervalo_arp_s=valor)
        self.assertEqual(interpretar_configuracion('{"intervalo_arp_s":0.5}').intervalo_arp_s, 0.5)

    def ejecutar_cli(self, argumentos):
        salida, errores = io.StringIO(), io.StringIO()
        codigo = 0
        with patch('sys.argv', ['backend', 'monitorear-arp', *argumentos]), \
             patch('backend.__main__.CoordinadorARP', return_value=self.coordinador), \
             redirect_stdout(salida), redirect_stderr(errores):
            try:
                main()
            except SystemExit as error:
                codigo = error.code
        return codigo, salida.getvalue(), errores.getvalue()

    def test_cli_json_lines_y_fallo_acumulado_aunque_se_recupere(self):
        self.arp.side_effect = [lectura('error_recoleccion'), lectura()]
        codigo, salida, errores = self.ejecutar_cli(['--ciclos', '2'])
        registros = [json.loads(linea) for linea in salida.splitlines()]
        self.assertEqual(codigo, 1)
        self.assertEqual([r['tipo'] for r in registros], ['observacion_arp', 'observacion_arp', 'fin_monitoreo_arp'])
        self.assertEqual(registros[-1]['ciclos_con_incidencias'], 1)
        self.assertIn('error_recoleccion', errores)
        self.assertNotIn('192.0.2.', errores)

    def test_cli_senales_cierran_y_restauran_manejadores(self):
        for senal in (signal.SIGINT, signal.SIGTERM):
            self.setUp()
            anteriores = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
            def consultar():
                signal.raise_signal(senal)
                return lectura()
            self.arp.side_effect = consultar
            codigo, salida, _ = self.ejecutar_cli([])
            registros = [json.loads(linea) for linea in salida.splitlines()]
            self.assertEqual(codigo, 130)
            self.assertEqual(registros[-1]['motivo'], 'detenido')
            self.assertEqual(registros[-1]['memoria']['conservadas'], 1)
            self.assertEqual({s: signal.getsignal(s) for s in anteriores}, anteriores)

    def test_cli_rechaza_argumentos_sin_consultas(self):
        for args in (['--ciclos', '0'], ['--intervalo', 'nan'], ['--intervalo', '-2']):
            codigo, salida, _ = self.ejecutar_cli(args)
            self.assertEqual(codigo, 2)
            self.assertEqual(salida, '')
        self.contexto.assert_not_called()
        self.arp.assert_not_called()

    def test_cli_intervalo_prevalece_sobre_archivo_y_exito_termina_en_cero(self):
        salida = io.StringIO()
        with patch('sys.argv', ['backend', '--config', 'config/ejemplo.json',
                                'monitorear-arp', '--intervalo', '0.25', '--ciclos', '1']), \
             patch('backend.__main__.CoordinadorARP', return_value=self.coordinador) as fabrica, \
             redirect_stdout(salida), redirect_stderr(io.StringIO()):
            main()
        self.assertEqual(fabrica.call_args.args[0].intervalo_arp_s, 0.25)
        self.assertEqual(json.loads(salida.getvalue().splitlines()[-1])['motivo'], 'limite_ciclos')

    def test_memoria_rechaza_fallos_incoherentes(self):
        self.arp.return_value = lectura('error_recoleccion')
        self.coordinador.ejecutar(ciclos=1)
        original = self.coordinador.memoria.ultima()
        for modificar in (
            lambda o: o.update(consulta_arp={}),
            lambda o: o.update(consulta_arp=None),
            lambda o: o.update(entradas=lectura()['entradas']),
            lambda o: o['resumen'].update(vecinos_candidatos=0),
            lambda o: o.update(contexto=None),
        ):
            dato = deepcopy(original)
            dato['id_observacion'] = 'otro'
            modificar(dato)
            with self.assertRaises(ValueError):
                self.coordinador.memoria.guardar(dato)
        self.assertEqual(self.coordinador.memoria.historial(), [original])

    def test_instancias_separadas_no_comparten_memoria_ni_ids(self):
        otra = CoordinadorARP(consultar_contexto=self.contexto, consultar_arp=self.arp)
        self.coordinador.ejecutar(ciclos=1)
        self.assertEqual(otra.memoria.historial(), [])
        otra.ejecutar(ciclos=1)
        a, b = self.coordinador.memoria.ultima(), otra.memoria.ultima()
        self.assertNotEqual(a['id_ejecucion'], b['id_ejecucion'])
        self.assertNotEqual(a['id_contexto'], b['id_contexto'])

    def test_parada_desde_otro_hilo_y_rechazo_concurrente(self):
        entrando, liberar = Event(), Event()
        finales = []

        def consultar():
            entrando.set()
            if not liberar.wait(2):
                raise RuntimeError('La prueba no liberó la fuente.')
            return lectura()

        c = CoordinadorARP(consultar_contexto=self.contexto, consultar_arp=consultar)
        hilo = Thread(target=lambda: finales.append(c.ejecutar()))
        hilo.start()
        try:
            self.assertTrue(entrando.wait(2))
            with self.assertRaises(RuntimeError):
                c.ejecutar()
            c.detener()
        finally:
            liberar.set()
            hilo.join(2)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(finales[0]['ciclos_completados'], 1)
        self.assertEqual(finales[0]['motivo'], 'detenido')
