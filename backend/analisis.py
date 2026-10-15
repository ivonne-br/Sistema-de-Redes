"""Convierte capturas de conectividad y del monitor web en observaciones para personas no técnicas.

Entrada: estados normalizados de los monitores, con edades calculadas por su reloj.
Salida: explicación, orientación y evidencia para API/Vue. No mide, no accede al
router y no atribuye causas. Compara dos ventanas de cinco minutos, con al menos
tres intentos utilizables en cada una, del mismo contexto y destino. No rellena
huecos ni interpreta errores de ejecución como fallos de Internet.
"""
from collections import Counter
from math import isfinite
from backend.memoria import clave_contexto

_RESULTADOS = {'correcto', 'tiempo_agotado', 'error_conexion', 'certificado_invalido',
               'error_tls', 'http_inesperado', 'error_resolucion', 'sin_direcciones'}


def analizar_observaciones(web, conexion):
    """Reúne análisis públicos y elige una orientación principal sin hacer sondas.

    Prioridad: seguridad, prueba web fallida, fallos anteriores, lectura de nombres
    fallida y resultado actual. No usa datos privados del router ni guarda estado.
    """
    salida = _analizar_recorrido(web, conexion)
    salida['incidencias'] = resumir_incidencias(web)
    salida['nombres'] = analizar_nombres(web)
    principal = {k: salida[k] for k in ('titulo', 'explicacion', 'orientacion')}
    principal.update(estado=salida['estado'], fuente='Visita al sitio de prueba',
                     fecha=salida['ultima_comprobacion'])
    if salida['estado'] == 'observado':
        ultimo = next(f for f in web['resultados'] if f['tipo'] == 'https')
        if ultimo['estado'] in ('certificado_invalido', 'error_tls'):
            principal.update(estado='atencion', titulo='La visita segura al sitio de prueba no pudo completarse.',
                             explicacion='La comprobación encontró un problema al establecer o verificar la conexión segura. Esto no demuestra que alguien esté atacando tu red.')
        elif ultimo['estado'] != 'correcto':
            principal['estado'] = 'atencion'
            if ultimo['estado'] in ('error_resolucion', 'sin_direcciones'):
                principal.update(titulo='No se pudo encontrar la dirección del sitio de prueba.',
                                 explicacion='Para abrir una página, tu computadora necesita encontrar la dirección que corresponde a su nombre. Ese paso falló en esta prueba.',
                                 orientacion='Prueba abrir otra página conocida. Si también falla, consulta al encargado de la red o a tu proveedor con estos resultados. No cambies ajustes todavía.')
            elif ultimo['estado'] == 'http_inesperado':
                principal.update(titulo='El sitio respondió de una forma distinta a la esperada.',
                                 explicacion='Hubo una respuesta, pero no fue la que usa esta aplicación para comprobar el acceso. No confirma una caída ni que la red exija iniciar sesión.',
                                 orientacion='Abre una página conocida en tu navegador. Si aparece un aviso para acceder a esta red, consulta las instrucciones de su responsable.')
            elif salida['recorrido']['estado'] == 'observado':
                principal.update({k: salida['recorrido'][k] for k in ('explicacion', 'orientacion')})
        elif salida['incidencias']['fallos_anteriores']:
            principal.update(estado='observar', titulo='El sitio respondió ahora, pero hubo pruebas con problemas antes.',
                             explicacion=salida['incidencias']['mensaje'],
                             orientacion='Comprueba si tu página o aplicación vuelve a funcionar. Una respuesta correcta no asegura que el problema haya terminado definitivamente.')
        elif salida['nombres']['estado'] == 'atencion':
            principal.update(estado='observar', titulo='La visita funcionó, aunque la búsqueda de un nombre falló.',
                             explicacion='Son pruebas distintas: una logró visitar el sitio y otra no pudo encontrar la dirección del nombre consultado. No significa que todo Internet esté caído.',
                             orientacion='Si algunas páginas no abren, prueba otra conocida y revisa si vuelve a ocurrir.')
    elif salida['nombres']['estado'] == 'atencion':
        principal.update({k: salida['nombres'][k] for k in ('titulo', 'explicacion', 'orientacion')})
        principal.update(estado='observar', fuente='Búsqueda del nombre de prueba', fecha=salida['nombres']['fecha'])
    salida['principal'] = principal
    return salida


