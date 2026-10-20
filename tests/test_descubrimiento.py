import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch
from uuid import UUID

from backend.__main__ import main
from backend.arp import crear_contexto_arp
from backend.descubrimiento import observar_arp

CONTEXTO = crear_contexto_arp('en0', '192.0.2.10/24', '192.0.2.1')


def linea(ip='192.0.2.20', mac='2:0:0:0:0:1', interfaz='en0'):
    return f'? ({ip}) at {mac} on {interfaz} [ethernet]\n'


class PruebasObservacion(unittest.TestCase):
    def test_modelo_identidad_tiempos_y_copia_del_contexto(self):
        original = deepcopy(CONTEXTO)
        resultado = observar_arp(linea(), contexto=original)
        self.assertEqual(resultado['version_esquema'], 1)
        self.assertEqual(UUID(resultado['id_observacion']).version, 4)
        self.assertNotEqual(resultado['id_observacion'], observar_arp(linea(), contexto=original)['id_observacion'])
        self.assertLessEqual(datetime.fromisoformat(resultado['inicio_procesamiento']), datetime.fromisoformat(resultado['fin_procesamiento']))
        self.assertIsNone(resultado['momento_captura_origen'])
        self.assertEqual(resultado['fuente'], 'texto_arp_stdin')
        self.assertEqual(resultado['fuente_contexto'], 'manual')
        self.assertEqual(resultado['contexto']['mascara'], '255.255.255.0')
        self.assertEqual(original, CONTEXTO)
        original['interfaz'] = 'en9'
        self.assertEqual(resultado['contexto']['interfaz'], 'en0')
        json.dumps(resultado, allow_nan=False)

    def test_resumen_separa_categorias_sin_fusionar_mac_ni_descartar_incompletas(self):
        texto = ''.join([
            linea(), linea('192.0.2.21'), linea('192.0.2.22', '(incomplete)'),
            linea('192.0.2.1'), linea('192.0.2.10'), linea('192.0.2.0'),
            linea('192.0.2.255'), linea('224.0.0.251'), linea('198.51.100.1'),
            linea(interfaz='en1'),
        ])
        r = observar_arp(texto, contexto=CONTEXTO)
        self.assertEqual(r['estado'], 'observacion_correcta')
        self.assertEqual(r['resumen']['entradas'], 10)
        self.assertEqual(r['resumen']['vecinos_candidatos'], 3)
        self.assertEqual(r['resumen']['por_categoria'], {
            'vecino':3, 'gateway':1, 'equipo_propio':1, 'direccion_red':1,
            'broadcast':1, 'multicast':1, 'fuera_subred':1, 'otra_interfaz':1,
        })
        self.assertEqual(r['resumen']['resolucion_mac'], {'resuelta':9, 'incompleta':1})
        self.assertEqual(len(r['entradas']), 10)
        self.assertEqual(r['entradas'][0]['mac'], r['entradas'][1]['mac'])
        self.assertEqual(r['entradas'][2]['categoria'], 'vecino')
        self.assertEqual(r['entradas'][2]['resolucion_mac'], 'incompleta')

    def test_estados_y_errores_por_linea(self):
        casos = [('', 'sin_entradas', 0, 0), ('\n  \n', 'sin_entradas', 0, 0),
                 ('incorrecta', 'error_interpretacion', 0, 1),
                 (linea() + 'incorrecta', 'observacion_parcial', 1, 1)]
        for texto, estado, entradas, errores in casos:
            with self.subTest(estado=estado):
                r = observar_arp(texto, contexto=CONTEXTO)
                self.assertEqual(r['estado'], estado)
                self.assertEqual(r['resumen']['entradas'], entradas)
                self.assertEqual(r['resumen']['errores'], errores)
                self.assertEqual(r['resumen']['vecinos_candidatos'], entradas)
                if errores:
                    self.assertEqual(r['errores'][0]['numero_linea'], entradas + 1)

    def test_consulta_automatica_se_conserva_sin_compartir_mutaciones(self):
        consulta = {'estado':'contexto_correcto', 'contexto':deepcopy(CONTEXTO),
                    'inicio':'2026-10-09T15:00:00+00:00', 'fin':'2026-10-09T15:00:01+00:00'}
        antes = deepcopy(consulta)
        r = observar_arp(linea(), consulta_contexto=consulta)
        self.assertEqual(consulta, antes)
        self.assertEqual(r['fuente_contexto'], 'contexto_ipv4_macos')
        self.assertEqual(r['consulta_contexto']['inicio'], antes['inicio'])
        r['contexto']['interfaz'] = 'en9'
        self.assertEqual(r['consulta_contexto']['contexto']['interfaz'], 'en0')
        self.assertEqual(consulta, antes)

    def test_error_contexto_conserva_datos_sin_inventar_cero_candidatos(self):
        for estado in ('sin_ruta', 'sin_ipv4', 'error_recoleccion', 'error_interpretacion'):
            with self.subTest(estado=estado):
                consulta = {'estado':estado, 'contexto':None, 'detalle':'fallo controlado'}
                r = observar_arp(linea() + 'incorrecta', consulta_contexto=consulta)
                self.assertEqual(r['estado'], 'error_contexto')
                self.assertEqual(r['consulta_contexto'], consulta)
                self.assertIsNone(r['contexto'])
                self.assertIsNone(r['resumen']['por_categoria'])
                self.assertIsNone(r['resumen']['vecinos_candidatos'])
                self.assertEqual(r['resumen']['entradas'], 1)
                self.assertEqual(r['resumen']['errores'], 1)
                self.assertNotIn('categoria', r['entradas'][0])

    def test_entradas_inconsistentes_se_rechazan(self):
        casos = [{}, {'contexto':CONTEXTO, 'consulta_contexto':{}},
                 {'contexto':{}}, {'contexto':{**CONTEXTO, 'subred':'198.51.100.0/24'}},
                 {'contexto':{**CONTEXTO, 'mascara':'255.255.0.0'}},
                 {'consulta_contexto':[]}, {'consulta_contexto':{'estado':'desconocido'}},
                 {'consulta_contexto':{'estado':'contexto_correcto', 'contexto':None}},
                 {'consulta_contexto':{'estado':'sin_ruta', 'contexto':CONTEXTO}}]
        for opciones in casos:
            with self.subTest(opciones=opciones), self.assertRaises(ValueError):
                observar_arp(linea(), **opciones)
        with self.assertRaises(TypeError):
            observar_arp(None, contexto=CONTEXTO)


