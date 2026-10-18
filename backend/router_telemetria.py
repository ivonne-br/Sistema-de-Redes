"""Traduce la lectura de un modelo al formato común del recolector.

Entradas: transporte acotado, credenciales efímeras y gateway verificado.
Salidas: sesión privada, inventario y contadores normalizados para router.py.
Cada integración define su acceso y fuentes; no concede escritura.
"""
import json

from backend.router_json import FUENTES, interpretar_json_router


class LecturaSercomm:
    """Contrato observado de Sercomm; no se reutiliza para otras marcas."""

    fuentes = tuple(FUENTES)
    fuente_inventario = 'dhcp-json'

    def __init__(self, transporte, login, error):
        self.transporte, self.login, self.error = transporte, login, error

    def autenticar(self, gateway, usuario, password, vigente):
        cookie, csrf = self.login(gateway, usuario, password, vigente)
        return {'cookie': cookie, 'csrf': csrf}

    def _pedir(self, gateway, ruta, acceso):
        return self.transporte(gateway, ruta, acceso['cookie'], acceso['csrf'])

    def verificar(self, gateway, acceso):
        script = self._pedir(gateway, '/js/status-and-support_wan.js', acceso)
        if not all(n in script for n in (FUENTES['wan-ipv4-json'],
                                        FUENTES['wan-ipv6-json'], '$.getJSON', 'csrf_token')):
            raise self.error('sesion_o_router_no_compatible')

    def validar_sesion(self, gateway, acceso):
        try:
            filas = json.loads(self._pedir(gateway, '/data/user_data.json', acceso))
            if not isinstance(filas, list) or not any(
                    isinstance(f, dict) and isinstance(f.get('username'), str)
                    and f['username'].strip() for f in filas):
                raise ValueError()
        except (ValueError, RecursionError):
            raise self.error('autorizacion_rechazada') from None

    def leer(self, gateway, fuente, acceso):
        texto = self._pedir(gateway, '/data/' + FUENTES[fuente], acceso)
        return interpretar_json_router(texto, fuente)
