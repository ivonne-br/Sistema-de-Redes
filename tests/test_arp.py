"""Pruebas del intérprete ARP con textos ficticios, sin acceso a la red."""

import unittest

from backend.arp import interpretar_linea_arp, interpretar_tabla_arp

class PruebasInterpreteArp(unittest.TestCase):
    def test_extrae_campos_y_normaliza_mac(self):
        linea = (
            "? (192.0.2.25) at 2:AB:0:0:0:25 "
            "on en0 ifscope permanent [ethernet]"
        )

        resultado = interpretar_linea_arp(linea)

        self.assertEqual(
            resultado,
            {
                "ipv4": "192.0.2.25",
                "mac": "02:ab:00:00:00:25",
                "interfaz": "en0",
                "marcas": ["ifscope", "permanent"],
                "tipo_enlace": "ethernet",
            },
        )

    def test_acepta_entrada_sin_marcas_y_con_espacios_exteriores(self):
        linea = (
            "  ? (192.0.2.25) at 02:00:00:00:00:25 "
            "on en0 [ethernet]\n"
        )

        resultado = interpretar_linea_arp(linea)

        self.assertEqual(resultado["marcas"], [])
        self.assertEqual(resultado["ipv4"], "192.0.2.25")
        self.assertEqual(resultado["mac"], "02:00:00:00:00:25")

    def test_entrada_incompleta_conserva_mac_ausente(self):
        linea = (
            "? (192.0.2.26) at (incomplete) "
            "on en0 ifscope [ethernet]"
        )

        resultado = interpretar_linea_arp(linea)

        self.assertEqual(
            resultado,
            {
                "ipv4": "192.0.2.26",
                "mac": None,
                "interfaz": "en0",
                "marcas": ["ifscope"],
                "tipo_enlace": "ethernet",
            },
        )

    def test_rechaza_lineas_invalidas(self):
        lineas = (
            "",
            "? (999.0.2.25) at 02:00:00:00:00:25 on en0 [ethernet]",
            "? (::1) at 02:00:00:00:00:25 on en0 [ethernet]",
            "? (192.0.2.25) at 02:00:00:00:25 on en0 [ethernet]",
            "? (192.0.2.25) at 02:00:00:00:00:GG on en0 [ethernet]",
            "? (192.0.2.26) at (incomplete) on en0 [ethernet] extra",
        )

        for linea in lineas:
            with self.subTest(linea=linea):
                with self.assertRaises(ValueError):
                    interpretar_linea_arp(linea)

class PruebasTablaArp(unittest.TestCase):
    def test_conserva_entradas_completas_e_incompletas(self):
        texto = (
            "? (192.0.2.25) at 2:0:0:0:0:25 on en0 [ethernet]\n"
            "? (192.0.2.26) at (incomplete) on en0 ifscope [ethernet]\n"
        )

        resultado = interpretar_tabla_arp(texto)

        self.assertEqual(resultado["errores"], [])
        self.assertEqual(len(resultado["entradas"]), 2)
        self.assertEqual(
            resultado["entradas"][0]["mac"], "02:00:00:00:00:25"
        )
        self.assertEqual(
            resultado["entradas"][1]["ipv4"], "192.0.2.26"
        )
        self.assertIsNone(resultado["entradas"][1]["mac"])

    def test_conserva_entradas_antes_y_despues_de_un_error(self):
        texto = (
            "? (192.0.2.25) at 02:00:00:00:00:25 on en0 [ethernet]\n"
            "\n"
            "línea no reconocida\n"
            "? (192.0.2.26) at (incomplete) on en0 [ethernet]\n"
        )

        resultado = interpretar_tabla_arp(texto)

        self.assertEqual(
            [entrada["ipv4"] for entrada in resultado["entradas"]],
            ["192.0.2.25", "192.0.2.26"],
        )
        self.assertEqual(len(resultado["errores"]), 1)
        self.assertEqual(resultado["errores"][0]["numero_linea"], 3)
        self.assertTrue(resultado["errores"][0]["detalle"])

    def test_texto_vacio_o_en_blanco_no_produce_errores(self):
        for texto in ("", "\n", "  \n\t\n"):
            with self.subTest(texto=texto):
                self.assertEqual(
                    interpretar_tabla_arp(texto),
                    {"entradas": [], "errores": []},
                )

    def test_texto_invalido_no_se_confunde_con_texto_vacio(self):
        texto = (
            "línea no reconocida\n"
            "? (999.0.2.25) at (incomplete) on en0 [ethernet]\n"
        )

        resultado = interpretar_tabla_arp(texto)

        self.assertEqual(resultado["entradas"], [])
        self.assertEqual(
            [error["numero_linea"] for error in resultado["errores"]],
            [1, 2],
        )
        for error in resultado["errores"]:
            self.assertTrue(error["detalle"])

if __name__ == "__main__":
    unittest.main()