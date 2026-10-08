"""Pruebas del intérprete ARP con textos ficticios, sin acceso a la red."""

import unittest

from backend.arp import interpretar_linea_arp


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


if __name__ == "__main__":
    unittest.main()