"""Interpreta una copia de las tablas del panel compartido, sin acceder a la red.

Entrada: texto exportado por la persona. Salida: inventario DHCP y contadores
WAN separados por familia, con errores y procedencia. El CLI consume esta
salida; no alimenta la API pública ni sustituye un adaptador autenticado.
"""

import ipaddress
import re
import unicodedata


LIMITE_TEXTO = 1_000_000
_DHCP = 'Tabla DHCP'
_WAN = {'Estadísticas IPv4 WAN': 'IPv4', 'Estadísticas de IPv6 WAN': 'IPv6'}
_LIMITES = {_DHCP, *_WAN, 'Estado LAN', 'Detalles de la conexión LAN IPv6',
            'Estadísticas LAN', 'Estadísticas WLAN', 'Enrutamiento',
            'Asignaciones de la tabla NAT', 'Información del Puente',
            'Reiniciar las estadísticas'}
_COLUMNAS_DHCP = ['HostName', 'Dirección MAC', 'Dirección IP', 'Tipo',
                  'Estado', 'Expira en', 'Tipo de Conexión']
_CABECERA_DHCP = 'HostNameDirección MACDirección IPTipoEstadoExpira enTipo de Conexión'
_CABECERA_WAN = ['Interfaz', 'Tipo', 'Bytes Rx', 'Paquetes', 'Errores',
                 'Perdidas', 'Bytes Tx', 'Paquetes', 'Errores', 'Perdidas']
_FILA_DHCP = re.compile(
    r'(?P<nombre>.*?)\s*(?P<mac>(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})\s*'
    r'(?P<ipv4>\d{1,3}(?:\.\d{1,3}){3})\s*(?P<tipo>DHCP)\s*'
    r'(?P<estado>Inactivo|Activo)\s*'
    r'(?P<expira>(?:\d+h\s*)?\d+m(?:\s*\d+s)?)\s*'
    r'(?P<conexion>WiFi 2\.4G|WiFi 5G|Ethernet)'
)


def _seccion(lineas, titulo):
    """Extrae solo una sección inequívoca; ausencia y duplicación son errores."""
    posiciones = [i for i, (_, texto) in enumerate(lineas) if texto == titulo]
    if len(posiciones) != 1:
        return None
    inicio = posiciones[0] + 1
    fin = next((i for i in range(inicio, len(lineas))
                if lineas[i][1] in _LIMITES), len(lineas))
    return lineas[inicio:fin]


