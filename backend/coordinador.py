"""Ciclo de vida de ARP local y consulta de resultados derivados de su memoria."""

from threading import Event, Lock
from time import monotonic
from uuid import uuid4

from backend.arp_macos import consultar_arp_sistema
from backend.configuracion import ConfiguracionBackend
from backend.consulta import ConsultaARP
from backend.contexto_red import consultar_contexto_ipv4
from backend.descubrimiento import observar_consulta_arp
from backend.memoria import MemoriaObservaciones, clave_contexto


class CoordinadorARP:
    """Una ejecución serial y una memoria; las dependencias permiten pruebas sin red."""

    def __init__(self, configuracion=None, *, memoria=None, reloj=monotonic,
                 consultar_contexto=consultar_contexto_ipv4, consultar_arp=consultar_arp_sistema,
                 parada=None):
        self.configuracion = configuracion if configuracion is not None else ConfiguracionBackend()
        if not isinstance(self.configuracion, ConfiguracionBackend):
            raise TypeError("configuracion debe ser una ConfiguracionBackend.")
        self.memoria = memoria if memoria is not None else MemoriaObservaciones(
            self.configuracion.memoria, reloj=reloj,
        )
        self.id_ejecucion = str(uuid4())
        self.consulta = ConsultaARP(self.memoria, id_ejecucion=self.id_ejecucion,
                                   configuracion=self.configuracion)
        self._reloj = reloj
        self._consultar_contexto = consultar_contexto
        self._consultar_arp = consultar_arp
        self._parada = parada if parada is not None else Event()
        self._lock = Lock()
        self._iniciado = False
        self._clave = None
        self._id_contexto = None

    def detener(self):
        """Despierta la espera e impide otro ciclo; el ciclo activo termina y se guarda."""
        self._parada.set()

    def consultar_calidad(self, *, id_contexto=None):
        """Conserva la interfaz anterior delegando al lector de resultados."""
        return self.consulta.calidad(id_contexto=id_contexto)

    def consultar_resumen(self, *, id_contexto=None):
        """Conserva la interfaz anterior delegando al lector de resultados."""
        return self.consulta.resumen(id_contexto=id_contexto)

    def _observar(self, ciclo):
        """Consulta ambas fuentes actuales, construye y guarda exactamente un intento."""
        consulta = self._consultar_contexto(self.configuracion.limite_contexto_s)
        lectura = self._consultar_arp()
        fin_consulta = self._reloj()
        observacion = observar_consulta_arp(lectura, consulta_contexto=consulta)
        clave = clave_contexto(observacion["contexto"])
        if clave is None:
            self._id_contexto = None
        elif clave != self._clave or self._id_contexto is None:
            self._id_contexto = str(uuid4())
        self._clave = clave
        observacion.update(id_ejecucion=self.id_ejecucion, ciclo=ciclo,
                           id_contexto=self._id_contexto)
        self.memoria.guardar(observacion, demora_captura_s=self._reloj() - fin_consulta)
        return observacion

    def ejecutar(self, *, ciclos=None, emitir=None):
        """Ejecuta una vez; espera el intervalo desde el fin de cada ciclo y emisión."""
        if ciclos is not None and (type(ciclos) is not int or ciclos <= 0):
            raise ValueError("ciclos debe ser un entero positivo o None.")
        with self._lock:
            if self._iniciado:
                raise RuntimeError("Este coordinador ya se inició; no admite ejecuciones superpuestas ni reinicios.")
            self._iniciado = True
        completados = 0
        con_incidencias = 0
        while not self._parada.is_set():
            observacion = self._observar(completados + 1)
            completados += 1
            con_incidencias += observacion["estado"] != "observacion_correcta"
            if emitir is not None:
                emitir(observacion)
            if ciclos is not None and completados >= ciclos:
                break
            # No se acumulan plazos vencidos: el siguiente se fija después de terminar.
            siguiente = self._reloj() + self.configuracion.intervalo_arp_s
            while not self._parada.is_set():
                restante = siguiente - self._reloj()
                if restante <= 0:
                    break
                self._parada.wait(restante)
        return {
            "version_esquema": 1, "tipo": "fin_monitoreo_arp",
            "id_ejecucion": self.id_ejecucion,
            "motivo": "detenido" if self._parada.is_set() else "limite_ciclos",
            "ciclos_completados": completados, "ciclos_con_incidencias": con_incidencias,
            "intervalo_arp_s": self.configuracion.intervalo_arp_s,
            "memoria": self.memoria.estadisticas(),
        }
