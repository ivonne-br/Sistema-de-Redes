"""Comprueba copias DHCP/WAN sintéticas y el CLI sin red ni datos privados.

Entradas: tablas del formato observado, incompletas y alteradas. Salidas:
inventario, contadores y errores del intérprete conectado a backend.__main__.
"""

import io
import json
import unicodedata
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from backend.__main__ import main
from backend.router_texto import interpretar_texto_router, LIMITE_TEXTO


DHCP = '''Tabla DHCP
HostNameDirección MACDirección IPTipoEstadoExpira enTipo de Conexión
Consola02:00:00:00:00:01192.0.2.2DHCPInactivo10h 15m 41sEthernet
Tablet02:00:00:00:00:02192.0.2.3DHCPActivo0mWiFi 5G
Detalles de la conexión LAN IPv6
texto no interpretado
'''


def wan(familia='IPv4', rx=115000674595, tx=5326354637):
    """Construye una tabla sintética con columnas explícitas y bytes grandes."""
    titulo = 'Estadísticas IPv4 WAN' if familia == 'IPv4' else 'Estadísticas de IPv6 WAN'
    return f'''{titulo}
Interfaz
Tipo
Bytes Rx
Paquetes
Errores
Perdidas
Bytes Tx
Paquetes
Errores
Perdidas
WAN_PRUEBA
pppoe
{rx}
100
0
0
{tx}
50
0
0
'''


def copia():
    return wan() + wan('IPv6', 200, 100) + 'Estado LAN\n' + DHCP


