"""Pruebas del intérprete ARP con textos ficticios, sin acceso a la red."""

import unittest
import subprocess
import json

from datetime import datetime
from unittest.mock import patch
from backend.arp import (
    interpretar_linea_arp,
    interpretar_tabla_arp,
    leer_cache_arp,
    consultar_arp,
    diagnosticar_arp,
)

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

class PruebasLecturaArp(unittest.TestCase):
    def setUp(self):
        sistema = patch("backend.arp.platform.system", return_value="Darwin")
        self.sistema = sistema.start()
        self.addCleanup(sistema.stop)

        proceso = patch("backend.arp.subprocess.run")
        self.proceso = proceso.start()
        self.addCleanup(proceso.stop)

    def test_lectura_correcta_conserva_texto_y_limite(self):
        texto = "? (192.0.2.25) at 02:00:00:00:00:25 on en0 [ethernet]\n"
        self.proceso.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=texto, stderr=""
        )

        resultado = leer_cache_arp(5)

        self.assertEqual(
            resultado,
            {
                "estado": "lectura_correcta",
                "texto": texto,
                "detalle": None,
            },
        )
        self.proceso.assert_called_once()
        argumentos, opciones = self.proceso.call_args
        self.assertEqual(argumentos[0], ["/usr/sbin/arp", "-an"])
        self.assertEqual(opciones["timeout"], 5)
        self.assertTrue(opciones["capture_output"])
        self.assertTrue(opciones["text"])
        self.assertEqual(opciones["env"]["LC_ALL"], "C")
        self.assertFalse(opciones.get("shell", False))

    def test_salida_vacia_es_una_lectura_correcta(self):
        self.proceso.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        resultado = leer_cache_arp(5)

        self.assertEqual(resultado["estado"], "lectura_correcta")
        self.assertEqual(resultado["texto"], "")
        self.assertIsNone(resultado["detalle"])

    def test_fallos_de_ejecucion_no_producen_texto_vacio(self):
        fallos = (
            subprocess.TimeoutExpired(cmd="arp", timeout=5),
            FileNotFoundError(),
            PermissionError(),
            UnicodeError(),
        )

        for fallo in fallos:
            with self.subTest(fallo=type(fallo).__name__):
                self.proceso.side_effect = fallo

                resultado = leer_cache_arp(5)

                self.assertEqual(resultado["estado"], "error_recoleccion")
                self.assertIsNone(resultado["texto"])
                self.assertTrue(resultado["detalle"])

    def test_error_informado_por_comando_no_se_interpreta_como_exito(self):
        for codigo, error in ((1, ""), (0, "error simulado")):
            with self.subTest(codigo=codigo, error=error):
                self.proceso.return_value = subprocess.CompletedProcess(
                    args=[], returncode=codigo, stdout="", stderr=error
                )

                resultado = leer_cache_arp(5)

                self.assertEqual(resultado["estado"], "error_recoleccion")
                self.assertIsNone(resultado["texto"])
                self.assertTrue(resultado["detalle"])

    def test_otro_sistema_no_ejecuta_arp(self):
        self.sistema.return_value = "Linux"

        resultado = leer_cache_arp(5)

        self.assertEqual(resultado["estado"], "error_recoleccion")
        self.assertIsNone(resultado["texto"])
        self.proceso.assert_not_called()

    def test_limite_invalido_no_ejecuta_arp(self):
        casos = (
            ("5", TypeError),
            (True, TypeError),
            (0, ValueError),
            (-1, ValueError),
        )

        for valor, error in casos:
            with self.subTest(valor=valor):
                with self.assertRaises(error):
                    leer_cache_arp(valor)

        self.proceso.assert_not_called()