def _actual_web(datos, tipo):
    """Devuelve una única lectura vigente del monitor activo o None."""
    if datos.get('estado') not in ('midiendo', 'en_espera') or not datos.get('id_contexto'):
        return None
    filas = [f for f in datos.get('resultados', []) if f.get('tipo') == tipo]
    if len(filas) != 1:
        return None
    f = filas[0]
    edad = f.get('antiguedad_s')
    if (f.get('vigencia') != 'vigente' or type(edad) not in (int, float)
            or not isfinite(edad) or not 0 <= edad < 120):
        return None
    return f


def analizar_nombres(datos):
    """Explica DNS por su propia evidencia, sin asumir que coincide con HTTPS."""
    salida = {'estado': 'sin_datos', 'titulo': 'Falta una búsqueda reciente del nombre de prueba.',
              'explicacion': 'Esta prueba comprueba si la computadora puede encontrar la dirección de un sitio a partir de su nombre.',
              'orientacion': 'Espera nuevas comprobaciones.', 'destino': None, 'fecha': None}
    f = _actual_web(datos, 'dns')
    if f is None:
        return salida
    salida.update(destino=f.get('destino'), fecha=f.get('fin'))
    if f.get('estado') == 'correcto':
        salida.update(estado='observado', titulo='Se encontró la dirección del nombre de prueba.',
                      orientacion='Encontrar la dirección no garantiza que la página abra. Consulta también la prueba de acceso.')
    elif f.get('estado') in ('error_resolucion', 'sin_direcciones', 'tiempo_agotado', 'error_conexion'):
        salida.update(estado='atencion', titulo='La búsqueda del nombre de prueba no pudo completarse.',
                      orientacion='Prueba abrir otra página conocida. Si tampoco abre, consulta al responsable de la red antes de cambiar ajustes.')
    else:
        salida.update(titulo='La aplicación no pudo realizar la búsqueda del nombre.',
                      orientacion='Un error de la aplicación no demuestra un fallo de tu Internet.')
    return salida


def resumir_incidencias(datos):
    """Cuenta intentos únicos de 10 min y muestra su secuencia, sin duración de caída.

    Los errores de medición quedan visibles pero no se cuentan como fallos de
    Internet. Orden por edad continua, no por reloj civil; no rellena huecos.
    """
    salida = {'estado': 'sin_datos', 'fallos': 0, 'fallos_anteriores': 0, 'correctos': 0, 'errores_medicion': 0,
              'mensaje': 'Faltan comprobaciones recientes para describir lo ocurrido.', 'eventos': []}
    actual = _actual_web(datos, 'https')
    if actual is None or actual.get('estado') not in _RESULTADOS:
        return salida
    ids = Counter(s.get('id_serie') for s in datos.get('historial', []))
    eventos = []
    for s in datos.get('historial', []):
        if not s.get('id_serie') or ids[s['id_serie']] != 1 or s.get('id_contexto') != datos['id_contexto']:
            continue
        filas = [f for f in s.get('resultados', []) if f.get('tipo') == 'https' and f.get('destino') == actual.get('destino')]
        if len(filas) != 1:
            continue
        f = filas[0]
        edad = f.get('antiguedad_s')
        if type(edad) not in (int, float) or not isfinite(edad) or not 0 <= edad < 600:
            continue
        estado = f.get('estado')
        if estado not in _RESULTADOS | {'error_medicion'}:
            continue
        eventos.append({'id': s['id_serie'], 'fecha': f.get('fin'), 'antiguedad_s': edad,
                        'resultado': estado, 'destino': f.get('destino'),
                        'descripcion': 'El sitio respondió correctamente.' if estado == 'correcto' else
                        'La aplicación no pudo realizar la prueba.' if estado == 'error_medicion' else
                        'La prueba del sitio no terminó correctamente.'})
    eventos.sort(key=lambda e: e['antiguedad_s'])
    if not eventos:
        return salida
    salida.update(estado='observado', eventos=eventos,
                  fallos=sum(e['resultado'] in _RESULTADOS - {'correcto'} for e in eventos),
                  fallos_anteriores=sum(e['resultado'] in _RESULTADOS - {'correcto'}
                                       and e['antiguedad_s'] > actual['antiguedad_s'] for e in eventos),
                  correctos=sum(e['resultado'] == 'correcto' for e in eventos),
                  errores_medicion=sum(e['resultado'] == 'error_medicion' for e in eventos))
    n = salida['fallos']
    salida['mensaje'] = (f'Hubo {n} pruebas con problemas en los últimos diez minutos. El problema se observó más de una vez.' if n >= 2 else
                         'Hubo una prueba con problemas en los últimos diez minutos.' if n == 1 else
                         'No hubo fallos en las pruebas que pudieron realizarse durante los últimos diez minutos.' if salida['correctos'] else
                         'Solo hay errores de la aplicación; no permiten saber cómo estuvo Internet.')
    return salida


