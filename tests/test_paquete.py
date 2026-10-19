"""Comprueba recursos instalados, auxiliar y selección de fuentes sin red ni GUI.

Entradas: carpetas temporales; salidas: errores claros y ausencia de compilación,
lecturas privadas o dependencia de la ubicación original del repositorio.
"""

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.entorno_aplicacion import comando_web, raiz_recursos
from backend.inicio import ErrorInicio, preparar_dashboard, identidad
from backend.paquete import main
from distribucion.construir import copiar_fuentes


class PruebasPaquete(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.dist = self.raiz / 'frontend/dist'
        (self.dist / 'assets').mkdir(parents=True)
        (self.dist / 'index.html').write_text('<script src="/assets/app.js"></script>')
        (self.dist / 'assets/app.js').write_text('/* público */')

    def test_paquete_no_compila_ni_escribe_en_su_carpeta(self):
        with patch('sys.frozen', True, create=True), patch('backend.inicio.subprocess.run') as ejecutar:
            self.assertEqual(preparar_dashboard(self.raiz), self.dist)
            ejecutar.assert_not_called()
            self.assertFalse((self.dist / '.inicio-huella').exists())

    def test_recurso_ausente_rechaza_inicio_sin_intentar_instalar(self):
        (self.dist / 'assets/app.js').unlink()
        with patch('sys.frozen', True, create=True), patch('backend.inicio.subprocess.run') as ejecutar:
            with self.assertRaisesRegex(ErrorInicio, 'incompleta'):
                preparar_dashboard(self.raiz)
            ejecutar.assert_not_called()

    def test_recursos_y_auxiliar_se_resuelven_desde_paquete_movido(self):
        with patch('sys.frozen', True, create=True), patch('sys._MEIPASS', str(self.raiz), create=True):
            self.assertEqual(raiz_recursos(), self.raiz)
            self.assertEqual(comando_web('dns', '127.0.0.1', 2, 204),
                             [sys.executable, '--trabajador-web', 'dns', '127.0.0.1', '2', '204'])
            self.assertEqual(identidad(self.raiz), identidad(self.raiz / 'otra ubicacion'))
        self.assertIn('backend.web', comando_web('dns', '127.0.0.1', 2, 204))

    def test_fuentes_no_copian_secretos_capturas_o_mapas_y_rechazan_enlaces(self):
        (self.raiz / 'backend').mkdir()
        (self.raiz / 'backend/__init__.py').write_text('')
        (self.raiz / 'backend/sesion.json').write_text('privado')
        (self.raiz / 'frontend/dist/assets/app.js.map').write_text('fuentes')
        (self.raiz / 'frontend/dist/captura.png').write_text('privado')
        (self.raiz / '.env').write_text('privado')
        (self.raiz / 'distribucion').mkdir()
        (self.raiz / 'distribucion/entrada.py').write_text('')
        destino = self.raiz / 'salida'
        with patch('distribucion.construir.RAIZ', self.raiz):
            copiar_fuentes(destino)
            self.assertEqual({str(p.relative_to(destino)) for p in destino.rglob('*') if p.is_file()},
                             {'backend/__init__.py', 'frontend/dist/index.html', 'frontend/dist/assets/app.js', 'entrada.py'})
            (self.dist / 'assets/enlace.js').symlink_to(self.raiz / '.env')
            with self.assertRaisesRegex(ValueError, 'enlaces'):
                copiar_fuentes(self.raiz / 'otra')

    def test_windows_linux_no_se_presentan_como_recolectores_compatibles(self):
        for sistema in ('win32', 'linux'):
            with patch('sys.argv', ['app']), patch('sys.platform', sistema), \
                    patch('backend.paquete.preparar_tls'), patch('backend.inicio.preparar_dashboard'), \
                    patch('backend.inicio.ejecutar') as ejecutar, patch('backend.paquete.mostrar_error') as aviso:
                self.assertEqual(main(), 1)
                ejecutar.assert_not_called()
                self.assertIn('experimental', aviso.call_args.args[0])

    def test_icono_lanza_servicio_separado_para_permitir_reapertura(self):
        with patch('sys.argv', ['app']), patch('sys.platform', 'darwin'), \
                patch('sys.frozen', True, create=True), patch('backend.paquete.preparar_tls'), \
                patch('backend.inicio.preparar_dashboard'), patch('backend.paquete.subprocess.Popen') as lanzar:
            self.assertEqual(main(), 0)
            self.assertEqual(lanzar.call_args.args[0], [sys.executable, '--servicio'])
            self.assertTrue(lanzar.call_args.kwargs['start_new_session'])

    def test_runtime_incompleto_no_inicia_api(self):
        with patch('sys.argv', ['app', '--autoprueba']), \
                patch('backend.paquete.preparar_tls', side_effect=OSError()), \
                patch('backend.inicio.ejecutar') as ejecutar, redirect_stdout(io.StringIO()) as salida:
            self.assertEqual(main(), 1)
            ejecutar.assert_not_called()
            self.assertIn('false', salida.getvalue())
