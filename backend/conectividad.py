"""Mide series ICMP hacia gateway y IPv4 externas, sin consultar ni depender de ARP.

Entradas: configuración, contexto IPv4 y sonda inyectables. Salida: copias de la
última serie por destino, métricas y antigüedad para la API. Conserva hasta la
capacidad/retención configuradas; los tramos de red tienen UUID propios.
"""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import math
from threading import Event, Lock
from time import monotonic
from uuid import uuid4

from backend.configuracion import ConfiguracionBackend
from backend.contexto_red import consultar_contexto_ipv4
from backend.descubrimiento import normalizar_contexto_observacion
from backend.memoria import clave_contexto
from backend.sonda import ejecutar_sonda


def fecha_actual():
    """Fecha visible; los plazos y edades usan el reloj monotónico separado."""
    return datetime.now(timezone.utc).isoformat()


def resumir_serie(muestras, programadas):
    """Calcula métricas de una serie; errores/omisiones impiden afirmar pérdida."""
    respuestas = [m['rtt_ms'] for m in muestras if m['estado'] == 'respuesta_valida']
    silencios = sum(m['estado'] == 'sin_respuesta' for m in muestras)
    errores = sum(m['estado'] == 'error_recoleccion' for m in muestras)
    omitidas = programadas - len(muestras)
    completa = not errores and not omitidas and bool(muestras)
    return {
        'programadas': programadas, 'realizadas': len(muestras),
        'respuestas': len(respuestas), 'sin_respuesta': silencios,
        'errores': errores, 'omitidas': omitidas,
        'calidad': 'completa' if completa else ('parcial' if len(respuestas) + silencios else 'no_disponible'),
        'perdida_observada_pct': round(100 * silencios / len(muestras), 2) if completa else None,
        'rtt_ms': {'muestras': len(respuestas),
                   'minimo': min(respuestas) if respuestas else None,
                   'promedio': round(sum(respuestas) / len(respuestas), 3) if respuestas else None,
                   'maximo': max(respuestas) if respuestas else None},
    }


