"""Comprueba explicaciones con capturas sintéticas: sin sondas ni acceso a redes.

Incluye ventanas, cambio de contexto, duplicados y errores de adquisición para
evitar conclusiones de recuperación o caída que los datos no sustentan.
"""
from copy import deepcopy
import unittest
from backend.analisis import analizar_web, analizar_observaciones, comparar_respuesta


def captura():
    def fila(edad, estado='correcto'):
        return {'tipo': 'https', 'destino': 'https://example.test', 'estado': estado,
                'fin': '2026-10-15T12:00:00+00:00', 'antiguedad_s': edad, 'vigencia': 'vigente'}
    return {'estado': 'en_espera', 'id_contexto': 'A', 'resultados': [fila(10)],
            'historial': [{'id_serie': str(i), 'id_contexto': 'A', 'resultados': [fila(edad)]}
                          for i, edad in enumerate([10, 80, 160, 310, 400, 500])]}


class PruebasAnalisis(unittest.TestCase):
    def test_compara_intentos_sin_inventar_caida_y_no_modifica_entrada(self):
        dato = captura()
        dato['historial'][0]['resultados'][0]['estado'] = 'tiempo_agotado'
        original = deepcopy(dato)
        r = analizar_web(dato)
        self.assertEqual(r['comparacion']['estado'], 'comparable')
        self.assertIn('más a menudo', r['comparacion']['mensaje'])
        self.assertEqual(r['comparacion']['reciente'], {'intentos': 3, 'no_correctos': 1})
        self.assertEqual(dato, original)

    def test_falta_de_muestras_no_es_cero_problemas(self):
        dato = captura(); dato['historial'] = dato['historial'][:2]
        self.assertEqual(analizar_web(dato)['comparacion']['estado'], 'insuficiente')

    def test_no_compara_otra_red_destino_duplicados_ni_errores_de_medicion(self):
        for variante in ('red', 'destino', 'duplicado', 'error'):
            with self.subTest(variante=variante):
                dato = captura()
                s = dato['historial'][0]
                if variante == 'red': s['id_contexto'] = 'B'
                if variante == 'destino': s['resultados'][0]['destino'] = 'https://otro.test'
                if variante == 'duplicado': dato['historial'].append(deepcopy(s))
                if variante == 'error': s['resultados'][0]['estado'] = 'error_medicion'
                self.assertEqual(analizar_web(dato)['comparacion']['estado'], 'insuficiente')

    def test_edades_limites_y_huecos_no_se_rellenan(self):
        dato = captura()
        dato['historial'][0]['resultados'][0]['antiguedad_s'] = 300
        dato['historial'][3]['resultados'][0]['antiguedad_s'] = 600
        r = analizar_web(dato)['comparacion']
        self.assertEqual(r['reciente']['intentos'], 2)
        self.assertEqual(r['anterior']['intentos'], 3)
        self.assertEqual(r['estado'], 'insuficiente')

    def test_dato_antiguo_monitor_detenido_y_error_no_muestran_exito(self):
        for variante in ('antiguo', 'detenido', 'sin_red', 'error'):
            dato = captura()
            if variante == 'antiguo': dato['resultados'][0]['vigencia'] = 'desactualizado'
            if variante == 'detenido': dato['estado'] = 'detenido'
            if variante == 'sin_red': dato['id_contexto'] = None
            if variante == 'error': dato['resultados'][0]['estado'] = 'error_medicion'
            r = analizar_web(dato)
            self.assertEqual(r['estado'], 'sin_datos')
            self.assertIsNone(r['comparacion'])

    def test_seguridad_y_mejoria_no_prometen_recuperacion(self):
        dato = captura(); dato['resultados'][0]['estado'] = 'certificado_invalido'
        self.assertIn('no la ignores', analizar_web(dato)['orientacion'])
        dato['historial'][3]['resultados'][0]['estado'] = 'error_conexion'
        self.assertIn('menos a menudo', analizar_web(dato)['comparacion']['mensaje'])


