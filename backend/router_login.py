"""Inicio de sesión Sercomm observado en login.js y pageLoadFunctions.js.

Un intento explícito, sin redirecciones ni ejecución del JavaScript remoto.
La contraseña nunca sale de Python: se envía el doble HMAC del panel.
"""
import hashlib
import hmac
import json
import re
import secrets
from http.client import HTTPConnection, BadStatusLine
from http.cookies import SimpleCookie
from urllib.parse import quote, urlencode
from backend.router_http import cabeceras_router, consulta_router


def iniciar_sesion(gateway, usuario, password, vigente):
    from backend.router import ErrorRouter, _SCRIPT, _REDES
    from ipaddress import IPv4Address
    if not any(IPv4Address(gateway) in red for red in _REDES):
        raise ErrorRouter('destino_no_admitido')
    cookies = {}
    etapa = 'inicio'

    def solicitar(ruta, campos=None, csrf=None):
        nonlocal etapa
        etapa = {'/login.html': 'pagina_login', _SCRIPT: 'compatibilidad',
                 '/data/user_lang.json': 'preparacion_login', '/data/reset.json': 'ocupacion',
                 '/data/login.json': 'envio_login', '/status-and-support.html': 'apertura_sesion'}[ruta]
        if not vigente():
            raise ErrorRouter('contexto_cambiado')
        conexion = HTTPConnection(gateway, timeout=3)
        try:
            headers = {**cabeceras_router(), 'Accept': '*/*',
                       'Referer': f'http://{gateway}/login.html',
                       'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items())}
            cuerpo = None
            if campos is not None:
                cuerpo = urlencode(campos, quote_via=quote, safe="~!*'()")
                headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
                headers['X-Requested-With'] = 'XMLHttpRequest'
            if csrf:
                ruta += '?' + consulta_router(csrf)
            conexion.request('POST' if campos is not None else 'GET', ruta, cuerpo, headers)
            r = conexion.getresponse()
            if r.status != 200:
                raise ErrorRouter('error_http_router')
            from backend.reloj import tiempo_continuo
            inicio = tiempo_continuo()
            data = bytearray()
            while True:
                bloque = r.read1(16384)
                data.extend(bloque)
                if len(data) > 1_000_000 or tiempo_continuo() - inicio > 5:
                    raise ErrorRouter('respuesta_no_admitida')
                if not bloque:
                    break
            for nombre, valor in r.getheaders():
                if nombre.lower() == 'set-cookie':
                    jar = SimpleCookie(); jar.load(valor)
                    for k, v in jar.items():
                        cookies[k] = v.coded_value
            if not vigente():
                raise ErrorRouter('contexto_cambiado')
            return data.decode('utf-8')
        finally:
            conexion.close()

    def token(html):
        encontrado = re.search(r"\bvar\s+csrf_token\s*=\s*['\"]([A-Za-z0-9_-]{1,256})['\"]", html)
        if not encontrado:
            raise ErrorRouter('sesion_o_router_no_compatible')
        return encontrado[1]

    try:
        pagina = solicitar('/login.html')
        if 'Sercomm' not in pagina or 'js/login.js' not in pagina:
            raise ErrorRouter('sesion_o_router_no_compatible')
        csrf = token(pagina)
        script = solicitar(_SCRIPT, csrf=csrf)
        if not all(s in script for s in ('statussupportwan_wan_statistics.json', '$.getJSON', 'csrf_token')):
            raise ErrorRouter('sesion_o_router_no_compatible')
        filas = json.loads(solicitar('/data/user_lang.json', csrf=csrf))
        if not isinstance(filas, list) or not all(isinstance(f, dict) for f in filas):
            raise ErrorRouter('sesion_o_router_no_compatible')
        datos = {k: v for fila in filas for k, v in fila.items()}
        if float(datos.get('delay_time', 0) or 0) > 0:
            raise ErrorRouter('login_en_espera')
        llave = datos.get('encryption_key')
        if not isinstance(llave, str) or not llave or len(llave) > 4096:
            raise ErrorRouter('sesion_o_router_no_compatible')
        cookies['login_uid'] = '0.' + str(secrets.randbelow(10**16)).zfill(16)
        if solicitar('/data/reset.json', {'chk_sys_busy': ''}, csrf).strip() == '1':
            raise ErrorRouter('router_ocupado')
        primero = hmac.new(b'$1$SERCOMM$', password.encode('utf-8'), hashlib.sha256).hexdigest()
        segundo = hmac.new(llave.encode('utf-8'), primero.encode('ascii'), hashlib.sha256).hexdigest()
        respuesta = solicitar('/data/login.json', {
            'LoginName': quote(usuario, safe="~!*'()"), 'LoginPWD': segundo}, csrf)
        try:
            resultado = json.loads(respuesta)
        except ValueError:
            raise ErrorRouter('autorizacion_rechazada') from None
        if resultado not in ('1', []):
            estado = {'2': 'router_ocupado', '3': 'password_rechazada', '4': 'usuario_rechazado', '5': 'password_rechazada'}.get(resultado) if isinstance(resultado, str) else None
            raise ErrorRouter(estado or 'autorizacion_rechazada')
        csrf = token(solicitar('/status-and-support.html'))
        if not cookies.get('session_id'):
            raise ErrorRouter('autorizacion_rechazada')
        return '; '.join(f'{k}={v}' for k, v in cookies.items()), csrf
    except ErrorRouter as error:
        error.etapa = etapa
        raise
    except BadStatusLine:
        error = ErrorRouter('http_invalido_router')
        error.etapa = etapa
        raise error from None
    except TimeoutError:
        error = ErrorRouter('tiempo_agotado_router')
        error.etapa = etapa
        raise error from None
    except OSError:
        error = ErrorRouter('conexion_fallida_router')
        error.etapa = etapa
        raise error from None
    except Exception:
        error = ErrorRouter('error_lectura_router')
        error.etapa = etapa
        raise error from None
    finally:
        password = ''
        cookies.clear()
