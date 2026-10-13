"""Recibe configuración y sirve JSON en loopback; administra ARP, búsqueda, ICMP y DNS/HTTPS independientes, sin medir al consultar."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from socketserver import TCPServer
from threading import BoundedSemaphore, Event, Lock, Thread
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from backend.configuracion import ConfiguracionBackend
from backend.coordinador import CoordinadorARP
from backend.eventos import registrar_resultado
from backend.busqueda import BusquedaLocal
from backend.conectividad import MonitoreoConectividad
from backend.web import MonitoreoWeb

_MONITOREO_PROCESO = Lock()


class _ServidorLocal(ThreadingHTTPServer):
    """Acota conexiones simultáneas y espera por cada conexión local."""

    daemon_threads = False
    block_on_close = True

    def __init__(self, direccion, aplicacion):
        self.aplicacion = aplicacion
        self._plazas = BoundedSemaphore(16)
        super().__init__(direccion, _Peticion)
        self.timeout = 0.2

    def get_request(self):
        conexion, direccion = super().get_request()
        conexion.settimeout(3)
        return conexion, direccion

    def server_bind(self):
        # HTTPServer resuelve el nombre del equipo; loopback no necesita DNS.
        TCPServer.server_bind(self)
        self.server_name = '127.0.0.1'
        self.server_port = self.server_address[1]

    def process_request(self, request, client_address):
        if not self._plazas.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._plazas.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._plazas.release()

    def handle_error(self, request, client_address):
        self.aplicacion.logger.error('Error al atender una petición HTTP local.')


class _Peticion(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):
        # No registrar rutas, parámetros ni direcciones proporcionadas por clientes.
        pass

    def _json(self, codigo, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        if codigo == 405:
            self.send_header('Allow', 'GET')
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(cuerpo)

    def send_error(self, code, message=None, explain=None):
        self._error(code, 'peticion_http_invalida', 'Petición HTTP no admitida.')

    def _error(self, codigo, nombre, detalle):
        self._json(codigo, {'version_esquema': 1, 'error': {'codigo': nombre, 'detalle': detalle}})

    def _solo_lectura(self):
        self._error(405, 'metodo_no_permitido', 'Esta API solo admite GET.')

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = _solo_lectura

    def do_GET(self):
        puerto = self.server.server_port
        hosts = {f'127.0.0.1:{puerto}', f'localhost:{puerto}'}
        origenes = {f'http://{host}' for host in hosts}
        if (len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in hosts
                or len(self.headers.get_all('Origin', [])) > 1
                or (self.headers.get('Origin') is not None and self.headers['Origin'] not in origenes)
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self._error(403, 'origen_no_permitido', 'Solo se admiten consultas locales del mismo origen.')
            return
        try:
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                raise ValueError
            parametros = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1)
            if parametros.keys() - {'id_contexto'}:
                raise ValueError
            identificador = parametros.get('id_contexto', [None])[0]
            if identificador is not None:
                identificador = str(UUID(identificador))
            if url.path in ('/api/v1/estado', '/api/v1/conectividad', '/api/v1/web') and parametros:
                raise ValueError
        except ValueError:
            self._error(400, 'parametros_invalidos', 'Solo se admite id_contexto con un UUID válido en rutas ARP.')
            return
        app = self.server.aplicacion
        if url.path == '/api/v1/estado':
            self._json(200, {'version_esquema': 1, 'monitoreo': app.estado()})
            return
        if url.path in ('/api/v1/conectividad', '/api/v1/web'):
            try:
                datos = app.estado_web() if url.path == '/api/v1/web' else app.estado_conectividad()
            except Exception:
                app.logger.error('No se pudo construir la consulta de conectividad.')
                self._error(500, 'error_consulta', 'No se pudo construir la consulta.')
                return
            self._json(200, {'version_esquema': 1, 'monitoreo': app.estado(),
                             'datos': datos})
            return
        rutas = {'/api/v1/arp/resumen': app.consulta.resumen,
                 '/api/v1/arp/calidad': app.consulta.calidad}
        if url.path not in rutas:
            self._error(404, 'ruta_no_encontrada', 'Ruta de consulta no encontrada.')
            return
        try:
            datos = rutas[url.path](id_contexto=identificador)
        except Exception:
            app.logger.error('No se pudo construir la respuesta de consulta ARP.')
            self._error(500, 'error_consulta', 'No se pudo construir la consulta.')
            return
        calidad = datos['calidad'] if 'calidad' in datos else datos
        if identificador is not None and calidad['id_ultimo_intento'] is None:
            self._error(404, 'contexto_no_disponible', 'El contexto no está conservado en esta ejecución.')
            return
        if url.path == '/api/v1/arp/resumen':
            datos['busqueda_activa'] = app.estado_busqueda(calidad['id_contexto'])
        self._json(200, {'version_esquema': 1, 'monitoreo': app.estado(), 'datos': datos})


class APILocal:
    """Posee un servidor, un coordinador y una memoria durante una ejecución.

    servir() ocupa el hilo llamante; ARP, búsqueda, ICMP y DNS/HTTPS usan hilos separados.
    detener() solicita cierre y el ciclo activo termina antes de liberar el dueño
    del monitoreo. sysctl conserva su limitación de no tener timeout duro.
    """

    def __init__(self, configuracion=None, *, crear_coordinador=CoordinadorARP,
                 crear_busqueda=BusquedaLocal, crear_conectividad=MonitoreoConectividad, crear_web=MonitoreoWeb, logger=None):
        self.configuracion = configuracion if configuracion is not None else ConfiguracionBackend()
        if not isinstance(self.configuracion, ConfiguracionBackend):
            raise TypeError('configuracion debe ser una ConfiguracionBackend.')
        self.logger = logger if logger is not None else logging.getLogger('backend.api')
        self._crear_coordinador = crear_coordinador
        self._crear_busqueda = crear_busqueda
        self._busqueda = None
        self._crear_conectividad = crear_conectividad
        self._conectividad = None
        self._crear_web = crear_web
        self._web = None
        self._parada = Event()
        self.preparada = Event()
        self._lock = Lock()
        self._usada = False
        self._estado = 'no_iniciado'
        self._error = None
        self._coordinador = None
        self.consulta = None
        self.puerto = None

    def estado(self):
        """Informa el ciclo de vida del servicio, distinto de la salud de la red."""
        with self._lock:
            return {'estado': self._estado, 'error': self._error,
                    'id_ejecucion': self._coordinador.id_ejecucion if self._coordinador else None}

    def detener(self):
        """Solicita parada sin bloquear; servir() realiza la limpieza."""
        self._parada.set()
        if self._coordinador is not None:
            self._coordinador.detener()
        if self._busqueda is not None:
            self._busqueda.detener()
        if self._conectividad is not None:
            self._conectividad.detener()
        if self._web is not None:
            self._web.detener()

    def estado_web(self):
        """Lee DNS/HTTPS sin enviar nuevas solicitudes ni depender de ARP/ICMP."""
        if self._web is None:
            return {'estado': 'desactivada', 'id_contexto': None, 'resultados': []}
        return self._web.estado()

    def estado_conectividad(self):
        """Entrega el estado independiente: un fallo ARP no impide esta consulta."""
        if self._conectividad is None:
            return {'estado': 'desactivada', 'id_contexto': None, 'contexto': None, 'destinos': []}
        return self._conectividad.estado()

    def estado_busqueda(self, id_contexto):
        """Consulta la última comprobación activa, con fechas propias y contexto explícito."""
        if self._busqueda is None:
            return {'estado': 'desactivada', 'id_contexto': id_contexto,
                    'detalle': None, 'resultados': []}
        return self._busqueda.estado(id_contexto=id_contexto)

    def _monitorear(self):
        try:
            self._coordinador.ejecutar(
                emitir=lambda o: registrar_resultado(self.logger, 'descubrir', o))
        except Exception:
            with self._lock:
                self._estado = 'error'
                self._error = 'El monitoreo se detuvo por un error interno.'
            self.logger.error('El hilo de monitoreo ARP terminó por un error interno.')
        else:
            with self._lock:
                self._estado = 'detenido'

    def servir(self, *, al_iniciar=None):
        """Reserva el puerto antes de iniciar un recolector; rechaza otra API activa."""
        if not _MONITOREO_PROCESO.acquire(blocking=False):
            raise RuntimeError('Ya existe una API con monitoreo en este proceso.')
        servidor = None
        hilo = None
        hilo_busqueda = None
        hilo_conectividad = None
        hilo_web = None
        try:
            if self._usada:
                raise RuntimeError('Esta instancia de API ya se inició.')
            self._usada = True
            servidor = _ServidorLocal(('127.0.0.1', self.configuracion.puerto_api), self)
            self.puerto = servidor.server_port
            self._coordinador = self._crear_coordinador(self.configuracion)
            self.consulta = self._coordinador.consulta
            if self._parada.is_set():
                self._coordinador.detener()
                return
            with self._lock:
                self._estado = 'activo'
            hilo = Thread(target=self._monitorear, name='monitoreo-arp')
            hilo.start()
            if self.configuracion.busqueda_activa:
                self._busqueda = self._crear_busqueda(
                    self._coordinador.memoria.ultima,
                    intervalo_s=self.configuracion.intervalo_busqueda_s)
                hilo_busqueda = Thread(target=self._busqueda.ejecutar, name='busqueda-local')
                hilo_busqueda.start()
            if self.configuracion.conectividad_activa:
                self._conectividad = self._crear_conectividad(self.configuracion)
                hilo_conectividad = Thread(target=self._conectividad.ejecutar, name='monitoreo-conectividad')
                hilo_conectividad.start()
            if self.configuracion.web_activa:
                self._web = self._crear_web(self.configuracion)
                hilo_web = Thread(target=self._web.ejecutar, name='monitoreo-web')
                hilo_web.start()
            self.preparada.set()
            if al_iniciar is not None:
                al_iniciar(self)
            while not self._parada.is_set():
                servidor.handle_request()
        finally:
            self.detener()
            if hilo is not None and hilo.ident is not None:
                hilo.join()
            if hilo_busqueda is not None and hilo_busqueda.ident is not None:
                hilo_busqueda.join()
            if hilo_conectividad is not None and hilo_conectividad.ident is not None:
                hilo_conectividad.join()
            if hilo_web is not None and hilo_web.ident is not None:
                hilo_web.join()
            if servidor is not None:
                servidor.server_close()
            with self._lock:
                if self._estado != 'error':
                    self._estado = 'detenido'
            _MONITOREO_PROCESO.release()
