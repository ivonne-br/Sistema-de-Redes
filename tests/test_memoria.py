import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from concurrent.futures import ThreadPoolExecutor

from backend.arp import crear_contexto_arp
from backend.configuracion import ConfiguracionMemoria, ConfiguracionBackend, interpretar_configuracion
from backend.descubrimiento import observar_arp
from backend.memoria import MemoriaObservaciones, clave_contexto

CONTEXTO = crear_contexto_arp('en0', '192.0.2.10/24', '192.0.2.1')
TEXTO = '? (192.0.2.20) at 2:0:0:0:0:20 on en0 [ethernet]\n'


def observacion(texto=TEXTO, contexto=CONTEXTO):
    return observar_arp(texto, contexto=contexto)


class PruebasConfiguracionMemoria(unittest.TestCase):
    def test_predeterminados_json_parcial_y_opciones(self):
        self.assertEqual(ConfiguracionBackend().memoria, ConfiguracionMemoria(100, 600))
        self.assertEqual(interpretar_configuracion('{}').memoria, ConfiguracionMemoria())
        self.assertEqual(interpretar_configuracion('{"memoria":{"capacidad":2}}').memoria, ConfiguracionMemoria(2, 600))
        config = interpretar_configuracion('{"memoria":{"capacidad":3,"retencion_s":10}}')
        self.assertEqual(config.memoria, ConfiguracionMemoria(3, 10))
        with self.assertRaises(FrozenInstanceError):
            config.memoria.capacidad = 4

    def test_rechaza_limites_y_estructuras_invalidos(self):
        for campo in ('capacidad', 'retencion_s'):
            for valor in (True, False, 0, -1, 1.2, '3', None):
                with self.subTest(campo=campo, valor=valor), self.assertRaises((ValueError, TypeError)):
                    ConfiguracionMemoria(**{campo: valor})
        for texto in ('{"memoria":null}', '{"memoria":[]}', '{"memoria":{"otra":1}}',
                      '{"memoria":{"capacidad":true}}', '{"memoria":{"capacidad":1,"capacidad":2}}'):
            with self.subTest(texto=texto), self.assertRaises((ValueError, TypeError)):
                interpretar_configuracion(texto)
        with self.assertRaises(TypeError):
            ConfiguracionBackend(memoria={})
        with self.assertRaises(TypeError):
            MemoriaObservaciones(configuracion={})
        with self.assertRaises(TypeError):
            MemoriaObservaciones(reloj=3)


