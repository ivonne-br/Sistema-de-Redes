"""Convierte análisis públicos y tráfico autorizado en orientación automática.

Entradas: capturas en memoria, sin nuevas sondas. Salidas: hallazgos, comprobación
manual y límites para Vue. La relación con tráfico exige contexto compatible y
cobertura por ventana; nunca atribuye una causa ni identifica consumo individual.
"""
from collections import defaultdict
from backend.memoria import clave_contexto
from backend.analisis import analizar_observaciones, comparar_respuesta


def diagnosticar_conexion(web, conexion):
    """Añade un siguiente paso comprobable a los hechos del análisis público."""
    datos = analizar_observaciones(web, conexion)
    principal = datos['principal']
    incidencias = datos['incidencias']
    cambios = [r for r in datos['tiempos_respuesta'] if r['estado'] == 'comparable']
    hallazgos = [principal['explicacion']]
    for r in cambios:
        hallazgos.append(f"{r['nombre']}: {r['mensaje']}")
    if datos['estado'] == 'sin_datos':
        comprobar = 'Espera una nueva lectura. Cuando llegue, aquí aparecerá el resultado sin que tengas que pulsar ningún botón.'
        falta = 'Todavía no hay una comprobación reciente suficiente para orientar sobre el acceso a Internet.'
    elif principal['estado'] == 'atencion':
        comprobar = 'Después de realizar el paso sugerido, comprueba si tu aplicación funciona y si las siguientes comprobaciones dejan de mostrar problemas. Cambia una sola cosa cada vez.'
        falta = 'Para localizar mejor el problema, comprueba si también ocurre en otro equipo de la misma red. Esta aplicación observa desde esta computadora.'
    elif incidencias['fallos']:
        comprobar = 'Comprueba si las interrupciones que notas vuelven a ocurrir. El sistema seguirá observando si se repiten las pruebas con problemas.'
        falta = 'Una respuesta correcta posterior no garantiza que las interrupciones hayan terminado.'
    else:
        comprobar = 'Si notas fallos, prueba otra página y otro equipo de la misma red. Si solo falla uno, empieza por ese equipo o aplicación; si fallan varios, revisa el resultado de la conexión aquí.'
        falta = 'No se capturó un fallo de acceso en las pruebas disponibles. Un corte breve puede ocurrir entre comprobaciones o afectar solo a otro equipo o servicio.'
    datos['diagnostico'] = {'hallazgos': hallazgos, 'comprobar': comprobar, 'falta': falta}
    datos['limite'] = 'El sistema compara automáticamente las mediciones recientes para orientarte. Indica lo que observó y lo que falta comprobar antes de atribuir una causa.'
    return datos


def diagnosticar_trafico(router, conexion, web):
    """Compara ventanas de 5 min; solo devuelve contenido para lectura autorizada.

    Exige 240 segundos de intervalos de tráfico en cada ventana, lecturas recientes
    y los mismos contextos normalizados. No mezcla familias ni interfaces. El
    porcentaje de consumo individual no se calcula con contadores WAN.
    """
    if not router.get('autorizada'):
        return None
    salida = {'estado': 'insuficiente', 'comparaciones': [],
              'mensaje': 'Aún faltan mediciones compatibles para comparar el uso de Internet con la respuesta de la conexión.',
              'consumo_individual': 'No disponible: la fuente leída informa tráfico por conexión, no bytes enviados y recibidos por cada equipo.',
              'siguiente_paso': 'Espera hasta reunir dos periodos de cinco minutos. El análisis se actualiza automáticamente.'}
    try:
        contexto = clave_contexto(router.get('contexto'))
        if contexto is None or contexto != clave_contexto(conexion.get('contexto')) or contexto != clave_contexto(web.get('contexto')):
            salida['mensaje'] = 'Las lecturas no describen la misma configuración de red. Esperamos nuevas mediciones antes de relacionarlas.'
            return salida
    except (TypeError, ValueError, KeyError):
        return salida
    if router.get('estado') != 'lectura_correcta':
        salida['mensaje'] = 'La lectura del router no está completa. No usamos datos anteriores para describir una coincidencia actual.'
        return salida
    publicos = analizar_observaciones(web, conexion)
    if publicos['estado'] != 'observado':
        return salida
    tiempos = [r for r in comparar_respuesta(conexion) if r['estado'] == 'comparable']
    if not tiempos:
        return salida
    grupos = defaultdict(lambda: [[], []])
    for p in router.get('series', []):
        edad, dt = p.get('antiguedad_s'), p.get('intervalo_s')
        if (type(edad) not in (int, float) or type(dt) not in (int, float)
                or not 0 <= edad < 600 or not 0 < dt <= 20 or p.get('motivo') != 'intervalo_valido'):
            continue
        ventana = 0 if edad < 300 else 1
        if edad + dt > (300 if ventana == 0 else 600):
            continue
        try:
            rx, tx = int(p['bytes_recibidos']), int(p['bytes_enviados'])
            if rx < 0 or tx < 0:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        grupos[(p['fuente'], p['familia_ip'], p['interfaz'])][ventana].append((edad, dt, rx, tx))
    for clave, ventanas in grupos.items():
        if not ventanas[0] or min(p[0] for p in ventanas[0]) > 20:
            continue
        resumen = []
        for ventana in ventanas:
            segundos = sum(p[1] for p in ventana)
            resumen.append({'segundos': round(segundos, 3),
                            'mbps': sum(p[2] + p[3] for p in ventana) * 8 / segundos / 1e6 if segundos else None})
        if any(r['segundos'] < 240 for r in resumen):
            continue
        reciente, anterior = resumen
        aumento = reciente['mbps'] > anterior['mbps']
        respuestas_mayores = [r['nombre'] for r in tiempos if r['reciente']['promedio_ms'] > r['anterior']['promedio_ms']]
        acceso = publicos['comparacion']
        mas_fallos = bool(acceso and acceso['estado'] == 'comparable'
                         and acceso['reciente']['no_correctos'] * acceso['anterior']['intentos']
                         > acceso['anterior']['no_correctos'] * acceso['reciente']['intentos'])
        coincidencia = aumento and (bool(respuestas_mayores) or mas_fallos)
        salida['comparaciones'].append({'fuente': clave[0], 'familia_ip': clave[1], 'interfaz': clave[2],
            'reciente': reciente, 'anterior': anterior, 'respuestas': tiempos, 'acceso': acceso,
            'mensaje': ('En el periodo reciente aumentó el tráfico promedio y también los tiempos de respuesta o la frecuencia de problemas al visitar el sitio de prueba.' if coincidencia else
                        'No observamos un aumento conjunto del tráfico y los problemas evaluados de conexión en estos periodos.'),
            'orientacion': ('Si estás notando lentitud y sabes que hay una descarga o una copia en curso, puedes pausarla temporalmente y observar si mejora. No podemos identificar qué equipo genera este tráfico.' if coincidencia else
                            'Si continúas notando fallos, comprueba si afectan a otro equipo o página. Esta comparación no descarta problemas breves.'),
            'comprobar': 'Tras un cambio, espera un nuevo periodo de cinco minutos y revisa si mejoran las respuestas y la aplicación que estabas usando. Una coincidencia no confirma la causa.'})
    if salida['comparaciones']:
        salida.update(estado='comparable', mensaje='Comparamos los últimos cinco minutos con los cinco anteriores, por conexión del router.',
                      siguiente_paso='Los cambios pequeños pueden no notarse. No interpretamos estas comparaciones como saturación ni como porcentaje de capacidad usada.')
    return salida
