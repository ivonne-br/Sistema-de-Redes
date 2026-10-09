import copy
import unittest

from backend.arp import crear_contexto_arp, clasificar_entradas_arp, interpretar_tabla_arp


class PruebasClasificacionArp(unittest.TestCase):
    def test_categorias_conservan_entradas_y_resolucion_independiente(self):
        casos = [
            ('192.0.2.10', 'en0', 'equipo_propio'),
            ('192.0.2.1', 'en0', 'gateway'),
            ('192.0.2.25', 'en0', 'vecino'),
            ('192.0.2.255', 'en0', 'broadcast'),
            ('255.255.255.255', 'en0', 'broadcast'),
            ('224.0.0.251', 'en0', 'multicast'),
            ('239.255.255.250', 'en0', 'multicast'),
            ('192.0.2.0', 'en0', 'direccion_red'),
            ('198.51.100.1', 'en0', 'fuera_subred'),
            ('192.0.2.1', 'en1', 'otra_interfaz'),
        ]
        for mac in ('2:0:0:0:0:1', '(incomplete)'):
            with self.subTest(mac=mac):
                texto = '\n'.join(f'? ({ip}) at {mac} on {interfaz} ifscope [ethernet]' for ip, interfaz, _ in casos)
                entradas = interpretar_tabla_arp(texto)['entradas']
                original = copy.deepcopy(entradas)
                resultado = clasificar_entradas_arp(entradas, 'en0', '192.0.2.10/24', '192.0.2.1')
                self.assertEqual(entradas, original)
                self.assertEqual([e['categoria'] for e in resultado], [c[2] for c in casos])
                for entrada, clasificada in zip(entradas, resultado):
                    self.assertIsNot(entrada, clasificada)
                    self.assertTrue(clasificada['motivo'])
                    self.assertEqual(clasificada['resolucion_mac'], 'incompleta' if mac == '(incomplete)' else 'resuelta')
                    for campo, valor in entrada.items():
                        self.assertEqual(clasificada[campo], valor)

    def test_contexto_invalido_incluso_sin_entradas(self):
        for interfaz, local, gateway in [
            ('', '192.0.2.10/24', None),
            ('en 0', '192.0.2.10/24', None),
            ('en0', '192.0.2.10', None),
            ('en0', '192.0.2.10/33', None),
            ('en0', '::1/128', None),
            ('en0', '192.0.2.0/24', None),
            ('en0', '192.0.2.255/24', None),
            ('en0', '224.0.0.1/24', None),
            ('en0', '192.0.2.10/24', '198.51.100.1'),
            ('en0', '192.0.2.10/24', '192.0.2.255'),
            ('en0', '192.0.2.10/24', '192.0.2.10'),
        ]:
            with self.subTest(local=local, gateway=gateway, interfaz=interfaz):
                with self.assertRaises(ValueError):
                    clasificar_entradas_arp([], interfaz, local, gateway)

    def test_gateway_opcional_y_mascara_decimal(self):
        contexto = crear_contexto_arp('en0', '192.0.2.10/255.255.255.0')
        self.assertEqual(contexto['subred'], '192.0.2.0/24')
        self.assertIsNone(contexto['gateway'])
        self.assertEqual(clasificar_entradas_arp([], 'en0', '192.0.2.10/24'), [])
        entradas = interpretar_tabla_arp('? (192.0.2.1) at (incomplete) on en0 [ethernet]')['entradas']
        self.assertEqual(clasificar_entradas_arp(entradas, 'en0', '192.0.2.10/24')[0]['categoria'], 'vecino')

    def test_prefijos_31_y_32_no_tienen_broadcast_de_subred(self):
        for local, ip, categoria in [('192.0.2.0/31', '192.0.2.1', 'vecino'), ('192.0.2.1/32', '192.0.2.1', 'equipo_propio')]:
            with self.subTest(local=local):
                entradas = interpretar_tabla_arp(f'? ({ip}) at (incomplete) on en0 [ethernet]')['entradas']
                resultado = clasificar_entradas_arp(entradas, 'en0', local)
                self.assertEqual(resultado[0]['categoria'], categoria)


if __name__ == '__main__':
    unittest.main()
