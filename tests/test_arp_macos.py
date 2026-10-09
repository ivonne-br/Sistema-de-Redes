"""Buffers controlados: no dependen de permisos ni de la red del equipo."""
import ctypes
import errno
import struct
import unittest
from unittest.mock import patch

from backend.arp_macos import (
    interpretar_cache_arp_sistema, leer_cache_arp_sistema, consultar_arp_sistema,
)


def registro(mac=b'\x02\x00\x00\x00\x00\x25', *, version=5):
    cabecera = bytearray(92)
    destino = bytearray(16)
    destino[:2] = bytes((16, 2))
    destino[4:8] = bytes((192, 0, 2, 25))
    enlace = bytearray(20)
    enlace[:2] = bytes((20, 18))
    struct.pack_into('=H', enlace, 2, 14)
    enlace[4:8] = bytes((6, 0, len(mac), 0))
    enlace[8:8 + len(mac)] = mac
    struct.pack_into('=HBB', cabecera, 0, 128, version, 4)
    struct.pack_into('=II', cabecera, 8, 0x1000400, 3)
    struct.pack_into('=I', cabecera, 48, 1234)
    return bytes(cabecera + destino + enlace)


class PruebasArpSistema(unittest.TestCase):
    def test_normaliza_y_conserva_incompletas(self):
        tabla = interpretar_cache_arp_sistema(registro() + registro(b''), resolver_interfaz=lambda i: 'en0')
        self.assertEqual(tabla['errores'], [])
        self.assertEqual(tabla['entradas'][0], {'ipv4': '192.0.2.25', 'mac': '02:00:00:00:00:25',
                                              'interfaz': 'en0', 'marcas': ['ifscope'], 'tipo_enlace': 'ethernet'})
        self.assertIsNone(tabla['entradas'][1]['mac'])

    def test_version_incompatible_no_oculta_registro_siguiente(self):
        tabla = interpretar_cache_arp_sistema(registro(version=9) + registro(), resolver_interfaz=lambda i: 'en0')
        self.assertEqual(len(tabla['entradas']), 1)
        self.assertEqual(tabla['errores'][0]['numero_registro'], 1)

    def test_truncamiento_y_longitud_cero_no_bucles(self):
        for datos in (b'x', b'\x00' * 100, registro()[:-1]):
            with self.subTest(datos=len(datos)):
                self.assertEqual(len(interpretar_cache_arp_sistema(datos)['errores']), 1)

    def test_limites_direcciones_y_mac(self):
        for offset, valor in ((92, 255), (109, 2), (114, 7), (113, 255)):
            datos = bytearray(registro()); datos[offset] = valor
            with self.subTest(offset=offset):
                self.assertEqual(len(interpretar_cache_arp_sistema(bytes(datos))['errores']), 1)

    def test_interfaz_desconocida_y_tipo_entrada(self):
        with patch('backend.arp_macos.socket.if_indextoname', side_effect=OSError('Interfaz ausente')):
            tabla = interpretar_cache_arp_sistema(registro())
        self.assertEqual(len(tabla['errores']), 1)
        with self.assertRaises(TypeError):
            interpretar_cache_arp_sistema('texto')

    def test_plataforma_y_error_api(self):
        with patch('backend.arp_macos.platform.system', return_value='Linux'):
            with self.assertRaises(OSError):
                leer_cache_arp_sistema()
        with patch('backend.arp_macos.platform.system', return_value='Darwin'), patch('backend.arp_macos.ctypes.CDLL') as lib:
            lib.return_value.sysctl.return_value = -1
            with self.assertRaises(OSError):
                leer_cache_arp_sistema()

    def test_lector_reintenta_crecimiento_y_respeta_bytes_devuelto(self):
        datos = registro()
        def llamada(mib, n, buffer, longitud, nuevo, tam):
            if buffer is None:
                longitud._obj.value = len(datos)
                return 0
            llamada.intentos += 1
            if llamada.intentos == 1:
                ctypes.set_errno(errno.ENOMEM)
                return -1
            ctypes.memmove(buffer, datos, len(datos))
            longitud._obj.value = len(datos)
            return 0
        llamada.intentos = 0
        with patch('backend.arp_macos.platform.system', return_value='Darwin'), patch('backend.arp_macos.ctypes.CDLL') as lib:
            lib.return_value.sysctl.side_effect = llamada
            self.assertEqual(leer_cache_arp_sistema(), datos)
        self.assertEqual(llamada.intentos, 2)

    def test_lector_acota_memoria_y_reintentos(self):
        def llamada(mib, n, buffer, longitud, nuevo, tam):
            longitud._obj.value = 17 * 1024 * 1024
            return 0
        with patch('backend.arp_macos.platform.system', return_value='Darwin'), patch('backend.arp_macos.ctypes.CDLL') as lib:
            lib.return_value.sysctl.side_effect = llamada
            with self.assertRaises(OSError):
                leer_cache_arp_sistema()
        def crecimiento(mib, n, buffer, longitud, nuevo, tam):
            if buffer is None:
                longitud._obj.value = 128
                return 0
            ctypes.set_errno(errno.ENOMEM)
            return -1
        with patch('backend.arp_macos.platform.system', return_value='Darwin'), patch('backend.arp_macos.ctypes.CDLL') as lib:
            lib.return_value.sysctl.side_effect = crecimiento
            with self.assertRaises(OSError):
                leer_cache_arp_sistema()
            self.assertEqual(lib.return_value.sysctl.call_count, 6)

    def test_consulta_estados_y_no_inventa_visibilidad(self):
        casos = ((b'', 'sin_datos_visibles'), (registro(), 'lectura_correcta'),
                 (registro(version=9), 'error_interpretacion'),
                 (registro() + registro(version=9), 'lectura_parcial'))
        for datos, estado in casos:
            with self.subTest(estado=estado), patch('backend.arp_macos.leer_cache_arp_sistema', return_value=datos), patch('backend.arp_macos.socket.if_indextoname', return_value='en0'):
                resultado = consultar_arp_sistema()
                self.assertEqual(resultado['estado'], estado)
                self.assertEqual(resultado['bytes_recibidos'], len(datos))
                self.assertLessEqual(resultado['inicio_captura'], resultado['fin_captura'])
        with patch('backend.arp_macos.leer_cache_arp_sistema', side_effect=OSError('Permiso denegado')):
            self.assertEqual(consultar_arp_sistema()['estado'], 'error_recoleccion')
