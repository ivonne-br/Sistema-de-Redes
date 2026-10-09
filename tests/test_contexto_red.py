import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from backend.contexto_red import (
    ErrorContexto, consultar_contexto_ipv4, interpretar_ruta_ipv4,
    interpretar_ipv4_interfaz,
)
from backend.__main__ import main

RUTA = "destination: default\ngateway: 192.0.2.1\ninterface: en0\nflags: <UP,GATEWAY,DONE>\n"
INTERFAZ = "en0: flags=8863<UP,BROADCAST> mtu 1500\n\tinet6 fe80::1%en0 prefixlen 64\n\tinet 192.0.2.10 netmask 0xffffff00 broadcast 192.0.2.255\n"


def lectura(texto=RUTA, codigo=0, error=""):
    return dict(texto=texto, codigo=codigo, error=error)


def proceso(texto, codigo=0, error=""):
    return subprocess.CompletedProcess([], codigo, texto, error)


class PruebasContexto(unittest.TestCase):
    def test_ruta_y_mascaras(self):
        self.assertEqual(interpretar_ruta_ipv4(lectura()), {"interfaz": "en0", "gateway": "192.0.2.1"})
        for mascara, prefijo in (("0xffffff00", 24), ("0xffffe000", 19), ("255.255.255.0", 24)):
            with self.subTest(mascara=mascara):
                self.assertEqual(interpretar_ipv4_interfaz(INTERFAZ.replace("0xffffff00", mascara), "en0"), f"192.0.2.10/{prefijo}")
        directa = RUTA.replace("192.0.2.1", "link#4").replace(",GATEWAY", "")
        self.assertIsNone(interpretar_ruta_ipv4(lectura(directa))["gateway"])

    def test_ruta_ausente_y_errores_no_se_confunden(self):
        casos = [
            (lectura("", 1, "route: writing to routing socket: not in table\n"), "sin_ruta"),
            (lectura("", 1, "route: socket: Operation not permitted"), "error_recoleccion"),
            (lectura("", 1), "error_recoleccion"),
            (lectura(error="advertencia"), "error_recoleccion"),
            (lectura(""), "error_interpretacion"),
            (lectura(RUTA + "interface: en1\n"), "error_interpretacion"),
            (lectura(RUTA.replace("default", "192.0.2.0")), "error_interpretacion"),
            (lectura(RUTA.replace("192.0.2.1", "link#4")), "error_interpretacion"),
            (lectura(RUTA.replace("en0", "-a")), "error_interpretacion"),
        ]
        for dato, estado in casos:
            with self.subTest(dato=dato), self.assertRaises(ErrorContexto) as error:
                interpretar_ruta_ipv4(dato)
            self.assertEqual(error.exception.estado, estado)

    def test_interfaz_sin_ipv4_no_equivale_a_salida_invalida(self):
        casos = [
            ("en0: flags=1<UP>\n\tinet6 ::1 prefixlen 128\n", "sin_ipv4"),
            ("", "error_interpretacion"),
            (INTERFAZ.replace("en0:", "en1:"), "error_interpretacion"),
            (INTERFAZ + "en1: flags=1<UP>\n", "error_interpretacion"),
            (INTERFAZ.replace("0xffffff00", "0xff00ff00"), "error_interpretacion"),
            (INTERFAZ.replace("0xffffff00", "0x100000000"), "error_interpretacion"),
            (INTERFAZ.replace("0xffffff00", "0.0.0.255"), "error_interpretacion"),
            (INTERFAZ.replace("192.0.2.10", "999.0.2.1"), "error_interpretacion"),
            (INTERFAZ.replace("netmask", "mascara"), "error_interpretacion"),
            (INTERFAZ + "\tinet 192.0.2.11 netmask 0xffffff00\n", "error_interpretacion"),
        ]
        for texto, estado in casos:
            with self.subTest(texto=texto), self.assertRaises(ErrorContexto) as error:
                interpretar_ipv4_interfaz(texto, "en0")
            self.assertEqual(error.exception.estado, estado)

    @patch("backend.contexto_red.platform.system", return_value="Darwin")
    def test_coordinacion_y_comandos_solo_lectura(self, sistema):
        with patch("backend.contexto_red.subprocess.run", side_effect=[proceso(RUTA), proceso(INTERFAZ)]) as ejecutar:
            resultado = consultar_contexto_ipv4()
        self.assertEqual(resultado["estado"], "contexto_correcto")
        self.assertEqual(resultado["contexto"], dict(interfaz="en0", ipv4_local="192.0.2.10/24", subred="192.0.2.0/24", gateway="192.0.2.1", mascara="255.255.255.0"))
        self.assertLessEqual(resultado["inicio"], resultado["fin"])
        self.assertEqual([c.args[0] for c in ejecutar.call_args_list], [["/sbin/route", "-n", "get", "-inet", "default"], ["/sbin/ifconfig", "en0"]])
        for llamada in ejecutar.call_args_list:
            self.assertEqual(llamada.kwargs["timeout"], 5)
            self.assertEqual(llamada.kwargs["env"]["LC_ALL"], "C")
            self.assertNotIn("shell", llamada.kwargs)

    @patch("backend.contexto_red.platform.system", return_value="Darwin")
    def test_fallos_recoleccion_y_contexto_incompatible(self, sistema):
        casos = [
            ([subprocess.TimeoutExpired("route", 5)], "error_recoleccion"),
            ([OSError("bloqueado")], "error_recoleccion"),
            ([UnicodeError("texto")], "error_recoleccion"),
            ([proceso("", 1, "route: writing to routing socket: not in table")], "sin_ruta"),
            ([proceso("")], "error_interpretacion"),
            ([proceso(RUTA), proceso("", 1)], "error_recoleccion"),
            ([proceso(RUTA), proceso(INTERFAZ, error="error")], "error_recoleccion"),
            ([proceso(RUTA), proceso("en0: flags=1<UP>\n")], "sin_ipv4"),
            ([proceso(RUTA.replace("192.0.2.1", "198.51.100.1")), proceso(INTERFAZ)], "error_interpretacion"),
        ]
        for respuestas, estado in casos:
            with self.subTest(estado=estado), patch("backend.contexto_red.subprocess.run", side_effect=respuestas) as ejecutar:
                resultado = consultar_contexto_ipv4()
            self.assertEqual(resultado["estado"], estado)
            self.assertIsNone(resultado["contexto"])
            self.assertTrue(resultado["detalle"])
            self.assertIsNotNone(resultado["fin"])
            self.assertEqual(ejecutar.call_count, len(respuestas))

    def test_plataforma_y_limite(self):
        with patch("backend.contexto_red.platform.system", return_value="Linux"), patch("backend.contexto_red.subprocess.run") as ejecutar:
            self.assertEqual(consultar_contexto_ipv4()["estado"], "error_recoleccion")
            ejecutar.assert_not_called()
        for valor, error in ((True, TypeError), (1.5, TypeError), (0, ValueError), (-1, ValueError)):
            with self.subTest(valor=valor), self.assertRaises(error):
                consultar_contexto_ipv4(valor)