class PruebasTextoRouter(unittest.TestCase):
    def test_dhcp_copiado_por_celdas_conserva_columnas(self):
        texto = '''Tabla DHCP
HostName
Dirección MAC
Dirección IP
Tipo
Estado
Expira en
Tipo de Conexión
Consola de prueba
02:00:00:00:00:01
192.0.2.2
DHCP
Inactivo
0h 13m 48s
Ethernet
Detalles de la conexión LAN IPv6
'''
        resultado = interpretar_texto_router(texto)
        self.assertEqual(resultado['inventario']['estado'], 'interpretado')
        equipo = resultado['inventario']['equipos'][0]
        self.assertEqual(equipo['nombre'], 'Consola de prueba')
        self.assertEqual(equipo['estado_original'], 'Inactivo')
        self.assertEqual(equipo['conexion_original'], 'Ethernet')
        for cambio in ('', 'SECRETO\n'):
            with self.subTest(cambio=cambio):
                parcial = interpretar_texto_router(texto.replace('192.0.2.2\n', cambio))
                self.assertEqual(parcial['inventario']['equipos'], [])
                self.assertNotIn('SECRETO', json.dumps(parcial))

    def test_wan_termina_antes_de_informacion_del_puente(self):
        resultado = interpretar_texto_router(
            copia().replace('Estado LAN\n', 'Información del Puente\nNombre\nVLAN Id\nEstado LAN\n'))
        self.assertEqual(resultado['estado'], 'lectura_correcta')
        self.assertEqual(len(resultado['wan']), 2)

    def test_botones_de_reinicio_no_son_filas_wan(self):
        resultado = interpretar_texto_router(
            wan() + 'Reiniciar las estadísticas\n' + wan('IPv6')
            + 'Reiniciar las estadísticas\nInformación del Puente\nNombre\n' + DHCP)
        self.assertEqual(resultado['estado'], 'lectura_correcta')
        self.assertEqual(len(resultado['wan']), 2)

    def test_normaliza_unicode_y_conserva_estados_y_enteros(self):
        r = interpretar_texto_router(unicodedata.normalize('NFD', copia()))
        self.assertEqual(r['estado'], 'lectura_correcta')
        self.assertEqual(r['inventario']['recuento_filas_interpretadas'],
                         {'total': 2, 'activo': 1, 'inactivo': 1})
        self.assertEqual(r['inventario']['equipos'][0]['estado_original'], 'Inactivo')
        self.assertEqual(r['wan'][0]['bytes_rx'], 115000674595)
        self.assertEqual(r['wan'][0]['bytes_tx'], 5326354637)
        self.assertEqual([c['familia_ip'] for c in r['wan']], ['IPv4', 'IPv6'])
        self.assertIsNone(r['momento_captura'])
        self.assertIsNone(r['contexto_red'])
        self.assertIsNone(r['wan'][0]['inicio_acumulacion'])

    def test_no_usa_nat_wlan_ni_bw_para_modificar_dhcp_o_wan(self):
        r = interpretar_texto_router(copia() + '''Estadísticas WLAN
SSIDBytes RxPaquetesErroresRX PerdidosBytes TxPaquetesTX Perdidos
RED214748364710000
Asignaciones de la tabla NAT
Consola
192.0.2.2
1
BW
866 Mbps
''')
        self.assertEqual(r['estado'], 'lectura_correcta')
        self.assertEqual(len(r['wan']), 2)
        self.assertEqual(r['inventario']['equipos'][0]['estado_original'], 'Inactivo')

    def test_ausencia_no_significa_cero(self):
        r = interpretar_texto_router('Página de acceso\nContraseña')
        self.assertEqual(r['estado'], 'sin_datos_utilizables')
        self.assertIsNone(r['inventario']['recuento_filas_interpretadas']['total'])
        self.assertEqual(r['wan'], [])

    def test_cabecera_sola_no_confirma_tabla_vacia(self):
        texto = '\n'.join(DHCP.splitlines()[:2])
        r = interpretar_texto_router(texto)
        self.assertEqual(r['inventario']['estado'], 'no_disponible')
        self.assertIsNone(r['inventario']['recuento_filas_interpretadas']['activo'])

    def test_fila_dhcp_invalida_no_oculta_las_validas_ni_se_filtra_a_errores(self):
        r = interpretar_texto_router(copia().replace('Tablet02:', 'SECRETO\nTablet02:'))
        self.assertEqual(r['inventario']['estado'], 'parcial')
        self.assertEqual(len(r['inventario']['equipos']), 2)
        self.assertNotIn('SECRETO', json.dumps(r))
        self.assertIsInstance(r['errores'][0]['numero_linea'], int)

    def test_ipv4_invalida_se_rechaza(self):
        r = interpretar_texto_router(copia().replace('192.0.2.2', '999.0.2.2'))
        self.assertEqual(len(r['inventario']['equipos']), 1)
        self.assertEqual(r['inventario']['estado'], 'parcial')

    def test_nombre_vacio_y_conexion_original(self):
        r = interpretar_texto_router(copia().replace('Tablet02:', '02:'))
        self.assertIsNone(r['inventario']['equipos'][1]['nombre'])
        self.assertEqual(r['inventario']['equipos'][1]['conexion_original'], 'WiFi 5G')

    def test_dhcp_duplicado_no_infla_recuento(self):
        fila = DHCP.splitlines()[2]
        r = interpretar_texto_router(copia().replace(fila, fila + '\n' + fila))
        self.assertEqual(r['inventario']['recuento_filas_interpretadas']['total'], 2)
        self.assertEqual(r['inventario']['estado'], 'parcial')

    def test_seccion_duplicada_es_ambigua(self):
        r = interpretar_texto_router(copia() + DHCP)
        self.assertEqual(r['inventario']['equipos'], [])
        self.assertEqual(len(r['wan']), 2)

    def test_wan_incompleta_no_produce_contadores_desplazados(self):
        r = interpretar_texto_router(copia().replace('115000674595\n', ''))
        self.assertEqual([c['familia_ip'] for c in r['wan']], ['IPv6'])
        self.assertEqual(r['estado'], 'lectura_parcial')

    def test_wan_rechaza_negativos_decimales_y_enteros_fuera_de_rango(self):
        for valor in ('-1', '1.2', 'NaN', str(2**64), '9' * 5000):
            with self.subTest(valor=valor[:20]):
                r = interpretar_texto_router(wan(rx=valor))
                self.assertEqual(r['wan'], [])

    def test_wan_conserva_cero_y_maximo_64_bits(self):
        r = interpretar_texto_router(wan(rx=0, tx=2**64 - 1))
        self.assertEqual(r['wan'][0]['bytes_rx'], 0)
        self.assertEqual(r['wan'][0]['bytes_tx'], 2**64 - 1)

    def test_interfaz_duplicada_no_se_elige_arbitrariamente(self):
        tabla = wan()
        fila = '\n'.join(tabla.splitlines()[11:]) + '\n'
        r = interpretar_texto_router(tabla + fila + fila)
        self.assertEqual(r['wan'], [])

    def test_no_admite_texto_sin_limite(self):
        with self.assertRaises(ValueError):
            interpretar_texto_router('x' * (LIMITE_TEXTO + 1))
        with self.assertRaises(TypeError):
            interpretar_texto_router(None)

    def test_cli_lee_copia_sin_consultar_red_ni_logging_privado(self):
        salida, errores = io.StringIO(), io.StringIO()
        with (patch('sys.argv', ['backend', 'interpretar-router', '--desde-stdin']),
              patch('sys.stdin', io.StringIO(copia())),
              patch('backend.__main__.consultar_contexto_ipv4') as contexto,
              patch('backend.__main__.APILocal') as api,
              redirect_stdout(salida), redirect_stderr(errores)):
            main()
        self.assertEqual(json.loads(salida.getvalue())['estado'], 'lectura_correcta')
        contexto.assert_not_called()
        api.assert_not_called()
        self.assertEqual(errores.getvalue(), '')

    def test_cli_salida_parcial_es_uno_y_conserva_json(self):
        salida = io.StringIO()
        with (patch('sys.argv', ['backend', 'interpretar-router', '--desde-stdin']),
              patch('sys.stdin', io.StringIO(DHCP)), redirect_stdout(salida),
              self.assertRaises(SystemExit) as error):
            main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads(salida.getvalue())['estado'], 'lectura_parcial')

    def test_cli_exige_entrada_explicita_no_interactiva(self):
        for opciones in ([], ['--desde-stdin']):
            with (self.subTest(opciones=opciones),
                  patch('sys.argv', ['backend', 'interpretar-router', *opciones]),
                  patch('sys.stdin') as entrada, redirect_stderr(io.StringIO()),
                  self.assertRaises(SystemExit) as error):
                entrada.isatty.return_value = True
                main()
            self.assertEqual(error.exception.code, 2)
            entrada.read.assert_not_called()