def capturas_recorrido():
    """Entrega dos monitores sintéticos de la misma red con UUID independientes."""
    web = captura()
    web['contexto'] = {'interfaz': 'en0', 'ipv4_local': '192.168.50.2/24',
                       'subred': '192.168.50.0/24', 'gateway': '192.168.50.1'}
    conexion = {'estado': 'en_espera', 'id_contexto': 'B',
                'contexto': deepcopy(web['contexto']), 'destinos': []}
    for tipo, ip in [('router', '192.168.50.1'), ('externo', '1.1.1.1')]:
        conexion['destinos'].append({'tipo': tipo, 'ipv4': ip, 'fin': '2026-10-15T12:00:00Z',
            'antiguedad_s': 12, 'vigencia': 'vigente', 'calidad': 'completa',
            'realizadas': 3, 'programadas': 3, 'respuestas': 3, 'sin_respuesta': 0,
            'errores': 0, 'omitidas': 0})
    return web, conexion


class PruebasRecorrido(unittest.TestCase):
    def test_orienta_cada_combinacion_sin_atribuir_causas(self):
        for local, externo, texto in [(3, 0, 'la prueba de fuera no respondió'),
                                     (0, 0, 'no recibieron respuesta'),
                                     (0, 3, 'aunque el equipo de tu red no contestó'),
                                     (3, 3, 'Hubo respuestas dentro y fuera')]:
            with self.subTest(local=local, externo=externo):
                web, conexion = capturas_recorrido()
                web['resultados'][0]['estado'] = 'tiempo_agotado'
                for fila, respuestas in zip(conexion['destinos'], (local, externo)):
                    fila.update(respuestas=respuestas, sin_respuesta=3-respuestas)
                original = deepcopy((web, conexion))
                r = analizar_observaciones(web, conexion)['recorrido']
                self.assertEqual(r['estado'], 'observado')
                self.assertIn(texto, r['titulo'])
                self.assertEqual(len(r['evidencia']), 2)
                self.assertEqual((web, conexion), original)

    def test_visita_exitosa_no_se_convierte_en_caida_por_silencio(self):
        web, conexion = capturas_recorrido()
        for fila in conexion['destinos']:
            fila.update(respuestas=0, sin_respuesta=3)
        r = analizar_observaciones(web, conexion)['recorrido']
        self.assertEqual(r['titulo'], 'Se pudo llegar al sitio de prueba.')
        self.assertIn('no demuestran', r['explicacion'])

    def test_no_cruza_redes_edades_ni_resultados_incompletos(self):
        for caso in ('red', 'sin_contexto', 'detenido', 'antiguo', 'separados', 'nan',
                     'parcial', 'errores', 'incoherente', 'duplicado', 'gateway', 'error_web'):
            with self.subTest(caso=caso):
                web, conexion = capturas_recorrido()
                fila = conexion['destinos'][0]
                if caso == 'red': conexion['contexto']['gateway'] = '192.168.50.254'
                if caso == 'sin_contexto': conexion['id_contexto'] = None
                if caso == 'detenido': conexion['estado'] = 'detenido'
                if caso == 'antiguo': fila['antiguedad_s'] = 90
                if caso == 'separados': fila['antiguedad_s'] = 41
                if caso == 'nan': fila['antiguedad_s'] = float('nan')
                if caso == 'parcial': fila['calidad'] = 'parcial'
                if caso == 'errores': fila['errores'] = 1
                if caso == 'incoherente': fila['respuestas'] = 4
                if caso == 'duplicado': conexion['destinos'].append(deepcopy(fila))
                if caso == 'gateway': fila['ipv4'] = '192.168.50.254'
                if caso == 'error_web': web['resultados'][0]['estado'] = 'error_medicion'
                r = analizar_observaciones(web, conexion)['recorrido']
                self.assertEqual(r['estado'], 'sin_datos')
                self.assertEqual(r['evidencia'], [])

    def test_conserva_orientacion_de_seguridad(self):
        web, conexion = capturas_recorrido()
        web['resultados'][0]['estado'] = 'certificado_invalido'
        self.assertIn('no la ignores', analizar_observaciones(web, conexion)['recorrido']['orientacion'])


def captura_tiempos():
    """Simula dos ventanas con tiempos distintos; no realiza consultas de red."""
    _, conexion = capturas_recorrido()
    conexion['historial'] = []
    for i, edad in enumerate((10, 80, 160, 310, 400, 500)):
        filas = deepcopy(conexion['destinos'])
        for fila in filas:
            fila['rtt_ms'] = {'muestras': 3, 'promedio': 40 if edad < 300 else 20}
        conexion['historial'].append({'id_serie': str(i), 'id_contexto': 'B',
                                      'antiguedad_s': edad, 'destinos': filas})
    return conexion


