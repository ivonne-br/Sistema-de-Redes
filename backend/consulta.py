"""Lectura local de resultados ARP; no inicia tareas ni consulta fuentes de red."""

from backend.calidad import evaluar_calidad_arp, resumir_vecinos_arp
from backend.configuracion import ConfiguracionBackend
from backend.memoria import MemoriaObservaciones
from backend.presencia import comparar_presencia_arp


class ConsultaARP:
    """Vista de una ejecución para consumidores como CLI y futura API.

    Comparte la memoria del recolector, pero cada consulta opera sobre una copia.
    Crear más lectores no crea memorias, coordinadores, hilos ni nuevas capturas.
    La caducidad sigue siendo responsabilidad de la memoria al obtener la copia.
    """

    def __init__(self, memoria, *, id_ejecucion, configuracion=None):
        if not isinstance(memoria, MemoriaObservaciones):
            raise TypeError("memoria debe ser una MemoriaObservaciones existente.")
        if not isinstance(id_ejecucion, str) or not id_ejecucion.strip():
            raise ValueError("id_ejecucion debe ser una cadena no vacía.")
        configuracion = configuracion if configuracion is not None else ConfiguracionBackend()
        if not isinstance(configuracion, ConfiguracionBackend):
            raise TypeError("configuracion debe ser una ConfiguracionBackend.")
        self._memoria = memoria
        self._id_ejecucion = id_ejecucion
        self._configuracion = configuracion

    def calidad(self, *, id_contexto=None):
        """Calcula calidad actual sin iniciar una captura ni renovar su fecha."""
        return evaluar_calidad_arp(
            self._memoria.instantanea_temporal(id_ejecucion=self._id_ejecucion),
            id_ejecucion=self._id_ejecucion, id_contexto=id_contexto,
            vigencia_s=self._configuracion.vigencia_arp_s,
        )

    def resumen(self, *, id_contexto=None):
        """Devuelve calidad, recuento y presencia coherentes con una única copia."""
        registros = self._memoria.instantanea_temporal(id_ejecucion=self._id_ejecucion)
        resumen = resumir_vecinos_arp(
            registros, id_ejecucion=self._id_ejecucion, id_contexto=id_contexto,
            vigencia_s=self._configuracion.vigencia_arp_s,
        )
        resumen["presencia"] = comparar_presencia_arp(
            registros, id_ejecucion=self._id_ejecucion,
            id_contexto=resumen["calidad"]["id_contexto"],
            vigencia_s=self._configuracion.vigencia_arp_s,
            ausencias=self._configuracion.ausencias_arp,
        )
        return resumen
