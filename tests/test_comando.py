import io
import unittest
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from backend.__main__ import main


class PruebasComando(unittest.TestCase):
    def test_destino_invalido_no_ejecuta_sonda(self):
        errores = io.StringIO() # espacio en memoria para errores

        with patch("sys.argv", ["backend", "sonda", "hola"]): # simula la línea de comandos con un destino inválido
            with patch("backend.__main__.ejecutar_sonda") as sonda:
                with redirect_stderr(errores):
                    with self.assertRaises(SystemExit) as salida:
                        main()

                self.assertEqual(salida.exception.code, 2)
                self.assertIn(
                    "Introduce una dirección IPv4 válida",
                    errores.getvalue(),
                )
                sonda.assert_not_called()

    def test_destino_valido_ejecuta_una_sonda_y_muestra_json(self):
        resultado_simulado = {
            "destino": "192.0.2.1",
            "inicio": "2026-10-04T12:00:00+00:00",
            "metodo": "icmp_ping_macos",
            "espera_ms": 1000,
            "estado": "respuesta_valida",
            "rtt_ms": 3.381,
            "detalle": None,
        }

        salida = io.StringIO()

        with patch("sys.argv", ["backend", "sonda", "192.0.2.1"]):
            with patch(
                "backend.__main__.ejecutar_sonda",
                return_value=resultado_simulado,
            ) as sonda:
                with redirect_stdout(salida):
                    main()

                sonda.assert_called_once_with("192.0.2.1")

        resultado_mostrado = json.loads(salida.getvalue())
        self.assertEqual(resultado_mostrado, resultado_simulado)    

if __name__ == "__main__":
    unittest.main()