class PruebasConsultaArp(unittest.TestCase):
    def test_distingue_resultados_de_interpretacion(self):
        linea = (
            "? (192.0.2.25) at 2:0:0:0:0:25 "
            "on en0 [ethernet]\n"
        )
        casos = (
            (linea, "lectura_correcta", 1, 0),
            (linea + "texto inválido\n", "lectura_parcial", 1, 1),
            ("texto inválido\n", "error_interpretacion", 0, 1),
        )

        for texto, estado, cantidad_entradas, cantidad_errores in casos:
            with self.subTest(estado=estado, texto=texto):
                lectura = {
                    "estado": "lectura_correcta",
                    "texto": texto,
                    "detalle": None,
                }

                with patch(
                    "backend.arp.leer_cache_arp",
                    return_value=lectura,
                ) as leer:
                    resultado = consultar_arp(5)

                leer.assert_called_once_with(5)
                self.assertEqual(resultado["estado"], estado)
                self.assertEqual(
                    len(resultado["entradas"]), cantidad_entradas
                )
                self.assertEqual(
                    len(resultado["errores"]), cantidad_errores
                )
                self.assertEqual(resultado["fuente"], "cache_arp_macos")
                self.assertIsNotNone(
                    datetime.fromisoformat(resultado["inicio"]).tzinfo
                )

                if cantidad_entradas:
                    self.assertEqual(
                        resultado["entradas"][0]["mac"],
                        "02:00:00:00:00:25",
                    )

                if cantidad_errores:
                    self.assertTrue(resultado["detalle"])
                    self.assertEqual(
                        resultado["errores"][0]["numero_linea"],
                        2 if cantidad_entradas else 1,
                    )
                else:
                    self.assertIsNone(resultado["detalle"])

    def test_consulta_vacia_informa_visibilidad_indeterminada(self):
        for texto in ("", " \n\t\n"):
            with self.subTest(texto=texto):
                lectura = {
                    "estado": "lectura_correcta",
                    "texto": texto,
                    "detalle": None,
                }
                with patch("backend.arp.leer_cache_arp", return_value=lectura):
                    resultado = consultar_arp(5)

                self.assertEqual(resultado["estado"], "lectura_sin_entradas")
                self.assertEqual(resultado["entradas"], [])
                self.assertEqual(resultado["errores"], [])
                self.assertIn("No se puede determinar", resultado["detalle"])
                self.assertIn("visibilidad", resultado["detalle"])

    def test_fallo_de_lectura_no_ejecuta_el_interprete(self):
        lectura = {
            "estado": "error_recoleccion",
            "texto": None,
            "detalle": "No se pudo ejecutar arp.",
        }

        with patch("backend.arp.leer_cache_arp", return_value=lectura):
            with patch("backend.arp.interpretar_tabla_arp") as interpretar:
                resultado = consultar_arp(5)

        interpretar.assert_not_called()
        self.assertEqual(resultado["estado"], "error_recoleccion")
        self.assertEqual(resultado["entradas"], [])
        self.assertEqual(resultado["errores"], [])
        self.assertEqual(resultado["detalle"], lectura["detalle"])


