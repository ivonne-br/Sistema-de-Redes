"""Consulta GET del Sercomm, sesión temporal y memoria de telemetría para API.

Entradas: contexto local, sesión del panel autorizada y reloj continuo. Salidas:
inventario y series WAN normalizados. Nunca escribe configuración del router;
los secretos viven en memoria y la API exige una clave distinta para consultar.
"""

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from http.client import HTTPConnection, BadStatusLine
from ipaddress import IPv4Address, IPv4Network
import re
import json
import secrets
from threading import Event, RLock
from uuid import uuid4

from backend.contexto_red import consultar_contexto_ipv4
from backend.reloj import tiempo_continuo
from backend.router_login import iniciar_sesion
from backend.router_http import cabeceras_router, consulta_router
from backend.router_json import interpretar_json_router, FUENTES

_REDES = tuple(IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
_SCRIPT = '/js/status-and-support_wan.js'
_RUTAS = {_SCRIPT, '/data/user_data.json', *('/data/' + nombre for nombre in FUENTES.values())}


class ErrorRouter(Exception):
    """Estado público sin URL, cookie, token ni cuerpo remoto."""


def leer_router(gateway, ruta, cookie, csrf):
    """GET acotado al gateway literal: sin proxy, redirecciones ni reintentos."""
    ip = IPv4Address(gateway)
    if not any(ip in red for red in _REDES) or ruta not in _RUTAS:
        raise ErrorRouter('destino_no_admitido')
    conexion = HTTPConnection(str(ip), timeout=3)
    try:
        conexion.request('GET', ruta + '?' + consulta_router(csrf), headers={
            **cabeceras_router(),
            'Cookie': cookie, 'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Referer': f'http://{ip}/status-and-support.html',
            'X-Requested-With': 'XMLHttpRequest', 'Cache-Control': 'no-cache',
        })
        respuesta = conexion.getresponse()
        if respuesta.status in (301, 302, 303, 307, 308, 401, 403):
            raise ErrorRouter('autorizacion_rechazada')
        if respuesta.status != 200:
            raise ErrorRouter('error_http_router')
        inicio = tiempo_continuo()
        cuerpo = bytearray()
        while True:
            bloque = respuesta.read1(16384)
            cuerpo.extend(bloque)
            if len(cuerpo) > 1_000_000 or tiempo_continuo() - inicio > 5:
                raise ErrorRouter('respuesta_no_admitida')
            if not bloque:
                break
        return cuerpo.decode('utf-8')
    except ErrorRouter:
        raise
    except BadStatusLine:
        raise ErrorRouter('http_invalido_router') from None
    except TimeoutError:
        raise ErrorRouter('tiempo_agotado_router') from None
    except OSError:
        raise ErrorRouter('conexion_fallida_router') from None
    except Exception:
        raise ErrorRouter('error_lectura_router') from None
    finally:
        conexion.close()


def _contexto(lectura):
    if lectura.get('estado') != 'contexto_correcto':
        return None
    c = lectura.get('contexto') or {}
    try:
        ip = IPv4Address(c['gateway'])
        if not any(ip in red for red in _REDES) or ip not in IPv4Network(c['subred']):
            return None
        return {k: c[k] for k in ('interfaz', 'ipv4_local', 'subred', 'gateway')}
    except (ValueError, KeyError, TypeError):
        return None


def resumir_trafico(series, ahora, ventana_s=600):
    """Suma bytes de intervalos completos en la ventana, separados por fuente.

    Entrada: puntos privados con edad continua y diferencias enteras. Salida:
    cantidades exactas como texto y duración medida para API/Vue. No extrapola
    huecos ni reparte un intervalo que cruce el inicio de la ventana.
    """
    grupos = {}
    for p in series:
        edad = ahora - p['_t']
        if not 0 <= edad < ventana_s:
            continue
        clave = (p['fuente'], p['familia_ip'], p['interfaz'])
        g = grupos.setdefault(clave, {'fuente': clave[0], 'familia_ip': clave[1], 'interfaz': clave[2],
            'ventana_s': ventana_s, 'intervalos_validos': 0, 'segundos_medidos': 0,
            'intervalos_excluidos': 0, 'bytes_recibidos': None, 'bytes_enviados': None,
            'recibidos_mb': None, 'enviados_mb': None, 'total_mb': None,
            'ultima_fecha': p['fecha'], 'antiguedad_s': edad})
        g.update(ultima_fecha=p['fecha'], antiguedad_s=edad)
        dt = p.get('intervalo_s')
        rx, tx = p.get('bytes_recibidos'), p.get('bytes_enviados')
        if (p.get('motivo') != 'intervalo_valido' or dt is None or not 0 < dt <= 20
                or edad + dt > ventana_s or type(rx) is not int or type(tx) is not int or rx < 0 or tx < 0):
            g['intervalos_excluidos'] += 1
            continue
        g['intervalos_validos'] += 1
        g['segundos_medidos'] += dt
        g['bytes_recibidos'] = (g['bytes_recibidos'] or 0) + rx
        g['bytes_enviados'] = (g['bytes_enviados'] or 0) + tx
    for g in grupos.values():
        if g['intervalos_validos']:
            g.update(recibidos_mb=g['bytes_recibidos'] / 1e6, enviados_mb=g['bytes_enviados'] / 1e6,
                     total_mb=(g['bytes_recibidos'] + g['bytes_enviados']) / 1e6)
            g['bytes_recibidos'], g['bytes_enviados'] = str(g['bytes_recibidos']), str(g['bytes_enviados'])
        g['segundos_medidos'] = round(g['segundos_medidos'], 3)
        g['segundos_sin_medicion'] = round(max(0, ventana_s - g['segundos_medidos']), 3)
    return list(grupos.values())


class MonitoreoRouter:
    """Un recolector independiente, una autorización y hasta diez minutos en RAM.

    La sesión se liga al contexto completo y caduca a los treinta minutos.
    Consultar estado no inicia lecturas. Cambio/pérdida de red retira secretos
    y datos; un fallo ordinario conserva la fecha de la última muestra útil.
    """

    def __init__(self, *, consultar_contexto=consultar_contexto_ipv4,
                 leer=leer_router, reloj=tiempo_continuo, login=iniciar_sesion):
        self._contexto = consultar_contexto
        self._leer = leer
        self._login = login
        self._reloj = reloj
        self._lock = RLock()
        self._parada = Event()
        self._despertar = Event()
        self._red = None
        self._id = None
        self._sesion = None
        self._estado = 'buscando_gateway'
        self._etapa_error = None
        self._tablas = {}
        self._series = deque(maxlen=360)
        self._bases = {}
        self._fallos = set()

    def _limpiar(self, estado):
        self._etapa_error = None
        if self._sesion:
            self._sesion.pop('password', None)
        self._sesion = None
        self._tablas.clear()
        self._series.clear()
        self._bases.clear()
        self._fallos.clear()
        self._estado = estado

    def _sincronizar(self):
        try:
            red = _contexto(self._contexto())
        except Exception:
            red = None
        with self._lock:
            if red != self._red:
                self._limpiar('requiere_autorizacion' if red else 'sin_contexto')
                self._red = red
                self._id = str(uuid4()) if red else None
            if red is None:
                self._estado = 'sin_contexto'
            return deepcopy(red)

    def autorizar(self, datos):
        """Recibe secretos del formulario local; devuelve solo una clave local nueva."""
        red = self._sincronizar()
        with self._lock:
            self._expirar()
            if self._sesion:
                raise ValueError('Ya existe una sesión; ciérrala o espera su caducidad.')
            if not red or datos.get('id_contexto') != self._id or datos.get('confirmado') is not True:
                raise ValueError('La red cambió o falta confirmar el destino.')
            clave = secrets.token_urlsafe(32)
            sesion = {'clave': clave, 'vence': self._reloj() + 1800, 'verificada': False}
            if 'usuario' in datos:
                usuario, password = datos.get('usuario'), datos.get('password')
                if (not isinstance(usuario, str) or not 1 <= len(usuario) <= 128
                        or not isinstance(password, str) or not 1 <= len(password) <= 1024):
                    raise ValueError('Credenciales no compatibles.')
                sesion.update(usuario=usuario, password=password)
            else:
                cookie, csrf = datos.get('cookie'), datos.get('csrf')
                if (not isinstance(cookie, str) or not 1 <= len(cookie) <= 4096
                        or any(ord(c) < 32 or ord(c) > 126 for c in cookie)
                        or not re.search(r'(?:^|;\s*)session_id=[^;\s]+', cookie)
                        or not isinstance(csrf, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', csrf)):
                    raise ValueError('La sesión del panel tiene un formato no compatible.')
                sesion.update(cookie=cookie, csrf=csrf)
            self._sesion = sesion
            self._estado = 'verificando_compatibilidad'
            self._despertar.set()
            return clave

    def _expirar(self):
        ahora = self._reloj()
        if self._sesion and ahora >= self._sesion['vence']:
            self._limpiar('autorizacion_expirada')
        while self._series and ahora - self._series[0]['_t'] > 600:
            self._series.popleft()
        self._tablas = {k: v for k, v in self._tablas.items() if ahora - v['_t'] <= 600}

    def revocar(self, clave):
        with self._lock:
            self._expirar()
            if not self._permitido(clave):
                raise PermissionError()
            self._limpiar('requiere_autorizacion')

    def _permitido(self, clave):
        return bool(self._sesion and isinstance(clave, str) and clave.isascii()
                    and secrets.compare_digest(self._sesion['clave'], clave))

    def estado(self, clave=None):
        with self._lock:
            self._expirar()
            permitido = self._permitido(clave)
            salida = {'estado': self._estado, 'etapa_error': self._etapa_error, 'id_contexto': self._id,
                      'gateway_candidato': self._red['gateway'] if self._red else None,
                      'autorizada': permitido, 'tablas': {}, 'series': [], 'resumen_trafico': [], 'trafico_por_periodo': {},
                      'intervalo_s': 5, 'retencion_s': 600}
            if permitido:
                salida['contexto'] = deepcopy(self._red)
                salida['restante_s'] = max(0, self._sesion['vence'] - self._reloj())
                for fuente, tabla in self._tablas.items():
                    copia = deepcopy(tabla)
                    copia['antiguedad_s'] = max(0, self._reloj() - copia.pop('_t'))
                    copia['vigencia'] = 'vigente' if copia['antiguedad_s'] <= 20 else 'desactualizado'
                    copia['ultimo_intento'] = 'error' if fuente in self._fallos else 'correcto'
                    salida['tablas'][fuente] = copia
                # Edad continua para representar huecos sin depender del reloj civil del navegador.
                instante = self._reloj()
                salida['series'] = [{**{k: v for k, v in p.items() if k != '_t'},
                                     'antiguedad_s': max(0, instante - p['_t']),
                                     'bytes_recibidos': str(p['bytes_recibidos']) if p.get('bytes_recibidos') is not None else None,
                                     'bytes_enviados': str(p['bytes_enviados']) if p.get('bytes_enviados') is not None else None} for p in self._series]
                salida['trafico_por_periodo'] = {str(periodo): resumir_trafico(self._series, instante, periodo)
                                               for periodo in (60, 300, 600)}
                salida['resumen_trafico'] = salida['trafico_por_periodo']['600']
            return salida

    def _vigente(self, sesion, red):
        # Se consulta de nuevo antes de cada petición para no reutilizar la sesión
        # en otra vivienda, incluso si el cambio ocurre durante el ciclo.
        actual = self._sincronizar()
        with self._lock:
            self._expirar()
            return not self._parada.is_set() and self._sesion is sesion and actual == red

    def ciclo(self):
        red = self._sincronizar()
        with self._lock:
            self._expirar()
            sesion = self._sesion
        if not red or not sesion:
            return
        etapa = 'inicio'
        try:
            if 'password' in sesion:
                with self._lock:
                    if self._sesion is not sesion or 'password' not in sesion:
                        return
                    password = sesion.pop('password')
                    usuario = sesion.pop('usuario')
                try:
                    cookie, csrf = self._login(red['gateway'], usuario, password,
                                              lambda: self._vigente(sesion, red))
                finally:
                    password = ''
                if not self._vigente(sesion, red):
                    return
                with self._lock:
                    sesion.update(cookie=cookie, csrf=csrf)
            if not sesion['verificada']:
                if not self._vigente(sesion, red):
                    return
                etapa = 'script_lectura'
                script = self._leer(red['gateway'], _SCRIPT, sesion['cookie'], sesion['csrf'])
                if not all(n in script for n in (FUENTES['wan-ipv4-json'],
                                                FUENTES['wan-ipv6-json'], '$.getJSON', 'csrf_token')):
                    raise ErrorRouter('sesion_o_router_no_compatible')
                sesion['verificada'] = True
            if not self._vigente(sesion, red):
                return
            etapa = 'validacion_sesion'
            try:
                usuario = json.loads(self._leer(red['gateway'], '/data/user_data.json', sesion['cookie'], sesion['csrf']))
                if (not isinstance(usuario, list) or not any(
                        isinstance(f, dict) and isinstance(f.get('username'), str) and f['username'].strip()
                        for f in usuario)):
                    raise ValueError()
            except (ValueError, RecursionError):
                raise ErrorRouter('autorizacion_rechazada') from None
            fallos = False
            for fuente, nombre in FUENTES.items():
                if not self._vigente(sesion, red):
                    return
                try:
                    inicio = self._reloj()
                    texto = self._leer(red['gateway'], '/data/' + nombre, sesion['cookie'], sesion['csrf'])
                    normal = interpretar_json_router(texto, fuente)
                    if normal['estado'] != 'lectura_correcta':
                        raise ValueError()
                    t = self._reloj()
                    if t - inicio > 8:
                        raise ValueError()
                except ErrorRouter as error:
                    if str(error) == 'autorizacion_rechazada':
                        raise
                    fallos = True
                    with self._lock:
                        self._fallos.add(fuente)
                        self._bases = {k: v for k, v in self._bases.items() if k[0] != fuente}
                    continue
                except ValueError:
                    fallos = True
                    with self._lock:
                        self._fallos.add(fuente)
                        self._bases = {k: v for k, v in self._bases.items() if k[0] != fuente}
                    continue
                if not self._vigente(sesion, red):
                    return
                with self._lock:
                    if self._sesion is not sesion:
                        return
                    self._fallos.discard(fuente)
                    fecha = datetime.now(timezone.utc).isoformat()
                    # Contadores como cadenas en HTTP: JavaScript no representa
                    # exactamente todos los enteros de 64 bits. Cálculo en Python.
                    muestra = {'_t': t, 'fecha': fecha, 'equipos': normal['equipos'],
                               'recuento': normal['recuento_filas_interpretadas'], 'wan': []}
                    presentes = set()
                    for contador in normal['wan']:
                        clave = (fuente, contador['interfaz'])
                        presentes.add(clave)
                        previa = self._bases.get(clave)
                        rx, tx = contador['bytes_rx'], contador['bytes_tx']
                        punto = {'_t': t, 'fecha': fecha, 'fuente': fuente,
                                 'interfaz': contador['interfaz'], 'familia_ip': contador['familia_ip'],
                                 'bajada_mbps': None, 'subida_mbps': None, 'intervalo_s': None,
                                 'bytes_recibidos': None, 'bytes_enviados': None,
                                 'motivo': 'referencia_inicial'}
                        if previa:
                            dt = t - previa[0]
                            punto['motivo'] = 'intervalo_no_comparable'
                            if 0 < dt <= 20 and rx >= previa[1] and tx >= previa[2]:
                                punto.update(bajada_mbps=(rx - previa[1]) * 8 / dt / 1e6,
                                             subida_mbps=(tx - previa[2]) * 8 / dt / 1e6,
                                             intervalo_s=dt, motivo='intervalo_valido',
                                             bytes_recibidos=rx - previa[1], bytes_enviados=tx - previa[2])
                        self._series.append(punto)
                        self._bases[clave] = (t, rx, tx)
                        muestra['wan'].append({**contador, 'bytes_rx': str(rx), 'bytes_tx': str(tx)})
                    self._bases = {k: v for k, v in self._bases.items() if k[0] != fuente or k in presentes}
                    self._tablas[fuente] = muestra
            with self._lock:
                if self._sesion is sesion:
                    self._estado = 'error_fuente' if fallos else 'lectura_correcta'
                    self._etapa_error = None
        except ErrorRouter as error:
            with self._lock:
                if self._sesion is sesion:
                    transitorio = str(error) in {
                        'http_invalido_router', 'error_http_router', 'tiempo_agotado_router',
                        'conexion_fallida_router', 'error_lectura_router'}
                    if transitorio and 'cookie' in sesion and not hasattr(error, 'etapa'):
                        # Solo se reintentan GET con la sesión ya obtenida. Nunca login.
                        self._estado = str(error)
                        self._bases.clear()
                        self._fallos.update(self._tablas)
                    else:
                        self._limpiar(str(error))
                    self._etapa_error = getattr(error, 'etapa', etapa)

    def ejecutar(self):
        while not self._parada.is_set():
            self._despertar.clear()
            try:
                self.ciclo()
            except Exception:
                with self._lock:
                    self._limpiar('error_recoleccion')
            self._despertar.wait(5)

    def detener(self):
        self._parada.set()
        self._despertar.set()
        with self._lock:
            self._limpiar('detenido')