def _analizar_recorrido(web, conexion):
    """Añade orientación del recorrido sin confundir silencio con desconexión.

    Los monitores tienen UUID independientes: se coteja su configuración de red,
    no sus UUID. Se exige una serie completa, reciente y a no más de 30 segundos
    del intento web; ese margen solo permite contrastar evidencia, no atribuir
    causalidad. No se suman ni mezclan los historiales de las fuentes.
    """
    salida = analizar_web(web)
    salida['tiempos_respuesta'] = comparar_respuesta(conexion)
    recorrido = {'estado': 'sin_datos', 'titulo': 'Todavía no podemos señalar dónde revisar.',
                 'explicacion': 'Faltan comprobaciones recientes que podamos comparar entre sí.',
                 'orientacion': 'Espera nuevas comprobaciones. No es necesario reiniciar ni cambiar ajustes por este aviso.',
                 'evidencia': []}
    salida['recorrido'] = recorrido
    if any(d.get('estado') not in ('midiendo', 'en_espera') or not d.get('id_contexto') for d in (web, conexion)):
        return salida
    try:
        contexto = clave_contexto(web.get('contexto'))
        if contexto is None or contexto != clave_contexto(conexion.get('contexto')):
            return salida
    except (ValueError, TypeError, KeyError):
        return salida
    actuales = [r for r in web.get('resultados', []) if r.get('tipo') == 'https']
    locales = [r for r in conexion.get('destinos', []) if r.get('tipo') == 'router']
    externos = [r for r in conexion.get('destinos', []) if r.get('tipo') == 'externo']
    # Solo un destino externo para no seleccionar arbitrariamente entre resultados.
    if len(actuales) != 1 or len(locales) != 1 or len(externos) != 1:
        return salida
    https, local, externo = actuales[0], locales[0], externos[0]
    if https.get('estado') not in _RESULTADOS:
        return salida
    edades = [f.get('antiguedad_s') for f in (https, local, externo)]
    if (any(not isinstance(e, (int, float)) or not isfinite(e) or not 0 <= e < 90 for e in edades)
            or max(edades) - min(edades) > 30
            or any(f.get('vigencia') != 'vigente' for f in (https, local, externo))):
        return salida
    if local.get('ipv4') != conexion['contexto'].get('gateway') or not local.get('ipv4') or not externo.get('ipv4'):
        return salida
    for fila in (local, externo):
        campos = [fila.get(k) for k in ('realizadas', 'programadas', 'respuestas', 'sin_respuesta', 'errores', 'omitidas')]
        if (any(type(n) is not int or n < 0 for n in campos)
                or fila.get('calidad') != 'completa' or fila['errores'] or fila['omitidas']
                or fila['realizadas'] <= 0 or fila['realizadas'] != fila['programadas']
                or fila['respuestas'] + fila['sin_respuesta'] != fila['realizadas']):
            return salida
    recorrido.update(estado='observado', evidencia=[
        {'nombre': nombre, 'fecha': fila.get('fin'), 'respuestas': fila['respuestas'],
         'intentos': fila['realizadas'], 'destino': fila['ipv4']}
        for nombre, fila in (('Dentro de tu red', local), ('Fuera de tu red', externo))])
    if https.get('estado') == 'correcto':
        recorrido.update(titulo='Se pudo llegar al sitio de prueba.',
                         explicacion=('Hubo mensajes sin respuesta, pero la visita al sitio sí funcionó. Esos mensajes no demuestran que hayas perdido Internet.'
                                      if local['sin_respuesta'] or externo['sin_respuesta'] else
                                      'Esta computadora recibió respuestas dentro y fuera de la red y logró visitar el sitio de prueba.'),
                         orientacion='Si solo falla un juego, una página o una videollamada, prueba otro servicio. Si otros funcionan, no hace falta cambiar toda la configuración de tu red.')
    elif local['respuestas'] and not externo['respuestas']:
        recorrido.update(titulo='Dentro de tu red hubo respuesta; la prueba de fuera no respondió.',
                         explicacion='Tu computadora pudo comunicarse con el equipo que le da conexión. La prueba de fuera no respondió, pero aún no sabemos si el problema está en el servicio de Internet o en el destino probado.',
                         orientacion='Prueba dos páginas que uses habitualmente. Si ninguna abre, pregunta si otra persona en la misma red tiene el mismo problema. En una red compartida, avisa al encargado; no reinicies sus equipos.')
    elif not local['respuestas'] and not externo['respuestas']:
        recorrido.update(titulo='Las comprobaciones breves no recibieron respuesta.',
                         explicacion='Esto puede ocurrir si la conexión falla o si la red no permite estas pruebas. No demuestra por sí solo que estés desconectado.',
                         orientacion='Comprueba si aparece el símbolo de Wi-Fi conectado o si el cable está bien colocado. Luego intenta abrir una página. Si abre, la red puede estar limitando estas pruebas.')
    elif not local['respuestas']:
        recorrido.update(titulo='La prueba de fuera respondió, aunque el equipo de tu red no contestó.',
                         explicacion='Algunos equipos no responden a estas comprobaciones. Por eso no podemos decir que el equipo que te da conexión esté averiado.',
                         orientacion='Prueba abrir una página. Si no abre, consulta al encargado de la red con estos resultados antes de cambiar ajustes.')
    else:
        recorrido.update(titulo='Hubo respuestas dentro y fuera de tu red.',
                         explicacion='Los mensajes de prueba recibieron respuesta. Eso no garantiza que las páginas o las aplicaciones funcionen correctamente.',
                         orientacion='Prueba otra página. Si el navegador pide iniciar sesión para usar esta red, sigue las indicaciones de su responsable.')
    if https.get('estado') in ('certificado_invalido', 'error_tls'):
        recorrido['orientacion'] = salida['orientacion']
    return salida


