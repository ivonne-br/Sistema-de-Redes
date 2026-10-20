"""Normaliza copias JSON DHCP/WAN del Sercomm observado para el CLI.

Entrada: una respuesta JSON y la tabla de procedencia elegida explícitamente.
Salida: campos permitidos, errores sin contenido privado y capacidades limitadas.
No obtiene sesiones, consulta la red, calcula tasas ni publica datos al invitado.
"""

from collections import Counter
import ipaddress
import json
import re

LIMITE_JSON = 1_000_000
FUENTES = {
    'dhcp-json': 'statussupportwan_lan_leases.json',
    'wan-ipv4-json': 'statussupportwan_wan_statistics.json',
    'wan-ipv6-json': 'statussupportwan_ipv6wan_statistics.json',
}
# Correspondencia observada entre JSON y etiquetas del panel FG6123BV3027.
# No representa presencia instantánea y no se extrapola a otros firmwares.
_ESTADOS = {'601045': 'Activo', '601046': 'Inactivo'}


def _objeto(pares):
    """Rechaza claves repetidas: json.loads normalmente elegiría la última."""
    resultado = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError('JSON ambiguo.')
        resultado[clave] = valor
    return resultado


def _constante_no_json(_valor):
    """Impide NaN/Infinity, extensiones que json.loads acepta por defecto."""
    raise ValueError('Constante no compatible.')


def _texto(fila, clave, *, vacio=False):
    valor = fila.get(clave)
    if not isinstance(valor, str) or len(valor) > 256 or (not vacio and not valor.strip()):
        raise ValueError('Campo no compatible.')
    return valor


def _bytes(fila, clave):
    """Convierte cadenas decimales sin pasar por float ni perder precisión."""
    valor = fila.get(clave)
    if not isinstance(valor, str) or not re.fullmatch(r'[0-9]{1,20}', valor):
        raise ValueError('Contador no compatible.')
    entero = int(valor)
    if entero > 2**64 - 1:
        raise ValueError('Contador fuera de rango.')
    return entero


def interpretar_json_router(texto, fuente):
    """Valida una tabla copiada; su importación no acredita fecha ni red actual.

    Omite filas inválidas y todas las variantes de claves duplicadas. Una lista
    vacía válida tiene cero filas; un error tiene recuentos nulos. Otros campos
    del documento no se propagan a la salida, incluidos posibles secretos.
    """
    if fuente not in FUENTES or not isinstance(texto, str) or len(texto) > LIMITE_JSON:
        raise ValueError('Fuente o tamaño no compatible.')
    try:
        filas = json.loads(texto, object_pairs_hook=_objeto,
                           parse_constant=_constante_no_json)
    except (ValueError, RecursionError):
        raise ValueError('JSON no válido o ambiguo.') from None
    if not isinstance(filas, list) or len(filas) > 4096:
        raise ValueError('Se requiere una única lista JSON de hasta 4096 filas.')
    equipos, contadores, errores = [], [], []
    candidatos = []
    for numero, fila in enumerate(filas, 1):
        try:
            if not isinstance(fila, dict):
                raise ValueError()
            interfaz = _texto(fila, 'interface')
            if fuente == 'dhcp-json':
                mac = _texto(fila, 'mac_address')
                if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac):
                    raise ValueError()
                ip = str(ipaddress.IPv4Address(_texto(fila, 'ip_address')))
                codigo = _texto(fila, 'status')
                item = {'nombre': _texto(fila, 'host_name', vacio=True) or None,
                        'ipv4': ip, 'mac': mac.lower(), 'interfaz': interfaz,
                        'tipo_original': _texto(fila, 'type'),
                        'codigo_estado_original': codigo,
                        'estado_original': _ESTADOS.get(codigo),
                        'expira_en_original': _texto(fila, 'expires_in'),
                        'conexion_original': _texto(fila, 'conn_type')}
                clave = (ip, mac.lower())
            else:
                item = {'interfaz': interfaz, 'tipo_original': _texto(fila, 'description'),
                        'familia_ip': 'IPv4' if fuente == 'wan-ipv4-json' else 'IPv6',
                        'bytes_rx': _bytes(fila, 'receivedbytes'),
                        'bytes_tx': _bytes(fila, 'transmittedbytes'),
                        'inicio_acumulacion': None}
                clave = interfaz
            item['fuente'] = FUENTES[fuente]
            candidatos.append((numero, clave, item))
        except ValueError:
            errores.append({'numero_fila': numero, 'motivo': 'Fila no compatible.'})
    repeticiones = Counter(clave for _, clave, _ in candidatos)
    for numero, clave, item in candidatos:
        if repeticiones[clave] > 1:
            errores.append({'numero_fila': numero, 'motivo': 'Clave repetida; se omiten sus variantes.'})
        elif fuente == 'dhcp-json':
            equipos.append(item)
        else:
            contadores.append(item)
    util = bool(equipos or contadores)
    recuentos = None
    if fuente == 'dhcp-json' and (util or not errores):
        recuentos = {'total': len(equipos),
                     'activo': sum(e['estado_original'] == 'Activo' for e in equipos),
                     'inactivo': sum(e['estado_original'] == 'Inactivo' for e in equipos),
                     'estado_desconocido': sum(e['estado_original'] is None for e in equipos)}
    return {'version_esquema': 1, 'fuente': FUENTES[fuente],
            'origen': 'json_panel_aportado', 'momento_captura': None, 'contexto_red': None,
            'estado': ('lectura_parcial' if util else 'sin_datos_utilizables') if errores else 'lectura_correcta',
            'equipos': equipos, 'recuento_filas_interpretadas': recuentos,
            'wan': contadores, 'errores': errores,
            'limitaciones': [
                'Copia manual sin fecha verificable ni asociación a la red actual.',
                'Estados DHCP según correspondencia observada en FG6123BV3027; no prueban presencia instantánea.',
                'Contadores WAN por interfaz y familia; no se suman IPv4 e IPv6.',
                'Alcance del tráfico e inicio de acumulación pendientes de comprobar.',
                'Sin tasas ni consumo por dispositivo.',
            ]}