class PruebasCliContexto(unittest.TestCase):
    def test_cli_real_coordinacion_simulada_y_arp_stdin(self):
        salida = io.StringIO()
        with (patch("sys.argv", ["backend", "arp", "--desde-stdin", "--contexto-auto"]),
              patch("sys.stdin", io.StringIO("? (192.0.2.1) at (incomplete) on en0 [ethernet]\nincorrecta")),
              patch("backend.contexto_red.platform.system", return_value="Darwin"),
              patch("backend.contexto_red.subprocess.run", side_effect=[proceso(RUTA), proceso(INTERFAZ)]) as ejecutar,
              redirect_stdout(salida)):
            main()
        resultado = json.loads(salida.getvalue())
        self.assertEqual(resultado["fuente"], "texto_arp_stdin")
        self.assertEqual(resultado["consulta_contexto"]["estado"], "contexto_correcto")
        self.assertEqual(resultado["entradas"][0]["categoria"], "gateway")
        self.assertEqual(resultado["entradas"][0]["resolucion_mac"], "incompleta")
        self.assertEqual(resultado["errores"][0]["numero_linea"], 2)
        self.assertEqual(ejecutar.call_count, 2)

    def test_fallo_contexto_conserva_arp_sin_clasificar_y_sale_uno(self):
        for estado in ("sin_ruta", "sin_ipv4", "error_recoleccion", "error_interpretacion"):
            salida = io.StringIO()
            with (self.subTest(estado=estado),
                  patch("sys.argv", ["backend", "arp", "--desde-stdin", "--contexto-auto"]),
                  patch("sys.stdin", io.StringIO("? (192.0.2.1) at (incomplete) on en0 [ethernet]")),
                  patch("backend.__main__.consultar_contexto_ipv4", return_value=dict(estado=estado, contexto=None)),
                  redirect_stdout(salida), self.assertRaises(SystemExit) as error):
                main()
            self.assertEqual(error.exception.code, 1)
            resultado = json.loads(salida.getvalue())
            self.assertNotIn("categoria", resultado["entradas"][0])
            self.assertNotIn("contexto", resultado)
            self.assertEqual(resultado["consulta_contexto"]["estado"], estado)

    def test_rechaza_mezcla_antes_de_consultar_o_leer(self):
        for opcion in (["--interfaz", "en0"], ["--ipv4-local", "192.0.2.10/24"], ["--gateway", "192.0.2.1"]):
            with (self.subTest(opcion=opcion),
                  patch("sys.argv", ["backend", "arp", "--desde-stdin", "--contexto-auto", *opcion]),
                  patch("sys.stdin") as entrada,
                  patch("backend.__main__.consultar_contexto_ipv4") as consulta,
                  redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error):
                main()
            self.assertEqual(error.exception.code, 2)
            consulta.assert_not_called()
            entrada.read.assert_not_called()

    def test_contexto_independiente_no_lee_stdin(self):
        for estado in ("contexto_correcto", "sin_ruta"):
            salida = io.StringIO()
            with (patch("sys.argv", ["backend", "contexto-red"]), patch("sys.stdin") as entrada,
                  patch("backend.__main__.consultar_contexto_ipv4", return_value={"estado": estado}),
                  redirect_stdout(salida)):
                if estado == "contexto_correcto":
                    main()
                else:
                    with self.assertRaises(SystemExit) as error:
                        main()
                    self.assertEqual(error.exception.code, 1)
            entrada.read.assert_not_called()
            self.assertEqual(json.loads(salida.getvalue())["estado"], estado)