def analizar_web(datos):
    """Evalúa hechos de una sola captura coherente; no conserva análisis anteriores."""
    salida = {'estado': 'sin_datos', 'titulo': 'Todavía no podemos decir cómo va tu conexión.',
              'explicacion': 'Necesitamos nuevas comprobaciones desde esta computadora.',
              'orientacion': 'Espera a que lleguen resultados. No hace falta cambiar nada de tu red.',
              'ultima_comprobacion': None, 'comparacion': None, 'evidencia': [],
              'limite': 'Estas comprobaciones visitan un sitio de prueba. No explican por sí solas por qué falla otra página, un juego o una videollamada.'}
    if not datos.get('id_contexto') or datos.get('estado') not in ('midiendo', 'en_espera'):
        return salida
    ultimos = [r for r in datos.get('resultados', []) if r.get('tipo') == 'https']
    if len(ultimos) != 1:
        return salida
    ultimo = ultimos[0]
    salida['ultima_comprobacion'] = ultimo.get('fin')
    if _actual_web(datos, 'https') is None:
        salida.update(titulo='La información anterior ya no describe este momento.',
                      explicacion='Hace falta una nueva comprobación para saber cómo está tu conexión ahora.')
        return salida
    if ultimo.get('estado') not in _RESULTADOS:
        salida.update(titulo='La aplicación no pudo completar la comprobación.',
                      explicacion='Eso no significa que tu Internet se haya cortado.')
        return salida
    salida['estado'] = 'observado'
    if ultimo['estado'] == 'correcto':
        salida.update(titulo='La última comprobación pudo llegar a Internet.',
                      explicacion='Esta computadora logró comunicarse con el sitio que usamos para probar la conexión.',
                      orientacion='Si una aplicación sigue fallando, prueba abrir otra página. Así podrás comprobar si el problema también ocurre fuera de esa aplicación.')
    else:
        salida.update(titulo='La última comprobación no pudo completarse correctamente.',
                      explicacion='El sitio de prueba no respondió como esperábamos. Todavía no sabemos si ocurre con otros sitios.',
                      orientacion='Abre una página que uses habitualmente. Si tampoco funciona, comprueba que tu computadora siga conectada al Wi-Fi o al cable. En una red compartida, consulta al encargado antes de cambiar ajustes.')
    if ultimo['estado'] in ('certificado_invalido', 'error_tls'):
        salida['orientacion'] = 'Si el navegador muestra una advertencia de seguridad, no la ignores. Comprueba la fecha y hora de tu computadora y consulta al encargado de la red si continúa.'
    series = datos.get('historial', [])
    ids = Counter(s.get('id_serie') for s in series)
    grupos = [[], []]
    for serie in series:
        if (not serie.get('id_serie') or ids[serie['id_serie']] != 1
                or serie.get('id_contexto') != datos['id_contexto']):
            continue
        filas = [r for r in serie.get('resultados', []) if r.get('tipo') == 'https'
                 and r.get('destino') == ultimo.get('destino')]
        if len(filas) != 1:
            continue
        fila = filas[0]
        edad = fila.get('antiguedad_s')
        if (fila.get('estado') not in _RESULTADOS or not isinstance(edad, (int, float))
                or not isfinite(edad) or not 0 <= edad < 600):
            continue
        grupos[0 if edad < 300 else 1].append(fila)
    resumen = [{'intentos': len(g), 'no_correctos': sum(f['estado'] != 'correcto' for f in g)} for g in grupos]
    reciente, anterior = resumen
    comparacion = {'estado': 'insuficiente', 'ventana_s': 300, 'minimo_intentos': 3,
                  'reciente': reciente, 'anterior': anterior,
                  'mensaje': 'Aún no hay suficientes comprobaciones para comparar los últimos cinco minutos con los cinco anteriores.'}
    if all(r['intentos'] >= 3 for r in resumen):
        diferencia = (reciente['no_correctos'] * anterior['intentos']
                      - anterior['no_correctos'] * reciente['intentos'])
        comparacion.update(estado='comparable', mensaje=(
            'El sitio de prueba falló más a menudo en las comprobaciones de los últimos cinco minutos.' if diferencia > 0 else
            'El sitio de prueba falló menos a menudo en las comprobaciones de los últimos cinco minutos.' if diferencia < 0 else
            'No observamos un cambio en la frecuencia de problemas entre ambos periodos.'))
    salida['comparacion'] = comparacion
    salida['evidencia'] = [{'fecha': f.get('fin'), 'resultado': f['estado'],
                           'destino': f.get('destino'), 'periodo': nombre}
                          for nombre, grupo in zip(('reciente', 'anterior'), grupos) for f in grupo]
    return salida