def interpretar_texto_router(texto):
    """Normaliza el formato observado; no certifica captura, modelo ni vigencia.

    Una tabla ausente o ilegible conserva cantidades nulas. Una tabla parcial
    cuenta únicamente sus filas interpretadas, sin confirmar ausencias. No se
    recuperan columnas numéricas concatenadas de LAN/WLAN ni se usa NAT como
    presencia. Los contadores grandes se conservan como enteros exactos.
    """
    if not isinstance(texto, str):
        raise TypeError('Se requiere texto del panel.')
    if len(texto) > LIMITE_TEXTO:
        raise ValueError('El texto del panel supera el límite de 1000000 caracteres.')
    lineas = [(n, ' '.join(unicodedata.normalize('NFC', linea).split()))
              for n, linea in enumerate(texto.splitlines(), 1) if linea.strip()]
    errores = []

    def error(seccion, motivo, linea=None):
        # No copiar líneas privadas ni posibles secretos a los diagnósticos.
        errores.append({'seccion': seccion, 'numero_linea': linea, 'motivo': motivo})

    equipos = []
    filas = _seccion(lineas, _DHCP)
    # El panel también entrega una celda por línea. Solo reconstruir bloques
    # completos con sus siete columnas: no buscar MAC para adivinar alineación.
    if filas and [valor for _, valor in filas[:7]] == _COLUMNAS_DHCP:
        celdas = filas[7:]
        if len(celdas) % 7:
            error(_DHCP, 'Tabla DHCP por celdas incompleta; no se adivinan columnas.')
            filas = None
        else:
            reconstruidas = [(filas[0][0], _CABECERA_DHCP)]
            for inicio in range(0, len(celdas), 7):
                bloque = celdas[inicio:inicio + 7]
                valores = [valor for _, valor in bloque]
                if (not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', valores[1])
                        or not re.fullmatch(r'\d{1,3}(?:\.\d{1,3}){3}', valores[2])
                        or valores[3] != 'DHCP'
                        or valores[4] not in ('Activo', 'Inactivo')
                        or not re.fullmatch(r'(?:\d+h\s*)?\d+m(?:\s*\d+s)?', valores[5])
                        or valores[6] not in ('WiFi 2.4G', 'WiFi 5G', 'Ethernet')):
                    error(_DHCP, 'Fila DHCP por celdas no compatible.', bloque[0][0])
                    continue
                reconstruidas.append((bloque[0][0], ' '.join(valores)))
            filas = reconstruidas
    if not filas or filas[0][1] != _CABECERA_DHCP:
        error(_DHCP, 'Sección ausente, repetida o cabecera no compatible.')
    else:
        vistos = set()
        for numero, fila in filas[1:]:
            coincidencia = _FILA_DHCP.fullmatch(fila)
            if coincidencia is None:
                error(_DHCP, 'Fila DHCP no compatible.', numero)
                continue
            campos = coincidencia.groupdict()
            try:
                ipv4 = str(ipaddress.IPv4Address(campos['ipv4']))
            except ipaddress.AddressValueError:
                error(_DHCP, 'Dirección IPv4 no válida.', numero)
                continue
            mac = campos['mac'].lower()
            clave = (ipv4, mac)
            if clave in vistos:
                error(_DHCP, 'Asociación IPv4–MAC repetida; no se cuenta de nuevo.', numero)
                continue
            vistos.add(clave)
            equipos.append({'nombre': campos['nombre'].strip() or None,
                            'ipv4': ipv4, 'mac': mac, 'tipo_original': campos['tipo'],
                            'estado_original': campos['estado'],
                            'expira_en_original': campos['expira'],
                            'conexion_original': campos['conexion'], 'fuente': 'tabla_dhcp'})
        if len(filas) == 1:
            error(_DHCP, 'No hay filas: esta copia no confirma un inventario vacío.')

    contadores = []
    for titulo, familia in _WAN.items():
        filas = _seccion(lineas, titulo)
        if not filas or [valor for _, valor in filas[:10]] != _CABECERA_WAN:
            error(titulo, 'Sección ausente, repetida o cabecera no compatible.')
            continue
        datos = filas[10:]
        if not datos or len(datos) % 10:
            error(titulo, 'Tabla WAN vacía o incompleta; no se adivinan columnas.')
            continue
        vistos = set()
        for inicio in range(0, len(datos), 10):
            fila = [valor for _, valor in datos[inicio:inicio + 10]]
            if (not all(re.fullmatch(r'[0-9]{1,20}', valor) for valor in fila[2:])
                    or any(int(valor) > 2**64 - 1 for valor in fila[2:])):
                error(titulo, 'Contadores no válidos; se esperan enteros sin signo de hasta 64 bits.',
                      datos[inicio][0])
                continue
            if fila[0] in vistos:
                error(titulo, 'Interfaz repetida; tabla WAN ambigua.', datos[inicio][0])
                # Ninguna de las dos versiones se considera una muestra válida.
                contadores = [c for c in contadores
                              if (c['familia_ip'], c['interfaz']) != (familia, fila[0])]
                continue
            vistos.add(fila[0])
            contadores.append({'interfaz': fila[0], 'tipo_original': fila[1],
                               'familia_ip': familia, 'bytes_rx': int(fila[2]),
                               'bytes_tx': int(fila[6]), 'fuente': titulo,
                               'inicio_acumulacion': None})

    errores_dhcp = any(e['seccion'] == _DHCP for e in errores)
    return {
        'version_esquema': 1, 'fuente': 'texto_panel_aportado',
        'momento_captura': None, 'contexto_red': None,
        'estado': ('lectura_parcial' if equipos or contadores else 'sin_datos_utilizables')
                  if errores else 'lectura_correcta',
        'inventario': {
            'estado': ('parcial' if equipos else 'no_disponible') if errores_dhcp else 'interpretado',
            'equipos': equipos,
            'recuento_filas_interpretadas': {
                'total': len(equipos) if equipos else None,
                'activo': sum(e['estado_original'] == 'Activo' for e in equipos) if equipos else None,
                'inactivo': sum(e['estado_original'] == 'Inactivo' for e in equipos) if equipos else None,
            },
        },
        'wan': contadores, 'errores': errores,
        'limitaciones': [
            'Copia manual sin fecha de captura ni asociación a la red actual.',
            'Activo e Inactivo son estados DHCP informados, no presencia instantánea.',
            'Bytes WAN acumulados: alcance e inicio de acumulación por comprobar.',
            'IPv4 e IPv6 se conservan separados; no se suman.',
            'Sin tasas: una copia no proporciona un intervalo de medición verificable.',
            'Sin consumo por dispositivo; NAT y BW no lo proporcionan.',
            'LAN y WLAN no se interpretan: las columnas copiadas están concatenadas.',
        ],
    }
