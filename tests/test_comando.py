import io
import unittest
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from backend.__main__ import main
from backend.configuracion import ConfiguracionSonda

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

                sonda.assert_called_once_with("192.0.2.1", ConfiguracionSonda())

        resultado_mostrado = json.loads(salida.getvalue())
        self.assertEqual(resultado_mostrado, resultado_simulado)    

    def test_arp_interpreta_stdin_y_muestra_json(self):
        linea = (
            "? (192.0.2.25) at 2:0:0:0:0:25 "
            "on en0 [ethernet]\n"
        )
        casos = (
            (linea, 1, 0),
            (linea + "texto inválido\n", 1, 1),
            ("texto inválido\n", 0, 1),
            ("", 0, 0),
        )

        for texto, cantidad_entradas, cantidad_errores in casos:
            with self.subTest(texto=texto):
                salida = io.StringIO()

                with (
                    patch("sys.argv", ["backend", "arp", "--desde-stdin"]),
                    patch("sys.stdin", io.StringIO(texto)),
                    patch("backend.arp.subprocess.run") as proceso,
                    redirect_stdout(salida),
                ):
                    main()

                proceso.assert_not_called()
                resultado = json.loads(salida.getvalue())

                self.assertEqual(resultado["fuente"], "texto_arp_stdin")
                self.assertEqual(
                    len(resultado["entradas"]), cantidad_entradas
                )
                self.assertEqual(
                    len(resultado["errores"]), cantidad_errores
                )

                if cantidad_entradas:
                    self.assertEqual(
                        resultado["entradas"][0]["mac"],
                        "02:00:00:00:00:25",
                    )

    def test_arp_clasifica_y_conserva_errores(self):
        salida = io.StringIO()
        texto = "? (192.0.2.1) at (incomplete) on en0 [ethernet]\ninválido"
        with (
            patch("sys.argv", ["backend", "arp", "--desde-stdin", "--interfaz", "en0",
                               "--ipv4-local", "192.0.2.10/24", "--gateway", "192.0.2.1"]),
            patch("sys.stdin", io.StringIO(texto)),
            patch("backend.arp.subprocess.run") as proceso,
            redirect_stdout(salida),
        ):
            main()
        proceso.assert_not_called()
        resultado = json.loads(salida.getvalue())
        self.assertEqual(resultado["contexto"]["subred"], "192.0.2.0/24")
        self.assertEqual(resultado["entradas"][0]["categoria"], "gateway")
        self.assertEqual(resultado["entradas"][0]["resolucion_mac"], "incompleta")
        self.assertEqual(resultado["errores"][0]["numero_linea"], 2)

    def test_arp_rechaza_contexto_incompleto_o_invalido_antes_de_leer(self):
        for opciones in (["--interfaz", "en0"], ["--gateway", "192.0.2.1"],
                         ["--ipv4-local", "192.0.2.10/24"],
                         ["--interfaz", "en0", "--ipv4-local", "inválida"]):
            with (
                self.subTest(opciones=opciones),
                patch("sys.argv", ["backend", "arp", "--desde-stdin", *opciones]),
                patch("sys.stdin") as entrada,
                redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as salida:
                    main()
                self.assertEqual(salida.exception.code, 2)
                entrada.read.assert_not_called()

    def test_arp_exige_opcion_desde_stdin(self):
        errores = io.StringIO()

        with (
            patch("sys.argv", ["backend", "arp"]),
            patch("sys.stdin") as entrada,
            redirect_stderr(errores),
        ):
            with self.assertRaises(SystemExit) as salida:
                main()

        self.assertEqual(salida.exception.code, 2)
        self.assertIn("--desde-stdin", errores.getvalue())
        entrada.read.assert_not_called()

    def test_arp_rechaza_entrada_interactiva(self):
        errores = io.StringIO()

        with (
            patch("sys.argv", ["backend", "arp", "--desde-stdin"]),
            patch("sys.stdin") as entrada,
            redirect_stderr(errores),
        ):
            entrada.isatty.return_value = True

            with self.assertRaises(SystemExit) as salida:
                main()

        self.assertEqual(salida.exception.code, 2)
        self.assertIn("tubería", errores.getvalue())
        entrada.read.assert_not_called()


class PruebasCliDiagnosticoArp(unittest.TestCase):
    def test_sin_referencia_no_lee_stdin_y_separa_json_de_eventos(self):
        r = {'estado':'diagnostico_con_datos', 'diagnostico':{'stdout_caracteres':20}}
        salida = io.StringIO()
        with (patch('sys.argv', ['backend', 'diagnostico-arp']), patch('sys.stdin') as entrada,
              patch('backend.__main__.diagnosticar_arp', return_value=r) as diagnostico,
              redirect_stdout(salida), redirect_stderr(io.StringIO())):
            main()
        diagnostico.assert_called_once_with(texto_referencia=None)
        entrada.read.assert_not_called()
        self.assertEqual(json.loads(salida.getvalue()), r)

    def test_comparacion_preserva_referencia_y_salida_vacia_sale_uno(self):
        salida, errores = io.StringIO(), io.StringIO()
        r = {'estado':'diagnostico_sin_datos', 'diagnostico':{'stdout_caracteres':0}}
        with (patch('sys.argv', ['backend', 'diagnostico-arp', '--comparar-stdin']),
              patch('sys.stdin', io.StringIO('texto de referencia')),
              patch('backend.__main__.diagnosticar_arp', return_value=r) as diagnostico,
              redirect_stdout(salida), redirect_stderr(errores), self.assertRaises(SystemExit) as error):
            main()
        self.assertEqual(error.exception.code, 1)
        diagnostico.assert_called_once_with(texto_referencia='texto de referencia')
        self.assertEqual(json.loads(salida.getvalue()), r)
        self.assertIn('operacion=diagnostico-arp', errores.getvalue())
        self.assertNotIn('texto de referencia', errores.getvalue())

    def test_comparacion_interactiva_no_inicia_proceso(self):
        with (patch('sys.argv', ['backend', 'diagnostico-arp', '--comparar-stdin']),
              patch('sys.stdin') as entrada, patch('backend.__main__.diagnosticar_arp') as diagnostico,
              redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error):
            entrada.isatty.return_value = True
            main()
        self.assertEqual(error.exception.code, 2)
        diagnostico.assert_not_called()
        entrada.read.assert_not_called()


class PruebasComandoSistema(unittest.TestCase):
    def lectura(self, estado='lectura_correcta'):
        return {'fuente': 'cache_arp_sysctl_macos', 'inicio_captura': '2026-10-09T19:00:00+00:00',
                'fin_captura': '2026-10-09T19:00:01+00:00', 'estado': estado, 'bytes_recibidos': 128,
                'entradas': [{'ipv4': '192.0.2.25', 'mac': None, 'interfaz': 'en0',
                              'marcas': [], 'tipo_enlace': 'ethernet'}], 'errores': [], 'detalle': None}

    def test_arp_sistema_no_lee_stdin_y_clasifica(self):
        salida = io.StringIO()
        with patch('sys.argv', ['backend', 'arp', '--desde-sistema', '--interfaz', 'en0', '--ipv4-local', '192.0.2.10/24']), patch('sys.stdin') as stdin, patch('backend.__main__.consultar_arp_sistema', return_value=self.lectura()), redirect_stdout(salida):
            main()
            stdin.read.assert_not_called()
        resultado = json.loads(salida.getvalue())
        self.assertEqual(resultado['fuente'], 'cache_arp_sysctl_macos')
        self.assertEqual(resultado['entradas'][0]['categoria'], 'vecino')

    def test_descubrir_sistema_conserva_fuente_intervalo_y_memoria(self):
        from backend.memoria import MemoriaObservaciones
        salida = io.StringIO()
        with patch('sys.argv', ['backend', 'descubrir', '--desde-sistema', '--interfaz', 'en0', '--ipv4-local', '192.0.2.10/24']), patch('backend.__main__.consultar_arp_sistema', return_value=self.lectura()), redirect_stdout(salida):
            main()
        resultado = json.loads(salida.getvalue())
        self.assertEqual(resultado['estado'], 'observacion_correcta')
        self.assertEqual(resultado['fuente'], 'cache_arp_sysctl_macos')
        self.assertEqual(resultado['fin_captura'], self.lectura()['fin_captura'])
        self.assertIsNone(resultado['momento_captura_origen'])
        memoria = MemoriaObservaciones()
        memoria.guardar(resultado)
        self.assertEqual(memoria.ultima()['id_observacion'], resultado['id_observacion'])

    def test_sistema_sin_visibilidad_y_fallo_no_son_red_vacia(self):
        for estado in ('sin_datos_visibles', 'error_recoleccion'):
            with self.subTest(estado=estado), patch('sys.argv', ['backend', 'arp', '--desde-sistema']), patch('backend.__main__.consultar_arp_sistema', return_value=self.lectura(estado)), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 1)

    def test_fuentes_son_exclusivas(self):
        with patch('sys.argv', ['backend', 'arp', '--desde-sistema', '--desde-stdin']), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