class MonitoreoConectividad:
    """Un ciclo a la vez; destinos en paralelo y una sonda por destino en cada ronda."""

    def __init__(self, configuracion=None, *, consultar_contexto=consultar_contexto_ipv4,
                 sonda=ejecutar_sonda, reloj=monotonic, esperar=None):
        self.config = configuracion if configuracion is not None else ConfiguracionBackend()
        self._contexto = consultar_contexto
        self._sonda = sonda
        self._reloj = reloj
        self._parada = Event()
        self._esperar = esperar if esperar is not None else self._parada.wait
        self._lock = Lock()
        self._ciclo_lock = Lock()
        self._historial = deque(maxlen=self.config.memoria.capacidad)
        self._clave = None
        self._meta = {'estado': 'esperando_contexto', 'id_contexto': None,
                      'contexto': None, 'detalle': None, 'rondas_completadas': 0}

    def detener(self):
        """Despierta la espera y omite las sondas que todavía no comenzaron."""
        self._parada.set()

    def _leer_contexto(self):
        """Consulta route/ifconfig con sus límites; nunca llama a sysctl ARP."""
        try:
            consulta = self._contexto(self.config.limite_contexto_s)
            if consulta['estado'] == 'contexto_correcto':
                return normalizar_contexto_observacion(consulta['contexto'])
        except Exception:
            pass
        return None

    def _sin_contexto(self, detalle):
        """Interrumpe el tramo; una recuperación con la misma IP recibirá otro UUID."""
        with self._lock:
            self._clave = None
            self._meta.update(estado='sin_contexto', id_contexto=None, contexto=None,
                              detalle=detalle, rondas_completadas=0)

    def _medir(self, ip):
        """Valida la evidencia de una sonda; una excepción no se cuenta como pérdida."""
        if self._parada.is_set():
            return None
        try:
            muestra = self._sonda(ip, self.config.sonda)
            if muestra['estado'] not in ('respuesta_valida', 'sin_respuesta', 'error_recoleccion'):
                raise ValueError('Estado no reconocido')
            rtt = muestra.get('rtt_ms') if muestra['estado'] == 'respuesta_valida' else None
            if muestra['estado'] == 'respuesta_valida' and (
                type(rtt) not in (int, float) or not math.isfinite(rtt) or rtt < 0
            ):
                raise ValueError('RTT no válido')
            return {'estado': muestra['estado'], 'rtt_ms': rtt}
        except Exception:
            return {'estado': 'error_recoleccion', 'rtt_ms': None}

    def ciclo(self):
        """Mide y publica una serie; descarta resultados si cambia el contexto leído."""
        if not self._ciclo_lock.acquire(blocking=False):
            raise RuntimeError('Ya hay un ciclo de conectividad activo.')
        try:
            self._ejecutar_ciclo()
        finally:
            self._ciclo_lock.release()

    def _ejecutar_ciclo(self):
        if self._parada.is_set():
            return
        contexto = self._leer_contexto()
        if contexto is None:
            self._sin_contexto('No se obtuvo un contexto IPv4 válido; no se enviaron sondas.')
            return
        clave = clave_contexto(contexto)
        with self._lock:
            if clave != self._clave:
                self._meta['id_contexto'] = str(uuid4())
                self._clave = clave
            identificador = self._meta['id_contexto']
            self._meta.update(estado='midiendo', contexto=contexto, detalle=None, rondas_completadas=0)
        destinos = [('router', contexto['gateway'])]
        destinos.extend(('externo', ip) for ip in self.config.destinos_externos if ip != contexto['gateway'])
        inicio = fecha_actual()
        muestras = [[] for _ in destinos]
        with ThreadPoolExecutor(max_workers=len(destinos), thread_name_prefix='icmp-conectividad') as pool:
            for ronda in range(self.config.muestras_conectividad):
                if self._parada.is_set():
                    break
                # Se comprueba entre rondas, además de al terminar; no se mezclan tramos.
                if ronda and clave_contexto(self._leer_contexto()) != clave:
                    self._sin_contexto('Cambió o se perdió el contexto durante la serie; se descartó la serie.')
                    return
                activos = [(i, ip) for i, (_, ip) in enumerate(destinos) if ip is not None]
                resultados = list(pool.map(self._medir, [ip for _, ip in activos]))
                for (i, _), resultado in zip(activos, resultados):
                    if resultado is not None:
                        muestras[i].append(resultado)
                with self._lock:
                    self._meta['rondas_completadas'] = ronda + 1
                if ronda + 1 < self.config.muestras_conectividad and self._esperar(1):
                    break
        if not self._parada.is_set() and clave_contexto(self._leer_contexto()) != clave:
            self._sin_contexto('Cambió o se perdió el contexto al terminar; se descartó la serie.')
            return
        fin, instante = fecha_actual(), self._reloj()
        filas = []
        for (tipo, ip), resultados in zip(destinos, muestras):
            filas.append({'tipo': tipo, 'ipv4': ip, 'inicio': inicio, 'fin': fin,
                          'omision': 'El contexto no informa un gateway IPv4.' if ip is None else None,
                          **resumir_serie(resultados, self.config.muestras_conectividad)})
        with self._lock:
            self._historial.append({'id_contexto': identificador, 'fin_monotonico': instante, 'destinos': filas})
            self._meta['estado'] = 'detenido' if self._parada.is_set() else 'en_espera'

    def estado(self):
        """Consulta copias sin enviar paquetes; expira memoria y conserva fechas previas."""
        with self._lock:
            ahora = self._reloj()
            while self._historial and ahora - self._historial[0]['fin_monotonico'] >= self.config.memoria.retencion_s:
                self._historial.popleft()
            meta = deepcopy(self._meta)
            historial = deepcopy([r for r in self._historial if r['id_contexto'] == meta['id_contexto']])
        filas = []
        if historial:
            ultimo = historial[-1]
            for fila in ultimo['destinos']:
                edad = max(0, ahora - ultimo['fin_monotonico'])
                fila.update(antiguedad_s=edad, vigencia='vigente' if edad < 90 else 'desactualizado', anterior_completa=None)
                if fila['calidad'] != 'completa':
                    for previo in reversed(historial[:-1]):
                        anterior = next((f for f in previo['destinos'] if f['tipo'] == fila['tipo'] and f['ipv4'] == fila['ipv4'] and f['calidad'] == 'completa'), None)
                        if anterior:
                            anterior['antiguedad_s'] = max(0, ahora - previo['fin_monotonico'])
                            fila['anterior_completa'] = anterior
                            break
                filas.append(fila)
        return {**meta, 'destinos': filas, 'series_conservadas': len(historial),
                'intervalo_s': self.config.intervalo_conectividad_s, 'muestras_por_serie': self.config.muestras_conectividad,
                'vigencia_s': 90, 'retencion_s': self.config.memoria.retencion_s,
                'metodo': 'icmp_ping_macos'}

    def ejecutar(self):
        """Programa series desde el fin de la anterior; una parada cancela las esperas."""
        try:
            while not self._parada.is_set():
                self.ciclo()
                if self._esperar(self.config.intervalo_conectividad_s):
                    break
        except Exception:
            with self._lock:
                self._meta.update(estado='error', detalle='El monitor se detuvo por un error interno.')
        else:
            with self._lock:
                self._meta['estado'] = 'detenido'