class PruebasMemoria(unittest.TestCase):
    def setUp(self):
        self.ahora = 100.0
        self.memoria = MemoriaObservaciones(ConfiguracionMemoria(2, 10), reloj=lambda: self.ahora)

    def test_vacia(self):
        self.assertIsNone(self.memoria.ultima())
        self.assertEqual(self.memoria.historial(), [])
        self.assertEqual(self.memoria.estadisticas()['conservadas'], 0)

    def test_capacidad_orden_y_duplicado_no_desplaza(self):
        a, b, c = observacion(), observacion(), observacion()
        self.memoria.guardar(a)
        self.memoria.guardar(b)
        with self.assertRaises(ValueError):
            self.memoria.guardar(a)
        self.assertEqual(self.memoria.historial(), [a, b])
        self.memoria.guardar(c)
        self.assertEqual(self.memoria.historial(), [b, c])
        self.assertEqual(self.memoria.ultima(), c)
        self.assertEqual(self.memoria.estadisticas()['descartadas_por_capacidad'], 1)

    def test_copias_protegen_original_lecturas_y_datos_anidados(self):
        a = observacion()
        antes = deepcopy(a)
        self.memoria.guardar(a)
        a['entradas'][0]['marcas'].append('modificada')
        a['contexto']['interfaz'] = 'en9'
        ultima = self.memoria.ultima()
        ultima['resumen']['vecinos_candidatos'] = 99
        historial = self.memoria.historial()
        historial[0]['entradas'].clear()
        self.assertEqual(self.memoria.ultima(), antes)

    def test_retencion_frontera_exacta_y_contadores_no_duplicados(self):
        a = observacion()
        self.memoria.guardar(a)
        self.ahora = 109.999
        self.assertEqual(self.memoria.ultima(), a)
        self.ahora = 110
        self.assertIsNone(self.memoria.ultima())
        self.assertEqual(self.memoria.historial(), [])
        self.assertEqual(self.memoria.estadisticas()['descartadas_por_antiguedad'], 1)
        self.assertEqual(self.memoria.estadisticas()['descartadas_por_capacidad'], 0)

    def test_purga_antes_de_guardar_y_retiene_por_insercion_no_fecha_del_texto(self):
        a = observacion()
        a['inicio_procesamiento'] = '2000-01-01T00:00:00+00:00'
        self.memoria.guardar(a)
        self.ahora = 105
        b = observacion()
        self.memoria.guardar(b)
        self.ahora = 110
        c = observacion()
        self.memoria.guardar(c)
        self.assertEqual(self.memoria.historial(), [b, c])
        stats = self.memoria.estadisticas()
        self.assertEqual(stats['descartadas_por_antiguedad'], 1)
        self.assertEqual(stats['descartadas_por_capacidad'], 0)

    def test_filtros_por_contexto_y_ausencia_de_contexto(self):
        memoria = MemoriaObservaciones(ConfiguracionMemoria(10, 600))
        a = observacion()
        cambios = [dict(CONTEXTO, interfaz='en1'),
                   crear_contexto_arp('en0', '192.0.2.11/24', '192.0.2.1'),
                   crear_contexto_arp('en0', '192.0.2.10/25', '192.0.2.1'),
                   crear_contexto_arp('en0', '192.0.2.10/24', '192.0.2.2')]
        memoria.guardar(a)
        for contexto in cambios:
            memoria.guardar(observacion(contexto=contexto))
            self.assertNotEqual(clave_contexto(CONTEXTO), clave_contexto(contexto))
        error = observar_arp(TEXTO, consulta_contexto={'estado':'sin_ruta','contexto':None})
        memoria.guardar(error)
        self.assertEqual(memoria.historial(contexto=CONTEXTO), [a])
        self.assertEqual(memoria.ultima(contexto=CONTEXTO), a)
        self.assertEqual(memoria.historial(contexto=None), [error])
        self.assertEqual(memoria.ultima(), error)
        self.assertIsNone(memoria.ultima(contexto=dict(CONTEXTO, interfaz='en8')))
        self.assertEqual(len(memoria.historial()), 6)
        equivalente = crear_contexto_arp('en0', '192.0.2.10/255.255.255.0', '192.0.2.1')
        self.assertEqual(memoria.ultima(contexto=equivalente), a)

    def test_todos_los_estados_se_conservan_sin_reemplazar_fallo_por_exito(self):
        memoria = MemoriaObservaciones(ConfiguracionMemoria(10, 600))
        for texto in (TEXTO, TEXTO+'incorrecto', '', 'incorrecto'):
            dato = observacion(texto)
            memoria.guardar(dato)
            self.assertEqual(memoria.ultima(), dato)
        fallo = observar_arp(TEXTO, consulta_contexto={'estado':'sin_ipv4','contexto':None})
        memoria.guardar(fallo)
        self.assertEqual(memoria.ultima()['estado'], 'error_contexto')
        self.assertIsNone(memoria.ultima()['resumen']['vecinos_candidatos'])
        self.assertEqual([o['estado'] for o in memoria.historial()], [
            'observacion_correcta', 'observacion_parcial', 'sin_entradas', 'error_interpretacion', 'error_contexto'])

    def test_entrada_invalida_no_desplaza_historial(self):
        a = observacion()
        self.memoria.guardar(a)
        for cambio in ({'version_esquema':True}, {'version_esquema':2}, {'id_observacion':''},
                       {'estado':'otro'}, {'estado':[]}, {'entradas':{}}, {'errores':None},
                       {'resumen':[]}, {'contexto':None}, {'estado':'error_contexto'}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.memoria.guardar({**a, **cambio})
        for dato in (None, {}, []):
            with self.assertRaises(ValueError):
                self.memoria.guardar(dato)
        self.assertEqual(self.memoria.historial(), [a])

    def test_memoria_nueva_no_comparte_historial(self):
        self.memoria.guardar(observacion())
        self.assertEqual(MemoriaObservaciones().historial(), [])

    def test_inserciones_concurrentes_respetan_capacidad_y_no_pierden_descartes(self):
        memoria = MemoriaObservaciones(ConfiguracionMemoria(5, 600))
        datos = [observacion() for _ in range(20)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(memoria.guardar, datos))
        self.assertEqual(len(memoria.historial()), 5)
        self.assertEqual(memoria.estadisticas()['descartadas_por_capacidad'], 15)
