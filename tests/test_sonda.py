"""Pruebas de la sonda con salidas simuladas: no envían paquetes a la red."""

import subprocess
import unittest
from datetime import datetime
from unittest.mock import patch

from backend.sonda import ejecutar_sonda

# Clase de pruebas para la función ejecutar_sonda. Se simula la salida del comando ping para probar diferentes escenarios.
class PruebasSonda(unittest.TestCase):
    # Dirección de ejemplo; subprocess.run siempre está sustituido por un mock.
    # mock sustituto configura la salida de ping para simular diferentes escenarios.
    destino = "192.0.2.1"

    def setUp(self):
        sistema = patch("backend.sonda.platform.system", return_value="Darwin")
        self.sistema = sistema.start()
        self.addCleanup(sistema.stop)
        proceso = patch("backend.sonda.subprocess.run")
        self.proceso = proceso.start()
        self.addCleanup(proceso.stop)

    def simular_salida(self, codigo=0, salida="", error=""):
        self.proceso.return_value = subprocess.CompletedProcess(
            args=[], returncode=codigo, stdout=salida, stderr=error
        )

    def comprobar_sin_rtt(self, resultado, estado):
        self.assertEqual(resultado["estado"], estado)
        self.assertIsNone(resultado["rtt_ms"])
        self.assertTrue(resultado["detalle"])

    def test_respuesta_valida_conserva_rtt_destino_y_fecha(self):
        self.simular_salida(
            salida="64 bytes from 192.0.2.1: icmp_seq=0 ttl=64 time=3.381 ms\n"
        )
        resultado = ejecutar_sonda(self.destino)
        self.assertEqual(resultado["estado"], "respuesta_valida")
        self.assertEqual(resultado["rtt_ms"], 3.381)
        self.assertEqual(resultado["destino"], self.destino)
        self.assertIsNone(resultado["detalle"])
        self.assertIsNotNone(datetime.fromisoformat(resultado["inicio"]).tzinfo)

        # La prueba debe pedir una sola sonda, con límites de espera y ejecución.
        self.proceso.assert_called_once()
        argumentos, opciones = self.proceso.call_args
        comando = argumentos[0]
        self.assertEqual(comando[comando.index("-c") + 1], "1")
        self.assertEqual(comando[comando.index("-W") + 1], "1000")
        self.assertEqual(opciones["timeout"], 5)
        self.assertFalse(opciones.get("shell", False))

    def test_envio_sin_respuesta_no_produce_rtt_cero(self):
        self.simular_salida(codigo=2)
        self.comprobar_sin_rtt(ejecutar_sonda(self.destino), "sin_respuesta")

    def test_error_informado_por_ping_no_se_cuenta_como_ausencia(self):
        for codigo in (0, 2, 64):
            with self.subTest(codigo=codigo):
                self.simular_salida(codigo=codigo, error="ping: sendto: error")
                self.comprobar_sin_rtt(
                    ejecutar_sonda(self.destino), "error_recoleccion"
                )

    def test_codigo_de_error_sin_diagnostico(self):
        self.simular_salida(codigo=64)
        self.comprobar_sin_rtt(ejecutar_sonda(self.destino), "error_recoleccion")

    def test_error_local_impide_clasificar_la_conectividad(self):
        for error in (PermissionError(), FileNotFoundError()):
            with self.subTest(error=type(error).__name__):
                self.proceso.side_effect = error
                self.comprobar_sin_rtt(
                    ejecutar_sonda(self.destino), "error_recoleccion"
                )

    def test_limite_del_proceso_es_error_de_recoleccion(self):
        self.proceso.side_effect = subprocess.TimeoutExpired(cmd="ping", timeout=5)
        self.comprobar_sin_rtt(ejecutar_sonda(self.destino), "error_recoleccion")

    def test_salida_inesperada_u_otro_destino_no_inventan_rtt(self):
        for salida in (
            "salida no reconocida",
            "64 bytes from 192.0.2.2: icmp_seq=0 ttl=64 time=3.381 ms\n",
        ):
            with self.subTest(salida=salida):
                self.simular_salida(salida=salida)
                self.comprobar_sin_rtt(
                    ejecutar_sonda(self.destino), "error_recoleccion"
                )

    def test_respuesta_tardia_no_se_utiliza_como_rtt_valido(self):
        self.simular_salida(
            salida="64 bytes from 192.0.2.1: icmp_seq=0 ttl=64 time=1001.5 ms\n"
        )
        self.comprobar_sin_rtt(ejecutar_sonda(self.destino), "sin_respuesta")

    def test_destino_invalido_se_rechaza_sin_ejecutar_ping(self):
        for destino in ("no-es-una-ip", "192.0.2.1; otro-comando", "::1"):
            with self.subTest(destino=destino):
                with self.assertRaises(ValueError):
                    ejecutar_sonda(destino)
        self.proceso.assert_not_called()

    def test_otro_sistema_no_ejecuta_ping_con_opciones_de_macos(self):
        self.sistema.return_value = "Linux"
        self.comprobar_sin_rtt(ejecutar_sonda(self.destino), "error_recoleccion")
        self.proceso.assert_not_called()


if __name__ == "__main__":
    unittest.main()