class PruebasCompararTiempos(unittest.TestCase):
    def test_compara_ponderando_cada_respuesta_y_separa_destinos(self):
        datos = captura_tiempos()
        f = datos['historial'][0]['destinos'][0]
        f.update(respuestas=1, sin_respuesta=2, rtt_ms={'muestras': 1, 'promedio': 10})
        original = deepcopy(datos)
        local, externo = comparar_respuesta(datos)
        self.assertEqual(local['estado'], 'comparable')
        self.assertAlmostEqual(local['reciente']['promedio_ms'], 35.714)
        self.assertEqual(externo['reciente']['promedio_ms'], 40)
        self.assertEqual(local['anterior']['promedio_ms'], 20)
        self.assertIn('tardaron más', local['mensaje'])
        self.assertEqual(datos, original)

    def test_menos_espera_e_igualdad_no_afirman_red_sana(self):
        for promedio, texto in ((10, 'tardaron menos'), (20, 'fue igual')):
            datos = captura_tiempos()
            for serie in datos['historial'][:3]:
                serie['destinos'][0]['rtt_ms']['promedio'] = promedio
            self.assertIn(texto, comparar_respuesta(datos)[0]['mensaje'])

    def test_silencio_no_se_convierte_en_cero_y_falta_de_cobertura_impide_comparar(self):
        for caso in ('silencio', 'errores'):
            datos = captura_tiempos()
            for serie in datos['historial'][:3]:
                f = serie['destinos'][0]
                if caso == 'silencio':
                    f.update(respuestas=0, sin_respuesta=3, rtt_ms={'muestras': 0, 'promedio': None})
                else:
                    f.update(respuestas=2, errores=1, calidad='parcial', rtt_ms={'muestras': 2, 'promedio': 20})
            r = comparar_respuesta(datos)[0]
            self.assertEqual(r['estado'], 'insuficiente')
            if caso == 'silencio': self.assertIsNone(r['reciente']['promedio_ms'])
            else: self.assertEqual(r['reciente']['respuestas'], 6)

    def test_excluye_red_distinta_duplicados_otro_destino_y_datos_invalidos(self):
        for caso in ('red', 'duplicado', 'destino', 'nan', 'edad', 'muestras', 'recuentos'):
            with self.subTest(caso=caso):
                datos = captura_tiempos()
                serie = datos['historial'][0]
                fila = serie['destinos'][0]
                if caso == 'red': serie['id_contexto'] = 'otra'
                if caso == 'duplicado': datos['historial'].append(deepcopy(serie))
                if caso == 'destino': fila['ipv4'] = '192.168.50.254'
                if caso == 'nan': fila['rtt_ms']['promedio'] = float('nan')
                if caso == 'edad': serie['antiguedad_s'] = -1
                if caso == 'muestras': fila['rtt_ms']['muestras'] = 8
                if caso == 'recuentos': fila['respuestas'] = 8
                self.assertEqual(comparar_respuesta(datos)[0]['estado'], 'insuficiente')

    def test_limites_ventanas_y_caducidad_tras_reposo(self):
        datos = captura_tiempos()
        datos['historial'][0]['antiguedad_s'] = 300
        datos['historial'][3]['antiguedad_s'] = 600
        r = comparar_respuesta(datos)[0]
        self.assertEqual(r['reciente']['series'], 2)
        self.assertEqual(r['anterior']['series'], 3)
        datos['destinos'][0]['antiguedad_s'] = 90
        self.assertEqual(comparar_respuesta(datos)[0]['estado'], 'sin_datos')
        datos['estado'] = 'detenido'
        self.assertEqual(comparar_respuesta(datos), [])

    def test_comparacion_no_depende_del_monitor_web(self):
        r = analizar_observaciones({'estado': 'desactivada'}, captura_tiempos())
        self.assertEqual(r['tiempos_respuesta'][0]['estado'], 'comparable')
        self.assertEqual(r['recorrido']['estado'], 'sin_datos')


