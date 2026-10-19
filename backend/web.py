"""Comprueba resolución de nombres y HTTPS, sin ARP ni cambios en el DNS del Mac.

Entradas: configuración y contexto IPv4; salidas: últimas comprobaciones, historial y recuentos temporales para la
API. Las operaciones de red se aíslan en procesos acotados para limitar también
getaddrinfo. Este módulo sirve como trabajador con `python -m backend.web`.
"""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from http.client import HTTPSConnection, HTTPException
import json
import socket
import ssl
import subprocess
import sys
from threading import Event, Lock
from backend.reloj import tiempo_continuo
from backend.entorno_aplicacion import comando_web, raiz_recursos
from urllib.parse import urlsplit
from uuid import uuid4

from backend.configuracion import ConfiguracionBackend
from backend.contexto_red import consultar_contexto_ipv4
from backend.descubrimiento import normalizar_contexto_observacion
from backend.memoria import clave_contexto


def comprobar(tipo, destino, limite, codigo=204):
    """Trabajador: DNS usa el resolvedor del sistema; HTTPS valida TLS y no redirige.

    Solo recibe cabeceras HTTPS, no descarga el cuerpo. La duración comprende toda
    la operación, incluida su resolución; no es RTT ni latencia de un servidor DNS.
    """
    inicio = tiempo_continuo()
    resultado = {'estado': 'error_medicion', 'direcciones': [], 'codigo_http': None}
    try:
        if tipo == 'dns':
            datos = socket.getaddrinfo(destino, None, socket.AF_INET, socket.SOCK_STREAM)
            resultado['direcciones'] = sorted({fila[4][0] for fila in datos})
            resultado['estado'] = 'correcto' if resultado['direcciones'] else 'sin_direcciones'
        elif tipo == 'https':
            url = urlsplit(destino)
            conexion = HTTPSConnection(url.hostname, url.port or 443, timeout=limite,
                                       context=ssl.create_default_context())
            try:
                ruta = (url.path or '/') + (('?' + url.query) if url.query else '')
                conexion.request('GET', ruta, headers={'User-Agent': 'Sistema-de-Redes/0.1',
                                                      'Connection': 'close', 'Cache-Control': 'no-cache'})
                respuesta = conexion.getresponse()
                resultado['codigo_http'] = respuesta.status
                resultado['estado'] = 'correcto' if respuesta.status == codigo else 'http_inesperado'
                respuesta.close()
            finally:
                conexion.close()
        else:
            raise ValueError('Tipo de comprobación desconocido.')
    except socket.gaierror:
        resultado['estado'] = 'error_resolucion'
    except ssl.SSLCertVerificationError:
        resultado['estado'] = 'certificado_invalido'
    except ssl.SSLError:
        resultado['estado'] = 'error_tls'
    except (TimeoutError, socket.timeout):
        resultado['estado'] = 'tiempo_agotado'
    except (OSError, HTTPException):
        resultado['estado'] = 'error_conexion'
    resultado['duracion_ms'] = round((tiempo_continuo() - inicio) * 1000, 3)
    return resultado


def ejecutar_comprobacion(tipo, destino, limite, codigo=204):
    """Acota el trabajador completo; run mata y recoge el hijo al agotar el plazo."""
    try:
        proceso = subprocess.run(
            comando_web(tipo, destino, limite, codigo),
            cwd=raiz_recursos(), capture_output=True, text=True,
            timeout=limite, check=True)
        dato = json.loads(proceso.stdout)
        if not isinstance(dato, dict) or 'estado' not in dato or 'duracion_ms' not in dato:
            raise ValueError('Resultado del trabajador inválido.')
        return dato
    except subprocess.TimeoutExpired:
        estado = 'tiempo_agotado'
    except (OSError, subprocess.SubprocessError, ValueError):
        estado = 'error_medicion'
    return {'estado': estado, 'duracion_ms': None, 'codigo_http': None, 'direcciones': []}


def resumir_ventana(historial):
    """Cuenta cada tipo y destino de la ventana; conserva estados de fallo separados."""
    grupos = {}
    for serie in historial:
        for fila in serie['resultados']:
            clave = (fila['tipo'], fila['destino'])
            grupo = grupos.setdefault(clave, {
                'tipo': fila['tipo'], 'destino': fila['destino'], 'intentos': 0,
                'correctos': 0, 'no_correctos': 0, 'por_estado': {},
                'primer_fin': fila['fin'], 'ultimo_fin': None, 'ultimo_estado': None,
            })
            estado = fila['estado']
            grupo['intentos'] += 1
            grupo['correctos'] += int(estado == 'correcto')
            grupo['no_correctos'] += int(estado != 'correcto')
            grupo['por_estado'][estado] = grupo['por_estado'].get(estado, 0) + 1
            grupo['ultimo_fin'], grupo['ultimo_estado'] = fila['fin'], estado
    for grupo in grupos.values():
        grupo['correcto_posterior'] = grupo['ultimo_estado'] == 'correcto' and grupo['no_correctos'] > 0
    return list(grupos.values())