class PruebasCliDescubrir(unittest.TestCase):
    def test_manual_y_eventos_sin_consultar_red(self):
        salida, errores = io.StringIO(), io.StringIO()
        with (patch('sys.argv', ['backend', 'descubrir', '--desde-stdin', '--interfaz', 'en0', '--ipv4-local', '192.0.2.10/24']),
              patch('sys.stdin', io.StringIO(linea() + 'incorrecta')),
              patch('backend.contexto_red.subprocess.run') as proceso,
              redirect_stdout(salida), redirect_stderr(errores), self.assertRaises(SystemExit) as error):
            main()
        proceso.assert_not_called()
        self.assertEqual(error.exception.code, 1)
        r = json.loads(salida.getvalue())
        self.assertEqual(r['estado'], 'observacion_parcial')
        self.assertEqual(r['resumen']['vecinos_candidatos'], 1)
        self.assertIn('WARNING', errores.getvalue())
        self.assertIn('operacion=descubrir', errores.getvalue())
        self.assertNotIn('192.0.2.', errores.getvalue())

    def test_auto_pasa_limite_y_conserva_fallo(self):
        for estado in ('contexto_correcto', 'sin_ruta'):
            salida = io.StringIO()
            consulta = {'estado':estado, 'contexto':CONTEXTO if estado == 'contexto_correcto' else None}
            with (self.subTest(estado=estado),
                  patch('sys.argv', ['backend', 'descubrir', '--desde-stdin', '--contexto-auto']),
                  patch('sys.stdin', io.StringIO(linea())),
                  patch('backend.__main__.consultar_contexto_ipv4', return_value=consulta) as consultar,
                  redirect_stdout(salida), redirect_stderr(io.StringIO())):
                if estado == 'contexto_correcto':
                    main()
                else:
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, 1)
            consultar.assert_called_once_with(5)
            self.assertEqual(json.loads(salida.getvalue())['estado'], 'observacion_correcta' if estado == 'contexto_correcto' else 'error_contexto')

    def test_opciones_invalidas_no_consumen_stdin(self):
        casos = [[], ['--desde-stdin'], ['--desde-stdin', '--interfaz', 'en0'],
                 ['--desde-stdin', '--contexto-auto', '--interfaz', 'en0']]
        for opciones in casos:
            with (self.subTest(opciones=opciones), patch('sys.argv', ['backend', 'descubrir', *opciones]),
                  patch('sys.stdin') as entrada,
                  patch('backend.__main__.consultar_contexto_ipv4') as consultar,
                  redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error):
                main()
            self.assertEqual(error.exception.code, 2)
            consultar.assert_not_called()
            entrada.read.assert_not_called()

    def test_texto_vacio_no_es_error_y_texto_invalido_si(self):
        for texto, estado, codigo in (('', 'sin_entradas', 0), ('incorrecto', 'error_interpretacion', 1)):
            salida = io.StringIO()
            with (patch('sys.argv', ['backend', 'descubrir', '--desde-stdin', '--interfaz', 'en0', '--ipv4-local', '192.0.2.10/24']),
                  patch('sys.stdin', io.StringIO(texto)), redirect_stdout(salida), redirect_stderr(io.StringIO())):
                if codigo:
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, codigo)
                else:
                    main()
            self.assertEqual(json.loads(salida.getvalue())['estado'], estado)
