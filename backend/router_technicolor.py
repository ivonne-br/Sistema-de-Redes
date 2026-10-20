"""Acceso HTTPS y lectura del Technicolor CGA4233TLV2 observado.

Entradas: gateway actual, huella TLS confirmada y credenciales efímeras.
Salidas: sesión privada e inventario normalizado para MonitoreoRouter. Reproduce
el contrato de login.html/app.js; no modifica ajustes ni expulsa otras sesiones.
"""
import hashlib
import hmac
import ipaddress
import json
import re
import ssl
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
from urllib.parse import urlencode

from backend.reloj import tiempo_continuo
from backend.router_http import cabeceras_router

PERFIL = {'ModelName': 'CGA4233TLV2', 'Manufacturer': 'Technicolor',
          'HardwareVersion': '0.1.0', 'SoftwareVersion': 'CGA4233TLV2-21.3-15.0-R29-RQ'}
IDENTIDAD = '/api/v1/system/ModelName,Manufacturer,HardwareVersion,SoftwareVersion'
HOSTS = '/api/v1/host/hostTbl'
LOGIN = '/api/v1/session/login'
MENU = '/api/v1/session/menu'
# hostTbl tarda 16.9–18.2 s en el equipo observado; margen acotado de lectura.
PLAZO_LECTURA_S = 30
PLAZO_ACCESO_S = 15

RUTAS = {'/', '/views/login.html', '/js/app/app.js', IDENTIDAD, HOSTS, LOGIN, MENU}


def _error(estado):
    from backend.router import ErrorRouter
    return ErrorRouter(estado)