class MonitoreoWeb:
    """Un par DNS/HTTPS por ciclo, con historial limitado por capacidad y retención."""

    def __init__(self, configuracion=None, *, consultar_contexto=consultar_contexto_ipv4,
                 sonda=ejecutar_comprobacion, reloj=tiempo_continuo):
        self.config = configuracion or ConfiguracionBackend()
        self._contexto, self._sonda, self._reloj = consultar_contexto, sonda, reloj
        self._parada, self._lock, self._ciclo_lock = Event(), Lock(), Lock()
        self._clave = None
        self._historial = deque(maxlen=self.config.memoria.capacidad)
        self._datos = {'estado': 'esperando_contexto', 'id_contexto': None, 'contexto': None,
                       'detalle': None, 'resultados': []}

    def detener(self):
        """Interrumpe la espera; las operaciones activas terminan dentro del plazo."""
        self._parada.set()

    def _leer_contexto(self):
        try:
            dato = self._contexto(self.config.limite_contexto_s)
            if dato['estado'] == 'contexto_correcto':
                return normalizar_contexto_observacion(dato['contexto'])
        except Exception:
            pass
        return None

    def _sin_contexto(self):
        with self._lock:
            self._clave = None
            self._datos.update(estado='sin_contexto', id_contexto=None, contexto=None,
                               resultados=[], detalle='Contexto IPv4 no disponible o cambiado; resultados descartados.')

    def _medir(self, tipo, destino):
        inicio = datetime.now(timezone.utc).isoformat()
        try:
            dato = self._sonda(tipo, destino, self.config.limite_web_s, self.config.codigo_https_esperado)
        except Exception:
            dato = {'estado': 'error_medicion', 'duracion_ms': None, 'codigo_http': None, 'direcciones': []}
        return {**dato, 'tipo': tipo, 'destino': destino, 'inicio': inicio,
                'fin': datetime.now(timezone.utc).isoformat(), '_instante': self._reloj()}

    def ciclo(self):
        """Mide independientemente ambos servicios; descarta cambios de contexto."""
        if not self._ciclo_lock.acquire(blocking=False):
            raise RuntimeError('Ya hay un ciclo web activo.')
        try:
            if self._parada.is_set():
                return
            contexto = self._leer_contexto()
            if contexto is None:
                self._sin_contexto()
                return
            clave = clave_contexto(contexto)
            with self._lock:
                if clave != self._clave:
                    self._datos.update(id_contexto=str(uuid4()), resultados=[])
                    self._clave = clave
                self._datos.update(estado='midiendo', contexto=contexto, detalle=None)
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix='web') as pool:
                dns = pool.submit(self._medir, 'dns', self.config.nombre_dns)
                https = pool.submit(self._medir, 'https', self.config.url_https)
                resultados = [dns.result(), https.result()]
            if clave_contexto(self._leer_contexto()) != clave:
                self._sin_contexto()
                return
            with self._lock:
                self._historial.append({'id_serie': str(uuid4()), 'id_contexto': self._datos['id_contexto'],
                                        '_instante': self._reloj(), 'resultados': resultados})
                self._datos.update(estado='detenido' if self._parada.is_set() else 'en_espera', resultados=resultados)
        finally:
            self._ciclo_lock.release()

    def estado(self):
        """Devuelve copias del tramo actual; expira historia sin renovar fechas ni medir."""
        with self._lock:
            ahora = self._reloj()
            while self._historial and ahora - self._historial[0]['_instante'] >= self.config.memoria.retencion_s:
                self._historial.popleft()
            self._datos['resultados'] = [r for r in self._datos['resultados']
                                        if ahora - r['_instante'] < self.config.memoria.retencion_s]
            dato = deepcopy(self._datos)
            historial = deepcopy([s for s in self._historial if s['id_contexto'] == dato['id_contexto']])
        def presentar(filas):
            salida = []
            for fila in filas:
                edad = max(0, ahora - fila.pop('_instante'))
                if edad < self.config.memoria.retencion_s:
                    fila.update(antiguedad_s=edad, vigencia='vigente' if edad < 120 else 'desactualizado')
                    salida.append(fila)
            return salida
        dato['resultados'] = presentar(dato['resultados'])
        ventana = []
        for serie in historial:
            serie['antiguedad_s'] = max(0, ahora - serie.pop('_instante'))
            serie['resultados'] = presentar(serie['resultados'])
            if serie['resultados']:
                ventana.append(serie)
        return {**dato, 'historial': ventana, 'resumen_ventana': resumir_ventana(ventana),
                'series_conservadas': len(ventana),
                'capacidad_series': self.config.memoria.capacidad, 'retencion_s': self.config.memoria.retencion_s,
                'intervalo_s': self.config.intervalo_web_s, 'limite_s': self.config.limite_web_s,
                'vigencia_s': 120, 'codigo_https_esperado': self.config.codigo_https_esperado}

    def ejecutar(self):
        """Espera desde el final de cada ciclo; la API solicita la parada ordenada."""
        try:
            while not self._parada.is_set():
                self.ciclo()
                if self._parada.wait(self.config.intervalo_web_s):
                    break
        except Exception:
            with self._lock:
                self._datos.update(estado='error', detalle='El monitor DNS/HTTPS se detuvo por un error interno.')
        else:
            with self._lock:
                self._datos['estado'] = 'detenido'


if __name__ == '__main__':
    print(json.dumps(comprobar(sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4]))))