class PruebasAnalisisIntegrado(unittest.TestCase):
    def test_seguridad_tiene_prioridad_sobre_silencios_y_fallos_previos(self):
        web, conexion = capturas_recorrido()
        web['resultados'][0]['estado'] = 'certificado_invalido'
        for f in conexion['destinos']:
            f.update(respuestas=0, sin_respuesta=3)
        r = analizar_observaciones(web, conexion)
        self.assertEqual(r['principal']['estado'], 'atencion')
        self.assertIn('segura', r['principal']['titulo'])
        self.assertIn('no la ignores', r['principal']['orientacion'])

    def test_fallos_repetidos_y_respuesta_posterior_sin_promesa_de_recuperacion(self):
        web = captura()
        for i in (1, 3):
            web['historial'][i]['resultados'][0]['estado'] = 'tiempo_agotado'
        original = deepcopy(web)
        r = analizar_observaciones(web, {})
        self.assertEqual(r['incidencias']['fallos'], 2)
        self.assertEqual(r['incidencias']['fallos_anteriores'], 2)
        self.assertIn('más de una vez', r['incidencias']['mensaje'])
        self.assertIn('respondió ahora', r['principal']['titulo'])
        self.assertIn('no asegura', r['principal']['orientacion'])
        self.assertEqual(web, original)

    def test_historial_se_ordena_por_edad_no_fecha_y_no_incluye_otra_red(self):
        web = captura()
        web['historial'].reverse()
        web['historial'][0]['resultados'][0]['fin'] = '2000-01-01T00:00:00Z'
        web['historial'][1]['id_contexto'] = 'otra-red'
        web['historial'][2]['resultados'][0]['estado'] = 'error_medicion'
        r = analizar_observaciones(web, {})['incidencias']
        self.assertEqual(r['errores_medicion'], 1)
        self.assertEqual(r['fallos'], 0)
        self.assertEqual(len(r['eventos']), 5)
        self.assertEqual(r['eventos'][0]['antiguedad_s'], 10)

    def test_no_publica_incidencias_actuales_tras_reposo_o_error(self):
        for caso in ('reposo', 'error', 'detenido'):
            web = captura()
            web['historial'][1]['resultados'][0]['estado'] = 'tiempo_agotado'
            if caso == 'reposo': web['resultados'][0]['antiguedad_s'] = 120
            if caso == 'error': web['resultados'][0]['estado'] = 'error_medicion'
            if caso == 'detenido': web['estado'] = 'detenido'
            r = analizar_observaciones(web, {})
            self.assertEqual(r['principal']['estado'], 'sin_datos')
            self.assertEqual(r['incidencias']['eventos'], [])

    def test_duplicados_huecos_y_limites_no_crean_fallos(self):
        web = captura()
        f = web['historial'][0]['resultados'][0]
        f['estado'] = 'tiempo_agotado'
        web['historial'].append(deepcopy(web['historial'][0]))
        web['historial'][1]['resultados'][0]['antiguedad_s'] = 600
        web['historial'][2]['resultados'][0]['antiguedad_s'] = float('nan')
        r = analizar_observaciones(web, {})['incidencias']
        self.assertEqual(r['fallos'], 0)
        self.assertEqual(len(r['eventos']), 3)

    def test_dns_independiente_no_anula_una_visita_correcta(self):
        web = captura()
        web['resultados'].append({'tipo': 'dns', 'destino': 'otro.test', 'estado': 'error_resolucion',
                                 'fin': '2026-10-15T12:00:00Z', 'antiguedad_s': 10, 'vigencia': 'vigente'})
        r = analizar_observaciones(web, {})
        self.assertEqual(r['nombres']['estado'], 'atencion')
        self.assertIn('La visita funcionó', r['principal']['titulo'])
        web['resultados'][1]['antiguedad_s'] = 120
        self.assertEqual(analizar_observaciones(web, {})['nombres']['estado'], 'sin_datos')
        web['resultados'][1]['antiguedad_s'] = 10
        web['resultados'][0]['estado'] = 'error_medicion'
        r = analizar_observaciones(web, {})
        self.assertEqual(r['principal']['fuente'], 'Búsqueda del nombre de prueba')

    def test_mensajes_distinguen_busqueda_respuesta_inesperada_y_error_interno(self):
        for estado, texto in [('error_resolucion', 'dirección'), ('http_inesperado', 'distinta'),
                              ('error_medicion', 'aplicación')]:
            web = captura()
            web['resultados'][0]['estado'] = estado
            self.assertIn(texto, analizar_observaciones(web, {})['principal']['titulo'])