class PruebasDiagnosticoArp(unittest.TestCase):
    def setUp(self):
        sistema = patch('backend.arp.platform.system', return_value='Darwin')
        sistema.start()
        self.addCleanup(sistema.stop)
        proceso = patch('backend.arp.subprocess.run')
        self.proceso = proceso.start()
        self.addCleanup(proceso.stop)

    def test_puntos_de_control_con_texto_valido_y_referencia_sin_datos_identificables(self):
        texto = '? (192.0.2.25) at 02:00:00:00:00:25 on en0 [ethernet]\n'
        self.proceso.return_value = subprocess.CompletedProcess([], 0, texto, '')
        r = diagnosticar_arp(texto_referencia=texto)
        self.assertEqual(r['estado'], 'diagnostico_con_datos')
        self.assertEqual(r['estado_lectura'], 'lectura_correcta')
        self.assertEqual(r['conclusion'], 'texto_recibido_e_interpretado')
        d = r['diagnostico']
        self.assertTrue(d['ejecucion_completada'])
        self.assertEqual(d['codigo_salida'], 0)
        self.assertEqual(d['tipo_stdout'], 'str')
        self.assertEqual(d['stdout_caracteres'], len(texto))
        self.assertEqual(d['stdout_lineas'], 1)
        self.assertEqual(d['stderr_caracteres'], 0)
        self.assertTrue(d['interpretacion_ejecutada'])
        self.assertEqual((d['entradas'], d['errores']), (1, 0))
        self.assertEqual(r['referencia']['entradas'], 1)
        self.assertLessEqual(r['inicio'], r['fin'])
        contenido = json.dumps(r)
        self.assertNotIn('192.0.2.25', contenido)
        self.assertNotIn('02:00:00:00:00:25', contenido)
        self.proceso.assert_called_once()

    def test_captura_vacia_no_se_atribuye_a_conversion_o_permisos(self):
        texto = '? (192.0.2.25) at (incomplete) on en0 [ethernet]\n'
        self.proceso.return_value = subprocess.CompletedProcess([], 0, '', '')
        r = diagnosticar_arp(texto_referencia=texto)
        self.assertEqual(r['estado'], 'diagnostico_sin_datos')
        self.assertEqual(r['conclusion'], 'python_sin_datos_con_referencia_interpretable')
        self.assertEqual(r['diagnostico']['stdout_caracteres'], 0)
        self.assertEqual(r['diagnostico']['tipo_stdout'], 'str')
        self.assertTrue(r['diagnostico']['interpretacion_ejecutada'])
        self.assertEqual(r['diagnostico']['entradas'], 0)
        for referencia in (None, '', 'incorrecto'):
            with self.subTest(referencia=referencia):
                r = diagnosticar_arp(texto_referencia=referencia)
                self.assertEqual(r['conclusion'], 'python_sin_datos_sin_referencia_interpretable')

    def test_datos_recibidos_con_formato_invalido_o_parcial(self):
        valido = '? (192.0.2.25) at (incomplete) on en0 [ethernet]\n'
        for texto, estado, entradas in [('incorrecto', 'error_interpretacion', 0),
                                       (valido+'incorrecto', 'lectura_parcial', 1)]:
            with self.subTest(estado=estado):
                self.proceso.return_value = subprocess.CompletedProcess([], 0, texto, '')
                r = diagnosticar_arp()
                self.assertEqual(r['estado'], 'diagnostico_con_errores')
                self.assertEqual(r['estado_lectura'], estado)
                self.assertGreater(r['diagnostico']['stdout_caracteres'], 0)
                self.assertEqual((r['diagnostico']['entradas'], r['diagnostico']['errores']), (entradas, 1))

    def test_etapas_de_fallos_y_no_interpretacion(self):
        for fallo, etapa in [(subprocess.TimeoutExpired('arp', 5), 'ejecucion'),
                             (FileNotFoundError(), 'ejecucion'),
                             (PermissionError(), 'ejecucion'),
                             (UnicodeError(), 'decodificacion')]:
            with self.subTest(fallo=type(fallo).__name__):
                self.proceso.side_effect = fallo
                r = diagnosticar_arp()
                self.assertEqual(r['estado'], 'error_recoleccion')
                self.assertEqual(r['diagnostico']['etapa'], etapa)
                self.assertEqual(r['diagnostico']['excepcion'], type(fallo).__name__)
                self.assertFalse(r['diagnostico']['ejecucion_completada'])
                self.assertFalse(r['diagnostico']['interpretacion_ejecutada'])
                self.assertIsNone(r['diagnostico']['stdout_caracteres'])

    def test_codigo_o_stderr_y_tipo_salida_incorrecto(self):
        for codigo, stdout, stderr, etapa in [(1, '', '', 'error_comando'),
                                             (0, '', 'fallo', 'error_comando'),
                                             (0, b'datos', '', 'tipo_salida'),
                                             (0, '', None, 'tipo_salida')]:
            with self.subTest(etapa=etapa, codigo=codigo):
                self.proceso.return_value = subprocess.CompletedProcess([], codigo, stdout, stderr)
                r = diagnosticar_arp()
                self.assertEqual(r['diagnostico']['etapa'], etapa)
                self.assertEqual(r['diagnostico']['codigo_salida'], codigo)
                self.assertTrue(r['diagnostico']['ejecucion_completada'])
                self.assertFalse(r['diagnostico']['interpretacion_ejecutada'])
                self.assertEqual(r['estado'], 'error_recoleccion')

    def test_otro_sistema_no_ejecuta_y_referencia_invalida_no_inicia_consulta(self):
        with patch('backend.arp.platform.system', return_value='Linux'):
            r = diagnosticar_arp()
        self.assertEqual(r['diagnostico']['etapa'], 'plataforma_no_compatible')
        self.proceso.assert_not_called()
        with self.assertRaises(TypeError):
            diagnosticar_arp(texto_referencia=25)
        with self.assertRaises(TypeError):
            leer_cache_arp(5, diagnostico=1)
        self.proceso.assert_not_called()

if __name__ == "__main__":
    unittest.main()