def _conexion(gateway):
    ip = ipaddress.IPv4Address(gateway)
    if not any(ip in ipaddress.IPv4Network(r) for r in
               ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise _error('destino_no_admitido')
    # Se verifica el certificado completo por SHA-256 antes de enviar HTTP.
    # La obtención inicial no envía credenciales y NO autoriza su uso.
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    return HTTPSConnection(str(ip), timeout=3, context=contexto)


def huella_publica(gateway):
    """Solo handshake TLS; obtiene una huella candidata, sin confiar en ella."""
    c = _conexion(gateway)
    try:
        c.connect()
        return hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest()
    finally:
        c.close()


def solicitar(gateway, ruta, acceso, campos=None, vigente=None):
    """Lista cerrada; pin TLS antes de secretos; sin redirecciones ni reintentos."""
    if ruta not in RUTAS or (campos is not None and ruta != LOGIN):
        raise _error('destino_no_admitido')
    vigente = vigente or acceso.get('vigente', lambda: True)
    huella = acceso.get('huella', '')
    if not isinstance(huella, str) or not re.fullmatch('[0-9a-f]{64}', huella):
        raise _error('certificado_router_no_confirmado')
    c = _conexion(gateway)
    inicio = tiempo_continuo()
    limite_s = PLAZO_LECTURA_S if ruta == HOSTS else PLAZO_ACCESO_S
    def restante():
        plazo = limite_s - (tiempo_continuo() - inicio)
        if plazo <= 0:
            raise TimeoutError()
        return plazo
    try:
        c.timeout = restante()
        if not vigente():
            raise _error('contexto_cambiado')
        c.connect()
        actual = hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest()
        if not hmac.compare_digest(huella, actual):
            raise _error('certificado_router_cambiado')
        cookies = acceso.setdefault('cookies', {})
        headers = {**cabeceras_router(), 'Accept': 'application/json, text/html',
                   'Referer': f'https://{gateway}/', 'X-Requested-With': 'XMLHttpRequest',
                   'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items()),
                   'X-CSRF-TOKEN': cookies.get('auth', ''), 'Cache-Control': 'no-cache'}
        cuerpo = None
        if campos is not None:
            cuerpo = urlencode(campos)
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        if not vigente():
            raise _error('contexto_cambiado')
        socket_tls = c.sock
        socket_tls.settimeout(restante())
        c.request('POST' if campos is not None else 'GET', ruta, cuerpo, headers)
        socket_tls.settimeout(restante())
        r = c.getresponse()
        # Diagnóstico acotado: solo presencia de las dos cookies del contrato.
        # Nunca conservar cuerpos, cabeceras completas, salts ni valores secretos.
        registro = {'paso': {IDENTIDAD: 'modelo', MENU: 'menu', LOGIN: 'acceso',
                            HOSTS: 'equipos'}.get(ruta, 'pagina_publica'),
                    'http': r.status, 'envia_sesion': bool(cookies.get('PHPSESSID')),
                    'envia_csrf': bool(cookies.get('auth')),
                    'recibe_sesion': False, 'recibe_csrf': False}
        for nombre, valor in r.getheaders():
            if nombre.lower() == 'set-cookie':
                nombre_cookie = valor.partition('=')[0].strip()
                registro['recibe_sesion'] |= nombre_cookie == 'PHPSESSID'
                registro['recibe_csrf'] |= nombre_cookie == 'auth'
        traza = acceso.setdefault('diagnostico', [])
        traza.append(registro)
        del traza[:-12]
        if r.status in (301, 302, 303, 307, 308, 401, 403):
            error = _error('autorizacion_rechazada')
            error.etapa = {IDENTIDAD: 'perfil_router', MENU: 'validacion_sesion',
                           LOGIN: 'envio_login', HOSTS: 'lectura_tablas'}.get(ruta, 'pagina_login')
            error.etapa += '_http_' + str(r.status)
            error.diagnostico = [dict(paso) for paso in traza]
            raise error
        if r.status != 200:
            raise _error('error_http_router')
        data = bytearray()
        while True:
            if not vigente():
                raise _error('contexto_cambiado')
            socket_tls.settimeout(restante())
            bloque = r.read1(16384)
            restante()
            data.extend(bloque)
            if len(data) > 1_000_000:
                raise _error('respuesta_no_admitida')
            if not bloque or r.isclosed() is True:
                break
        if not vigente():
            raise _error('contexto_cambiado')
        for nombre, valor in r.getheaders():
            if nombre.lower() == 'set-cookie':
                jar = SimpleCookie()
                jar.load(valor)
                for k, v in jar.items():
                    if len(v.coded_value) > 4096 or any(ord(x) < 32 or ord(x) > 126 for x in v.coded_value):
                        raise _error('respuesta_no_admitida')
                    cookies[k] = v.coded_value
                    if len(cookies) > 32 or sum(len(k) + len(v) for k, v in cookies.items()) > 8192:
                        raise _error('respuesta_no_admitida')
        registro['conserva_sesion'] = bool(cookies.get('PHPSESSID'))
        registro['conserva_csrf'] = bool(cookies.get('auth'))
        return data.decode('utf-8')
    except TimeoutError:
        error = _error('tiempo_agotado_router')
        error.diagnostico = [{'paso': {IDENTIDAD: 'modelo', MENU: 'menu', LOGIN: 'acceso',
                                      HOSTS: 'equipos'}.get(ruta, 'pagina_publica'),
                              'resultado': 'tiempo_agotado_router',
                              'limite_s': limite_s}]
        raise error from None
    except (OSError, UnicodeError):
        raise _error('conexion_fallida_router') from None
    finally:
        c.close()


def objeto(texto):
    """Rechaza JSON ambiguo y nunca incorpora el cuerpo remoto al error público."""
    def pares(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError()
            d[k] = v
        return d
    try:
        r = json.loads(texto, object_pairs_hook=pares)
        if not isinstance(r, dict):
            raise ValueError()
        return r
    except (ValueError, RecursionError):
        raise _error('respuesta_no_admitida') from None


def datos(texto):
    r = objeto(texto)
    if r.get('error') != 'ok' or not isinstance(r.get('data'), dict):
        raise _error('autorizacion_rechazada')
    return r['data']


def derivar(password, salt):
    """Equivalente a sjcl.misc.pbkdf2(texto, salt, 1000, 128), salida hexadecimal."""
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 1000, 16).hex()


def inventario(texto):
    """Mapea hostTbl observado; estado del panel no equivale a presencia probada."""
    filas = datos(texto).get('hostTbl')
    if not isinstance(filas, list) or len(filas) > 4096:
        raise ValueError('Tabla no compatible.')
    equipos, vistas = [], set()
    for f in filas:
        if not isinstance(f, dict):
            raise ValueError('Fila no compatible.')
        def campo(k):
            v = f.get(k)
            if not isinstance(v, str) or len(v) > 256:
                raise ValueError('Campo no compatible.')
            return v
        mac = campo('physaddress').lower()
        if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', mac) or mac in vistas:
            raise ValueError('Identidad no compatible.')
        vistas.add(mac)
        # El panel muestra ipv41; versiones sin ese campo conservan ipaddress.
        ip = campo('ipv41' if 'ipv41' in f else 'ipaddress')
        ip = str(ipaddress.IPv4Address(ip)) if ip else None
        estado = campo('active')
        interfaz = campo('layer1interface')
        equipos.append({'nombre': campo('hostname') or None, 'mac': mac, 'ipv4': ip,
                        'interfaz': interfaz or None, 'tipo_original': campo('addresssource') or None,
                        'codigo_estado_original': estado,
                        'estado_original': {'true': 'Activo', 'false': 'Inactivo'}.get(estado),
                        'expira_en_original': None, 'conexion_original': None,
                        'fuente': HOSTS})
    return {'estado': 'lectura_correcta', 'equipos': equipos, 'wan': [],
            'recuento_filas_interpretadas': {'total': len(equipos),
                'activo': sum(e['estado_original'] == 'Activo' for e in equipos),
                'inactivo': sum(e['estado_original'] == 'Inactivo' for e in equipos),
                'estado_desconocido': sum(e['estado_original'] is None for e in equipos)}}


class LecturaTechnicolor:
    nombre = 'Technicolor CGA4233TLV2'
    plazo_lectura_s = PLAZO_LECTURA_S + 1
    fuentes = ('technicolor-hosts',)
    fuente_inventario = 'technicolor-hosts'

    def __init__(self, transporte=solicitar):
        self.transporte = transporte

    def autenticar(self, gateway, usuario, password, vigente, *, huella):
        acceso = {'huella': huella, 'cookies': {}, 'vigente': vigente}
        def pedir(ruta, campos=None):
            return self.transporte(gateway, ruta, acceso, campos, vigente)
        # Identificación del contrato público ANTES de enviar el usuario/password.
        portada = pedir('/')
        pagina = pedir('/views/login.html')
        app = pedir('/js/app/app.js')
        if ('technicolor' not in portada.lower() or not all(x in pagina for x in
                ('seeksalthash', 'saltwebui', 'sjcl.misc.pbkdf2', '1000,128'))
                or not all(x in app for x in ('X-CSRF-TOKEN', 'api/v1/'))):
            raise _error('sesion_o_router_no_compatible')
        # app.init consulta el menú público para preparar cookies/CSRF.
        objeto(pedir(MENU))
        reto = objeto(pedir(LOGIN, {'username': usuario, 'password': 'seeksalthash', 'logout': 'false'}))
        if reto.get('message') == 'MSG_LOGIN_150':
            raise _error('router_ocupado')
        if reto.get('error') != 'ok':
            raise _error('autorizacion_rechazada')
        salt, web = reto.get('salt'), reto.get('saltwebui')
        if not isinstance(salt, str) or not 1 <= len(salt) <= 1024:
            raise _error('respuesta_no_admitida')
        if salt == 'none':
            prueba = password
        else:
            if not isinstance(web, str) or not 1 <= len(web) <= 1024:
                raise _error('respuesta_no_admitida')
            prueba = derivar(derivar(password, salt), web)
        respuesta = objeto(pedir(LOGIN, {'username': usuario, 'password': prueba}))
        if respuesta.get('error') != 'ok':
            raise _error('autorizacion_rechazada')
        # login.html recarga la portada al aceptar el acceso. Esa respuesta
        # puede establecer el token que app.js usa en X-CSRF-TOKEN.
        pedir('/')
        # Tras location.reload(), app.init vuelve a consultar el menú. El menú
        # autenticado debe estar disponible antes de pedir recursos protegidos.
        self.validar_sesion(gateway, acceso)
        return acceso

    def verificar(self, gateway, acceso):
        respuesta = objeto(self.transporte(gateway, IDENTIDAD, acceso))
        if respuesta.get('error') != 'ok' or not isinstance(respuesta.get('data'), dict):
            error = _error('respuesta_no_admitida')
            error.etapa = 'perfil_router_formato'
            raise error
        perfil = respuesta['data']
        if any(perfil.get(k) != v for k, v in PERFIL.items()):
            raise _error('sesion_o_router_no_compatible')

    def validar_sesion(self, gateway, acceso):
        respuesta = objeto(self.transporte(gateway, MENU, acceso))
        menu = respuesta.get('data')
        login = menu.get('login') if isinstance(menu, dict) else None
        identificada = (isinstance(login, dict) and isinstance(login.get('user'), str)
                        and bool(login['user']))
        traza = acceso.get('diagnostico', [])
        if traza and traza[-1]['paso'] == 'menu':
            traza[-1]['sesion_identificada'] = identificada
        if respuesta.get('error') != 'ok' or not identificada:
            error = _error('autorizacion_rechazada')
            error.etapa = 'menu_sin_sesion'
            error.diagnostico = [dict(paso) for paso in traza]
            raise error

    def leer(self, gateway, fuente, acceso):
        if fuente != self.fuente_inventario:
            raise ValueError('Fuente no compatible.')
        return inventario(self.transporte(gateway, HOSTS, acceso))
