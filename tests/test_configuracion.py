"""Pruebas locales de configuración."""

import unittest

from backend.configuracion import ConfiguracionSonda

class PruebasConfiguracion(unittest.TestCase):
    def test_valores_predeterminados(self):
        configuracion = ConfiguracionSonda()

        self.assertEqual(configuracion.espera_ms, 1000)
        self.assertEqual(configuracion.limite_proceso_s, 5)

    def test_acepta_valores_personalizados_validos(self):
        configuracion = ConfiguracionSonda(
            espera_ms=2000,
            limite_proceso_s=6,
        )

        self.assertEqual(configuracion.espera_ms, 2000)
        self.assertEqual(configuracion.limite_proceso_s, 6)

    def test_rechaza_tipos_incorrectos(self):
        for valor in ("1000", 1.5, True, False, None):
            with self.subTest(campo="espera_ms", valor=valor):
                with self.assertRaises(TypeError):
                    ConfiguracionSonda(espera_ms=valor)

            with self.subTest(campo="limite_proceso_s", valor=valor):
                with self.assertRaises(TypeError):
                    ConfiguracionSonda(limite_proceso_s=valor)

    def test_rechaza_cero_y_negativos(self):
        for valor in (0, -1):
            with self.subTest(campo="espera_ms", valor=valor):
                with self.assertRaises(ValueError):
                    ConfiguracionSonda(espera_ms=valor)

            with self.subTest(campo="limite_proceso_s", valor=valor):
                with self.assertRaises(ValueError):
                    ConfiguracionSonda(limite_proceso_s=valor)

    def test_rechaza_limite_sin_margen_para_la_respuesta(self):
        for espera_ms in (5000, 6000):
            with self.subTest(espera_ms=espera_ms):
                with self.assertRaises(ValueError):
                    ConfiguracionSonda(
                        espera_ms=espera_ms,
                        limite_proceso_s=5,
                    )


if __name__ == "__main__":
    unittest.main()