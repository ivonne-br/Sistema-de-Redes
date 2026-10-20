import io
import json
import logging
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from backend.__main__ import main
from backend.configuracion import (
    ConfiguracionBackend, ConfiguracionSonda,
    cargar_configuracion, interpretar_configuracion,
)
from backend.eventos import configurar_logging, registrar_resultado


class PruebasConfiguracionBackend(unittest.TestCase):
    def test_predeterminados_parciales_e_inmutabilidad(self):
        self.assertEqual(cargar_configuracion(), ConfiguracionBackend())
        self.assertEqual(interpretar_configuracion('{}'), ConfiguracionBackend())
        config = interpretar_configuracion('{"sonda":{"espera_ms":2000},"limite_contexto_s":8,"nivel_log":"INFO"}')
        self.assertEqual(config.sonda, ConfiguracionSonda(2000, 5))
        self.assertEqual(config.limite_contexto_s, 8)
        self.assertEqual(config.nivel_log, "INFO")
        with self.assertRaises(FrozenInstanceError):
            config.limite_contexto_s = 9

    def test_rechaza_json_tipos_claves_duplicadas_y_limites(self):
        casos = ['{', '[]', 'null', 'true', '1',
                 '{"desconocida":1}', '{"sonda":null}', '{"sonda":[]}',
                 '{"sonda":{"espera":1000}}', '{"sonda":{"espera_ms":true}}',
                 '{"sonda":{"espera_ms":0}}', '{"sonda":{"espera_ms":5000}}',
                 '{"limite_contexto_s":false}', '{"limite_contexto_s":0}',
                 '{"limite_contexto_s":-1}', '{"limite_contexto_s":1.2}',
                 '{"limite_contexto_s":"5"}', '{"nivel_log":"info"}',
                 '{"nivel_log":null}', '{"nivel_log":[]}',
                 '{"nivel_log":"INFO","nivel_log":"ERROR"}',
                 '{"sonda":{"espera_ms":1,"espera_ms":2}}',
                 '{"limite_contexto_s":NaN}', '{"limite_contexto_s":Infinity}']
        for texto in casos:
            with self.subTest(texto=texto), self.assertRaises((ValueError, TypeError)):
                interpretar_configuracion(texto)

    def test_lectura_utf8_archivo_inexistente_y_no_legible(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'config.json'
            ruta.write_text('{"nivel_log":"INFO"}', encoding='utf-8')
            self.assertEqual(cargar_configuracion(ruta).nivel_log, 'INFO')
            ruta.write_bytes(b'\xff')
            with self.assertRaisesRegex(ValueError, 'UTF-8'):
                cargar_configuracion(ruta)
            with self.assertRaises(ValueError):
                cargar_configuracion(Path(carpeta) / 'ausente')
            with self.assertRaises(ValueError):
                cargar_configuracion(carpeta)

    def test_validacion_construccion_directa(self):
        for opciones in ({'sonda': {}}, {'limite_contexto_s': True}, {'limite_contexto_s': 0}, {'nivel_log': 20}):
            with self.subTest(opciones=opciones), self.assertRaises((ValueError, TypeError)):
                ConfiguracionBackend(**opciones)


class PruebasEventos(unittest.TestCase):
    def test_reconfiguracion_no_duplica_ni_altera_logger_raiz(self):
        errores = io.StringIO()
        raiz = logging.getLogger()
        nivel, handlers = raiz.level, list(raiz.handlers)
        with redirect_stderr(errores):
            configurar_logging('INFO')
            logger = configurar_logging('INFO')
            registrar_resultado(logger, 'contexto-red', {'estado': 'contexto_correcto'})
        self.assertEqual(len(errores.getvalue().splitlines()), 1)
        self.assertRegex(errores.getvalue(), r'^\d{4}-\d{2}-\d{2}T.*Z INFO backend.cli')
        self.assertEqual((raiz.level, raiz.handlers), (nivel, handlers))

    def test_niveles_y_datos_no_incluidos(self):
        casos = [
            ('sonda', {'estado': 'respuesta_valida'}, 'INFO'),
            ('sonda', {'estado': 'sin_respuesta'}, 'WARNING'),
            ('sonda', {'estado': 'error_recoleccion'}, 'ERROR'),
            ('contexto-red', {'estado': 'sin_ruta'}, 'ERROR'),
            ('arp', {'entradas': [], 'errores': []}, 'INFO'),
            ('arp', {'entradas': [{'ipv4': '192.0.2.1'}], 'errores': []}, 'INFO'),
            ('arp', {'entradas': [], 'errores': [{'detalle': 'texto recibido'}]}, 'WARNING'),
            ('arp', {'entradas': [], 'errores': [], 'consulta_contexto': {'estado': 'sin_ipv4'}}, 'ERROR'),
        ]
        for operacion, resultado, nivel in casos:
            errores = io.StringIO()
            resultado['detalle'] = 'dato que no debe aparecer'
            with self.subTest(operacion=operacion, resultado=resultado), redirect_stderr(errores):
                registrar_resultado(configurar_logging('INFO'), operacion, resultado)
            self.assertIn(nivel, errores.getvalue())
            for dato in ('192.0.2.1', 'texto recibido', 'dato que no debe aparecer'):
                self.assertNotIn(dato, errores.getvalue())

    def test_nivel_predeterminado_oculta_exitos(self):
        errores = io.StringIO()
        with redirect_stderr(errores):
            registrar_resultado(configurar_logging(), 'sonda', {'estado': 'respuesta_valida'})
        self.assertEqual(errores.getvalue(), '')


class PruebasCliBaseComun(unittest.TestCase):
    def test_config_invalida_detiene_operacion_antes_de_leer_o_consultar(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'config.json'
            ruta.write_text('{"limite_contexto_s":false}')
            for argumentos in (['contexto-red'], ['sonda', '192.0.2.1'], ['arp', '--desde-stdin']):
                with (self.subTest(argumentos=argumentos),
                      patch('sys.argv', ['backend', '--config', str(ruta), *argumentos]),
                      patch('sys.stdin') as entrada,
                      patch('backend.__main__.consultar_contexto_ipv4') as contexto,
                      patch('backend.__main__.ejecutar_sonda') as sonda,
                      redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()) as salida,
                      self.assertRaises(SystemExit) as error):
                    main()
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(salida.getvalue(), '')
                entrada.read.assert_not_called()
                contexto.assert_not_called()
                sonda.assert_not_called()

    def test_config_llega_a_sonda_y_contexto_json_separado_de_logs(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'config.json'
            ruta.write_text('{"sonda":{"espera_ms":2000,"limite_proceso_s":7},"limite_contexto_s":9,"nivel_log":"INFO"}')
            casos = [(['sonda', '192.0.2.1'], 'ejecutar_sonda', {'estado':'respuesta_valida'}, ('192.0.2.1', ConfiguracionSonda(2000, 7))),
                     (['contexto-red'], 'consultar_contexto_ipv4', {'estado':'contexto_correcto'}, (9,))]
            for argumentos, funcion, resultado, llamada in casos:
                salida, errores = io.StringIO(), io.StringIO()
                with (self.subTest(argumentos=argumentos),
                      patch('sys.argv', ['backend', '--config', str(ruta), *argumentos]),
                      patch('backend.__main__.' + funcion, return_value=resultado) as ejecutar,
                      redirect_stdout(salida), redirect_stderr(errores)):
                    main()
                ejecutar.assert_called_once_with(*llamada)
                self.assertEqual(json.loads(salida.getvalue()), resultado)
                self.assertIn('INFO', errores.getvalue())
                self.assertNotIn('INFO', salida.getvalue())

    def test_config_contexto_auto_y_fallo_conservan_json_y_codigo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'config.json'
            ruta.write_text('{"limite_contexto_s":8}')
            salida, errores = io.StringIO(), io.StringIO()
            with (patch('sys.argv', ['backend', '--config', str(ruta), 'arp', '--desde-stdin', '--contexto-auto']),
                  patch('sys.stdin', io.StringIO('? (192.0.2.1) at (incomplete) on en0 [ethernet]')),
                  patch('backend.__main__.consultar_contexto_ipv4', return_value={'estado': 'sin_ruta', 'contexto': None}) as consulta,
                  redirect_stdout(salida), redirect_stderr(errores), self.assertRaises(SystemExit) as error):
                main()
            consulta.assert_called_once_with(8)
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(len(json.loads(salida.getvalue())['entradas']), 1)
            self.assertIn('ERROR', errores.getvalue())
            self.assertNotIn('192.0.2.1', errores.getvalue())
