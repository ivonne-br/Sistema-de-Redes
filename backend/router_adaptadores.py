"""Identifica paneles y traduce operaciones al contrato Sercomm observado.

Entradas: gateway del contexto, sesión efímera y campos validados. Salidas:
identidad, configuración y resultado HTTP. router/administracion_router gestionan
permisos; este módulo no ejecuta JavaScript ni sigue redirecciones.
"""
import json
import re
from http.client import HTTPConnection
from ipaddress import IPv4Address, IPv4Network
from urllib.parse import urlencode, quote

from backend.reloj import tiempo_continuo
from backend.router_http import cabeceras_router, consulta_router

REDES = tuple(IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
RUTAS = {'/', '/login.html', '/js/status-and-support_wan.js', '/data/statussupportstatus.json',
         '/data/user_data.json', '/data/wifi_general.json', '/data/wifi_mac_filter.json',
         '/data/wifi_mac_filter_list.json', '/data/reset.json', '/data/login.json'}
ESCRITURA = {'/data/wifi_general.json', '/data/wifi_mac_filter.json', '/data/reset.json', '/data/login.json'}
PERFIL = {'sys_model_name': 'FG6123BTM', 'sys_firmware_version': 'FG6123BV3027',
          'sys_hardware_version': '6123BV1'}


def solicitar(gateway, ruta, cookie='', csrf='', campos=None, vigente=lambda: True):
    """Una petición limitada; comprueba permiso justo antes del envío y al regresar."""
    if ruta not in RUTAS or (campos is not None and ruta not in ESCRITURA):
        raise ValueError('Operación no compatible.')
    ip = IPv4Address(gateway)
    if not any(ip in r for r in REDES) or not vigente():
        raise PermissionError('La red o el permiso cambiaron.')
    conexion = HTTPConnection(str(ip), timeout=3)
    try:
        headers = {**cabeceras_router(), 'Accept': '*/*', 'Cache-Control': 'no-cache',
                   'Referer': f'http://{ip}/wifi.html', 'X-Requested-With': 'XMLHttpRequest'}
        if cookie:
            headers['Cookie'] = cookie
        cuerpo = None
        if campos is not None:
            cuerpo = urlencode(campos, quote_via=quote, safe="~!*'()")
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        if not vigente():
            raise PermissionError('La red o el permiso cambiaron.')
        conexion.request('GET' if campos is None else 'POST',
                         ruta + ('?' + consulta_router(csrf) if csrf else ''), cuerpo, headers)
        respuesta = conexion.getresponse()
        if respuesta.status != 200:
            raise ValueError('El router no permitió completar la solicitud.')
        inicio = tiempo_continuo()
        data = bytearray()
        while True:
            bloque = respuesta.read1(16384)
            data.extend(bloque)
            if len(data) > 1_000_000 or tiempo_continuo() - inicio > 5:
                raise ValueError('Respuesta del router no compatible.')
            if not bloque:
                break
        if not vigente():
            raise PermissionError('La red o el permiso cambiaron.')
        return data.decode('utf-8')
    except (OSError, UnicodeError):
        raise ValueError('No se pudo completar la comunicación con el router.') from None
    finally:
        conexion.close()


def identificar(gateway):
    """Consulta pública sin credenciales; la marca no acredita un modelo concreto."""
    desconocido = {'adaptador': None, 'nombre': 'Router sin identificar',
                   'estado': 'no_reconocido',
                   'mensaje': 'El panel respondió, pero todavía no tenemos una lectura compatible. Puedes seguir comprobando tu conexión sin ingresar la contraseña del router.'}
    respondio = False
    for ruta in ('/login.html', '/'):
        try:
            pagina = solicitar(gateway, ruta)
            respondio = True
            # La etiqueta del usuario no sustituye la identificación del equipo actual.
            if ('technicolor' in pagina.lower()
                    and re.search(r'\bCGA4233TLV2\b', pagina, re.I)):
                return {**desconocido, 'nombre': 'Technicolor CGA4233TLV2',
                        'estado': 'lectura_pendiente',
                        'mensaje': 'Reconocimos el Technicolor CGA4233TLV2. Su acceso y lectura de datos todavía no están integrados; por eso los campos están desactivados. Las comprobaciones generales siguen disponibles.'}
            token = re.search(r"\bvar\s+csrf_token\s*=\s*['\"]([A-Za-z0-9_-]{1,256})['\"]", pagina)
            if 'Sercomm' not in pagina or 'js/login.js' not in pagina or not token:
                continue
            script = solicitar(gateway, '/js/status-and-support_wan.js', csrf=token[1])
            if all(s in script for s in ('$.getJSON', 'csrf_token', 'statussupportwan_wan_statistics.json',
                                        'statussupportwan_ipv6wan_statistics.json')):
                return {'adaptador': 'sercomm', 'nombre': 'Panel Sercomm reconocido',
                        'estado': 'compatible'}
        except Exception:
            continue
    if not respondio:
        return {**desconocido, 'estado': 'sin_respuesta',
                'mensaje': 'No pudimos consultar el panel de este router. Esto no significa que Internet esté caído ni que tu contraseña sea incorrecta: todavía no la hemos enviado. Comprueba si puedes abrir el panel en tu navegador.'}
    return desconocido


def objeto(texto):
    """Normaliza filas de campos sin aceptar duplicados ni respuestas HTML."""
    filas = json.loads(texto)
    if not isinstance(filas, list) or not all(isinstance(f, dict) for f in filas):
        raise ValueError('Formato del router no compatible.')
    salida = {}
    for fila in filas:
        for k, v in fila.items():
            if k in salida or not isinstance(v, str):
                raise ValueError('Formato del router no compatible.')
            salida[k] = v
    return salida


class Sercomm:
    """Contrato de Wi-Fi y filtro MAC del modelo/firmware inspeccionado."""

    def __init__(self, pedir):
        self.pedir = pedir

    def comprobar(self):
        perfil = objeto(self.pedir('/data/statussupportstatus.json'))
        if any(perfil.get(k) != v for k, v in PERFIL.items()):
            raise ValueError('Aún no hay operaciones comprobadas para este modelo y versión.')
        acceso = objeto(self.pedir('/data/user_data.json'))
        if acceso.get('usermode') != 'admin':
            raise PermissionError('La sesión del router no tiene permisos administrativos.')
        usuario = acceso.get('username')
        if not usuario:
            raise PermissionError('El router ya no reconoce la sesión.')
        texto_panel(usuario)
        self.identidad = {'modelo': perfil['sys_model_name'], 'firmware': perfil['sys_firmware_version'],
                          'hardware': perfil['sys_hardware_version']}
        return usuario

    def leer(self, tipo):
        if tipo == 'wifi':
            datos = objeto(self.pedir('/data/wifi_general.json'))
            campos = {}
            for sufijo in ('', '_5g'):
                activo = datos.get('wifi_network_onoff' + sufijo)
                if activo not in ('0', '1'):
                    raise ValueError('No se pudo comprobar el estado de ambas bandas.')
                campos['wifi_network_onoff' + sufijo] = activo
                if activo == '0':
                    continue
                # Se conserva el formulario completo; no se supone que el router admita parches.
                for nombre in ('wifi_ssid', 'wifi_channel', 'wifi_obss', 'wifi_broadcast_ssid',
                               'wifi_password', 'wifi_protection', 'encryption_technique',
                               'block_wireless_bridging', 'wireless_multicast', 'wifi_number_of_wifi_devices'):
                    clave = nombre + sufijo
                    if clave not in datos:
                        raise ValueError('Faltan ajustes para conservar la configuración Wi-Fi.')
                    texto_panel(datos[clave])
                    campos[clave] = datos[clave]
                password = datos['wifi_password' + sufijo]
                if not 8 <= len(password) <= 63 or set(password) <= {'*', '•'}:
                    raise ValueError('No se puede conservar una contraseña Wi-Fi oculta o de formato no comprobado.')
                if datos['wifi_protection' + sufijo] != 'wpa2' or datos['encryption_technique' + sufijo] != 'aes':
                    raise ValueError('La edición está comprobada para WPA2 con AES. Usa el panel para esta configuración.')
            return campos
        config = objeto(self.pedir('/data/wifi_mac_filter.json'))
        lista = json.loads(self.pedir('/data/wifi_mac_filter_list.json'))
        if (config.get('mac_filtering') not in ('0', '1') or config.get('access_listed') != '0'
                or config.get('wifi_disabled') != '0'):
            raise ValueError('Se necesita Wi-Fi disponible y modo de lista de bloqueo; no se cambiará una lista de permitidos.')
        if not isinstance(lista, list) or len(lista) > 64:
            raise ValueError('Lista de restricciones no compatible.')
        for fila in lista:
            if (not isinstance(fila, dict) or set(fila) != {'macfilter_name', 'macfilter_mac'}
                    or not isinstance(fila['macfilter_name'], str)):
                raise ValueError('Regla del router no compatible.')
            mac(fila['macfilter_mac'])
            texto_panel(fila['macfilter_name'])
        if len({mac(f['macfilter_mac']) for f in lista}) != len(lista):
            raise ValueError('Hay reglas duplicadas; revísalas en el panel.')
        return {'activo': config['mac_filtering'], 'lista': lista}

    def escribir(self, tipo, esperado, usuario):
        if self.pedir('/data/reset.json', {'chk_sys_busy': usuario}).strip() in ('1', '"1"'):
            return False
        self.pedir('/data/login.json', {'loginUserChkLoginTimeout': usuario})
        if tipo == 'wifi':
            campos = esperado
            ruta = '/data/wifi_general.json'
        else:
            campos = {'macFilterFiltering': '1', 'access_listed': '0',
                      'macFilterList': json.dumps(esperado['lista'], ensure_ascii=False, separators=(',', ':'))}
            ruta = '/data/wifi_mac_filter.json'
        return self.pedir(ruta, campos).strip() in ('1', '"1"')


def mac(valor):
    if not isinstance(valor, str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', valor):
        raise ValueError('Introduce la dirección MAC del dispositivo, con seis pares separados por dos puntos.')
    normal = valor.upper()
    if int(normal[:2], 16) & 1 or normal == '00:00:00:00:00:00':
        raise ValueError('La dirección no identifica un dispositivo individual.')
    return normal


def texto_panel(valor):
    """Rechaza caracteres que el panel elimina, en vez de cambiarlos silenciosamente."""
    if (not isinstance(valor, str) or any(c in valor for c in '<>"\\\'')
            or re.search(r'&(?:lt|gt|#)', valor, re.IGNORECASE)):
        raise ValueError('El panel no conserva comillas, barras invertidas, signos < > ni entidades HTML. Usa otros caracteres o revisa el ajuste en su panel.')
    return valor
