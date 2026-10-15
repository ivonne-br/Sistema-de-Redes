"""Diagnóstico interactivo de user_data.json; no guarda credenciales ni respuestas.

Ejecutar: python -B -m backend.router_diagnostico. Un login explícito y hasta
seis GET de validación sobre la misma red. Nunca modifica configuración.
"""
from getpass import getpass
from http.client import HTTPConnection, BadStatusLine
import json
import time
from urllib.parse import urlencode

from backend.contexto_red import consultar_contexto_ipv4
from backend.router import _contexto, ErrorRouter
from backend.router_http import cabeceras_router
from backend.router_login import iniciar_sesion


def variantes(cookie, csrf, gateway):
    query = urlencode({'csrf_token': csrf})
    con_fecha = urlencode({'_': int(time.time() * 1000), 'csrf_token': csrf})
    headers = {**cabeceras_router(), 'Cookie': cookie,
               'Accept': 'application/json, text/javascript, */*; q=0.01',
               'Referer': f'http://{gateway}/status-and-support.html',
               'X-Requested-With': 'XMLHttpRequest', 'Cache-Control': 'no-cache'}
    ordenada = '; '.join(sorted(cookie.split('; '), key=lambda c: not c.startswith('session_id=')))
    return [
        ('actual', query, headers),
        ('marca_de_tiempo', con_fecha, headers),
        ('cookie_sesion_primero', con_fecha, {**headers, 'Cookie': ordenada}),
        ('sin_cabecera_ajax', con_fecha, {k: v for k, v in headers.items() if k != 'X-Requested-With'}),
        ('cabeceras_del_login', con_fecha, {**cabeceras_router(), 'Cookie': cookie,
            'Accept': '*/*', 'Referer': f'http://{gateway}/login.html'}),
    ]


def consultar(gateway, query, headers):
    c = HTTPConnection(gateway, timeout=3)
    try:
        c.request('GET', '/data/user_data.json?' + query, headers=headers)
        r = c.getresponse()
        if r.status != 200:
            return f'HTTP {r.status}'
        inicio = time.monotonic()
        cuerpo = bytearray()
        while True:
            bloque = r.read1(16384)
            cuerpo.extend(bloque)
            if len(cuerpo) > 1_000_000 or time.monotonic() - inicio > 5:
                return 'respuesta fuera del límite'
            if not bloque:
                break
        try:
            datos = json.loads(cuerpo)
        except (ValueError, RecursionError):
            return 'HTTP 200; JSON no válido'
        valida = isinstance(datos, list) and any(
            isinstance(f, dict) and isinstance(f.get('username'), str) and f['username'].strip()
            for f in datos)
        return 'HTTP 200; sesión validada' if valida else 'HTTP 200; sesión no confirmada'
    except BadStatusLine as error:
        # Solo el código numérico; nunca se imprime la línea remota completa.
        partes = error.line.split()
        codigo = partes[1] if len(partes) > 1 and partes[1] in ('400', '401', '403', '500') else 'desconocido'
        return f'HTTP malformado; código {codigo}'
    except TimeoutError:
        return 'tiempo agotado'
    except Exception:
        return 'error de conexión o lectura'
    finally:
        c.close()


def main():
    red = _contexto(consultar_contexto_ipv4())
    if not red:
        print('No se encontró una puerta de enlace local compatible.')
        return
    print(f"Router de la red actual: {red['gateway']}")
    print('Un inicio de sesión y cinco consultas de lectura. No se guardan datos.')
    usuario = input('Usuario del panel (tal como aparece allí): ').strip()
    password = getpass('Contraseña del panel (no se mostrará): ')
    vigente = lambda: _contexto(consultar_contexto_ipv4()) == red
    cookie = csrf = ''
    try:
        try:
            cookie, csrf = iniciar_sesion(red['gateway'], usuario, password, vigente)
        finally:
            password = ''
        print('Login completado; comprobando la validación de sesión.')
        for nombre, query, headers in variantes(cookie, csrf, red['gateway']):
            if not vigente():
                print('Red cambiada: diagnóstico detenido.')
                return
            print(f'{nombre}: {consultar(red["gateway"], query, headers)}', flush=True)
    except ErrorRouter as error:
        print(f'Login detenido: {error}; etapa: {getattr(error, "etapa", "inicio")}. No se reintentó.')
    finally:
        cookie = csrf = password = ''


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nDiagnóstico cancelado.')
