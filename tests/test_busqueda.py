"""Entradas y sondas artificiales verifican búsqueda, fechas, límites y separación de contextos sin red."""

from threading import Barrier, Lock, Thread
import unittest

from backend.busqueda import BusquedaLocal, destinos_locales
from backend.configuracion import interpretar_configuracion


class PruebasBusqueda(unittest.TestCase):
    def setUp(self):
        self.actual = {"id_contexto": "A", "contexto": {
            "ipv4_local": "192.168.0.56/24", "gateway": "192.168.0.1"},
            "entradas": [{"ipv4": "192.168.0.120", "categoria": "vecino"}]}
        self.ahora = 10
        self.llamadas = []
        self.respuesta = "respuesta_valida"
        def sonda(ip, config):
            self.llamadas.append(ip)
            self.assertEqual(config.limite_proceso_s, 2)
            return {"estado": self.respuesta}
        self.busqueda = BusquedaLocal(lambda: self.actual, sonda=sonda, reloj=lambda: self.ahora)

    def test_explora_desconocidas_y_excluye_local_gateway_red_broadcast(self):
        self.busqueda.barrer()
        self.assertEqual(len(set(self.llamadas)), 252)
        self.assertIn("192.168.0.168", self.llamadas)
        self.assertEqual(self.llamadas[0], "192.168.0.120")
        for final in (0, 1, 56, 255):
            self.assertNotIn(f"192.168.0.{final}", self.llamadas)
        estado = self.busqueda.estado(id_contexto="A")
        self.assertEqual(estado["consultados"], 252)
        self.assertEqual(estado["estado"], "en_espera")
        self.assertEqual(estado["contexto"]["ipv4_local"], "192.168.0.56/24")
        estado["contexto"]["ipv4_local"] = "alterado"
        self.assertEqual(self.actual["contexto"]["ipv4_local"], "192.168.0.56/24")

    def test_silencio_no_borra_ultima_respuesta_y_consultar_no_sondea(self):
        self.busqueda.barrer()
        antes = self.busqueda.estado(id_contexto="A")["resultados"][0]
        self.respuesta = "sin_respuesta"
        self.ahora = 20
        self.busqueda.barrer()
        self.ahora = 201
        despues = self.busqueda.estado(id_contexto="A")["resultados"][0]
        self.assertEqual(despues["estado"], "sin_respuesta")
        self.assertEqual(despues["ultima_respuesta"], antes["ultima_respuesta"])
        self.assertTrue(despues["respondio_alguna_vez"])
        self.assertEqual(despues["antiguedad_s"], 181)
        self.assertEqual(despues["vigencia"], "desactualizado")
        self.assertEqual(len(self.llamadas), 504)
        despues["estado"] = "inventado"
        self.assertEqual(self.busqueda.estado(id_contexto="A")["resultados"][0]["estado"], "sin_respuesta")

    def test_tramos_a_b_a_nuevo_no_conservan_asociaciones_previas(self):
        self.busqueda.barrer()
        self.assertEqual(self.busqueda.estado(id_contexto="B")["resultados"], [])
        self.assertIsNone(self.busqueda.estado(id_contexto="B")["contexto"])
        for identificador in ("B", "A-nuevo"):
            self.actual["id_contexto"] = identificador
            self.respuesta = "sin_respuesta"
            self.busqueda.barrer()
            filas = self.busqueda.estado(id_contexto=identificador)["resultados"]
            self.assertTrue(all(not fila["respondio_alguna_vez"] for fila in filas))
            self.assertTrue(all(fila["ultima_respuesta"] is None for fila in filas))

    def test_contexto_cambia_durante_lote_descarta_resultados(self):
        def cambiar(ip, config):
            self.actual["id_contexto"] = "B"
            return {"estado": "respuesta_valida"}
        self.busqueda._sonda = cambiar
        self.busqueda.barrer()
        self.assertEqual(self.busqueda.estado(id_contexto="A")["resultados"], [])
        self.assertEqual(self.busqueda.estado(id_contexto="B")["resultados"], [])

    def test_subred_grande_publica_y_contexto_ausente_no_envian(self):
        for direccion in ("192.168.0.56/23", "8.8.8.8/24"):
            self.actual["contexto"]["ipv4_local"] = direccion
            self.busqueda.barrer()
            self.assertEqual(self.busqueda.estado(id_contexto="A")["estado"], "omitida")
        self.actual = None
        self.busqueda.barrer()
        self.assertEqual(self.busqueda.estado()["estado"], "esperando_contexto")
        self.assertEqual(self.llamadas, [])

    def test_error_de_sonda_es_explicito(self):
        self.actual["contexto"]["ipv4_local"] = "192.168.0.2/30"
        self.actual["contexto"]["gateway"] = None
        def fallar(ip, config):
            raise OSError("fuente fallida")
        self.busqueda._sonda = fallar
        self.busqueda.barrer()
        self.assertEqual(self.busqueda.estado(id_contexto="A")["resultados"][0]["estado"], "error_recoleccion")

    def test_ocho_sondas_simultaneas_y_parada_impide_lotes_pendientes(self):
        barrera = Barrier(8, timeout=3)
        lock = Lock()
        cantidad = []
        def sonda(ip, config):
            with lock:
                cantidad.append(ip)
            barrera.wait()
            self.busqueda.detener()
            return {"estado": "sin_respuesta"}
        self.busqueda._sonda = sonda
        hilo = Thread(target=self.busqueda.ejecutar)
        hilo.start()
        hilo.join(4)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(len(cantidad), 8)
        self.assertEqual(self.busqueda.estado(id_contexto="A")["estado"], "detenida")

    def test_configuracion_automatica_y_validacion(self):
        self.assertTrue(interpretar_configuracion('{}').busqueda_activa)
        self.assertEqual(interpretar_configuracion('{}').intervalo_busqueda_s, 60)
        for texto in ('{"busqueda_activa": 1}', '{"intervalo_busqueda_s": false}',
                      '{"intervalo_busqueda_s": 0}', '{"intervalo_busqueda_s": 86401}'):
            with self.subTest(texto=texto), self.assertRaises((ValueError, TypeError)):
                interpretar_configuracion(texto)