def comparar_respuesta(datos):
    """Compara RTT por destino en dos ventanas de 5 min del mismo monitor.

    Entrada: captura de conectividad; salida: promedios ponderados por respuestas,
    recuentos y orientación para Vue. Exige 3 series, 6 respuestas y 80 % de
    intentos utilizables por ventana. No asigna tiempo a silencios/errores y no
    aplica umbrales de salud: solo describe diferencias entre promedios.
    """
    if datos.get('estado') not in ('midiendo', 'en_espera') or not datos.get('id_contexto'):
        return []
    historial = datos.get('historial', [])
    ids = Counter(s.get('id_serie') for s in historial)
    actuales = datos.get('destinos', [])
    claves = Counter((f.get('tipo'), f.get('ipv4')) for f in actuales)
    salida = []
    for actual in actuales:
        clave = (actual.get('tipo'), actual.get('ipv4'))
        if clave[0] not in ('router', 'externo') or not clave[1] or claves[clave] != 1:
            continue
        resultado = {'nombre': 'Dentro de tu red' if clave[0] == 'router' else 'Fuera de tu red',
                     'destino': clave[1], 'estado': 'insuficiente', 'ultima_comprobacion': actual.get('fin'),
                     'mensaje': 'Todavía faltan comprobaciones para comparar los tiempos de respuesta.',
                     'orientacion': 'Espera más resultados. No necesitas cambiar ajustes por este aviso.',
                     'anterior': None, 'reciente': None}
        salida.append(resultado)
        edad_actual = actual.get('antiguedad_s')
        if (actual.get('vigencia') != 'vigente' or type(edad_actual) not in (int, float)
                or not isfinite(edad_actual) or not 0 <= edad_actual < 90):
            resultado.update(estado='sin_datos', mensaje='Hace falta una comprobación nueva para comparar este momento.')
            continue
        grupos = [[], []]
        for serie in historial:
            edad = serie.get('antiguedad_s')
            if (not serie.get('id_serie') or ids[serie['id_serie']] != 1
                    or serie.get('id_contexto') != datos['id_contexto']
                    or type(edad) not in (int, float) or not isfinite(edad) or not 0 <= edad < 600):
                continue
            filas = [f for f in serie.get('destinos', []) if (f.get('tipo'), f.get('ipv4')) == clave]
            if len(filas) != 1:
                continue
            f = filas[0]
            campos = [f.get(k) for k in ('programadas', 'realizadas', 'respuestas', 'sin_respuesta', 'errores', 'omitidas')]
            if (any(type(n) is not int or n < 0 for n in campos) or not f['programadas']
                    or f['realizadas'] + f['omitidas'] != f['programadas']
                    or f['respuestas'] + f['sin_respuesta'] + f['errores'] != f['realizadas']):
                continue
            rtt = f.get('rtt_ms', {})
            promedio = rtt.get('promedio')
            if rtt.get('muestras') != f['respuestas']:
                continue
            if f['respuestas'] and (type(promedio) not in (int, float) or not isfinite(promedio) or promedio < 0):
                continue
            grupos[0 if edad < 300 else 1].append(f)
        for nombre, grupo in zip(('reciente', 'anterior'), grupos):
            respuestas = sum(f['respuestas'] for f in grupo)
            programadas = sum(f['programadas'] for f in grupo)
            utilizables = sum(f['respuestas'] + f['sin_respuesta'] for f in grupo)
            resultado[nombre] = {
                'series': len(grupo), 'respuestas': respuestas, 'programadas': programadas,
                'sin_respuesta': sum(f['sin_respuesta'] for f in grupo),
                'cobertura_pct': round(100 * utilizables / programadas, 1) if programadas else None,
                'promedio_ms': round(sum(f['rtt_ms']['promedio'] * f['respuestas']
                                        for f in grupo if f['respuestas']) / respuestas, 3) if respuestas else None,
                'suficiente': len(grupo) >= 3 and respuestas >= 6 and utilizables * 5 >= programadas * 4}
        reciente, anterior = resultado['reciente'], resultado['anterior']
        if reciente['suficiente'] and anterior['suficiente']:
            diferencia = reciente['promedio_ms'] - anterior['promedio_ms']
            resultado.update(estado='comparable', mensaje=(
                'Las respuestas tardaron más, en promedio, que en los cinco minutos anteriores.' if diferencia > 0 else
                'Las respuestas tardaron menos, en promedio, que en los cinco minutos anteriores.' if diferencia < 0 else
                'El tiempo promedio de respuesta fue igual en ambos periodos.'),
                orientacion='Si notas pausas en una llamada o un juego, comprueba si se repiten. Esta comparación por sí sola no explica la causa ni indica cuánto puedes descargar.')
    return salida
