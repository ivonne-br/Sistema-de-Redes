import argparse # módulo para analizar argumentos de línea de comandos
import ipaddress
import json
import sys
import signal
from dataclasses import replace

from backend.arp import (
    interpretar_tabla_arp, crear_contexto_arp, clasificar_entradas_arp, diagnosticar_arp,
)
from backend.sonda import ejecutar_sonda
from backend.contexto_red import consultar_contexto_ipv4
from backend.configuracion import cargar_configuracion
from backend.eventos import configurar_logging, registrar_resultado
from backend.descubrimiento import observar_arp, observar_tabla_arp
from backend.arp_macos import consultar_arp_sistema
from backend.coordinador import CoordinadorARP
from backend.api import APILocal


def ejecutar_api(configuracion, logger):
    """Conecta señales del CLI al cierre de la API y su único monitoreo."""
    api = APILocal(configuracion, logger=logger)
    anteriores = {}
    try:
        for senal in (signal.SIGINT, signal.SIGTERM):
            anteriores[senal] = signal.signal(senal, lambda signum, frame: api.detener())
        api.servir(al_iniciar=lambda app: print(json.dumps({
            "version_esquema": 1, "tipo": "api_iniciada",
            "url": f"http://127.0.0.1:{app.puerto}",
            "id_ejecucion": app.estado()["id_ejecucion"],
        }), flush=True))
    except (OSError, RuntimeError):
        logger.error("No se pudo iniciar o mantener la API local; revisa que el puerto esté libre.")
        raise SystemExit(1) from None
    finally:
        for senal, anterior in anteriores.items():
            signal.signal(senal, anterior)
    if api.estado()["error"] is not None:
        raise SystemExit(1)


def ejecutar_monitoreo(configuracion, ciclos, logger):
    """Adapta señales y JSON Lines al coordinador, restaurando los manejadores."""
    coordinador = CoordinadorARP(configuracion)
    consulta = coordinador.consulta

    def emitir(observacion):
        registrar_resultado(logger, "descubrir", observacion)
        print(json.dumps({"version_esquema": 1, "tipo": "observacion_arp",
                          **consulta.resumen(),
                          "observacion": observacion}, ensure_ascii=False, allow_nan=False), flush=True)

    def detener(signum, frame):
        coordinador.detener()

    anteriores = {}
    try:
        for senal in (signal.SIGINT, signal.SIGTERM):
            anteriores[senal] = signal.signal(senal, detener)
        resultado = coordinador.ejecutar(ciclos=ciclos, emitir=emitir)
        resultado.update(consulta.resumen())
        print(json.dumps(resultado, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        for senal, anterior in anteriores.items():
            signal.signal(senal, anterior)
    if resultado["motivo"] == "detenido":
        raise SystemExit(130)
    if resultado["ciclos_con_incidencias"]:
        raise SystemExit(1)

def validar_ipv4(texto):
    try:
        return str(ipaddress.IPv4Address(texto))
    except ipaddress.AddressValueError:
        raise argparse.ArgumentTypeError(
            "Introduce una dirección IPv4 válida, por ejemplo 192.0.1.2."
        ) from None

def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Análisis de Redes."
    )

    parser.add_argument(
        "--config", metavar="ARCHIVO",
        help="Archivo JSON de configuración; colocar antes del subcomando.",
    )
    subcomandos = parser.add_subparsers(dest="comando")
    api = subcomandos.add_parser("servir-api", help="Iniciar API de lectura en 127.0.0.1 y un único monitoreo ARP; Ctrl+C para cerrar.")
    api.add_argument("--puerto", type=int, help="Puerto local (8000 por defecto; 0 elige uno libre).")
    monitoreo = subcomandos.add_parser("monitorear-arp", help="Consultar contexto y ARP periódicamente; emitir JSON Lines.")
    monitoreo.add_argument("--intervalo", type=float, help="Segundos de espera entre ciclos (predeterminado: configuración o 5).")
    monitoreo.add_argument("--ciclos", type=int, help="Número positivo de ciclos; omitir para continuar hasta Ctrl+C.")

    comando_sonda = subcomandos.add_parser(
        "sonda",
        help="Ejecutar una sonda ICMP hacia una dirección IPv4.",
    )

    comando_sonda.add_argument(
        "destino", # argumento posicional para la dirección IPv4
        type=validar_ipv4, # función de validación para asegurar que es una dirección IPv4 válida
        help="Dirección IPv4 que se desea consultar.",
    )

    for nombre, descripcion in (
        ("arp", "Leer ARP del sistema o interpretar texto recibido."),
        ("descubrir", "Construir una observación de descubrimiento ARP."),
    ):
        comando_arp = subcomandos.add_parser(
            nombre,
            help=descripcion,
        )

        origen = comando_arp.add_mutually_exclusive_group(required=True)
        origen.add_argument(
            "--desde-stdin", action="store_true",
            help="Leer texto ARP desde una tubería o archivo redirigido.",
        )
        origen.add_argument(
            "--desde-sistema", action="store_true",
            help="Leer la caché ARP actual con sysctl en macOS, sin ejecutar arp.",
        )

        comando_arp.add_argument("--interfaz", help="Interfaz del contexto, por ejemplo en0.")
        comando_arp.add_argument("--ipv4-local", help="IPv4 local con prefijo, por ejemplo 192.0.2.10/24.")
        comando_arp.add_argument("--gateway", help="Puerta de enlace IPv4, si se conoce.")

        comando_arp.add_argument(
            "--contexto-auto", action="store_true",
            help="Consultar el contexto IPv4 actual de macOS para clasificar.",
        )
    subcomandos.add_parser("contexto-red", help="Consultar el contexto IPv4 actual de macOS.")

    comando_diagnostico = subcomandos.add_parser(
        "diagnostico-arp", help="Localizar el resultado de la lectura ARP desde Python.",
    )
    comando_diagnostico.add_argument(
        "--comparar-stdin", action="store_true",
        help="Comparar con texto de referencia suministrado por tubería o archivo.",
    )
    argumentos = parser.parse_args()
    try:
        configuracion = cargar_configuracion(argumentos.config)
        if argumentos.comando == "servir-api" and argumentos.puerto is not None:
            configuracion = replace(configuracion, puerto_api=argumentos.puerto)
        if argumentos.comando == "monitorear-arp":
            if argumentos.intervalo is not None:
                configuracion = replace(configuracion, intervalo_arp_s=argumentos.intervalo)
            if argumentos.ciclos is not None and argumentos.ciclos <= 0:
                raise ValueError("--ciclos debe ser mayor que cero.")
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    logger = configurar_logging(configuracion.nivel_log)

    if argumentos.comando == "servir-api":
        ejecutar_api(configuracion, logger)
    elif argumentos.comando == "monitorear-arp":
        ejecutar_monitoreo(configuracion, argumentos.ciclos, logger)
    elif argumentos.comando == "sonda":
        resultado = ejecutar_sonda(argumentos.destino, configuracion.sonda) # Ejecuta la función de sonda con la dirección IPv4 proporcionada en un diccionario
        registrar_resultado(logger, argumentos.comando, resultado)
        print(json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False))
    elif argumentos.comando == "diagnostico-arp":
        referencia = None
        if argumentos.comparar_stdin:
            if sys.stdin.isatty():
                parser.error("--comparar-stdin requiere una tubería o un archivo redirigido.")
            referencia = sys.stdin.read()
        resultado = diagnosticar_arp(texto_referencia=referencia)
        registrar_resultado(logger, argumentos.comando, resultado)
        print(json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False))
        if resultado["estado"] != "diagnostico_con_datos":
            raise SystemExit(1)
    elif argumentos.comando == "contexto-red":
        resultado = consultar_contexto_ipv4(configuracion.limite_contexto_s)
        registrar_resultado(logger, argumentos.comando, resultado)
        print(json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False))
        if resultado["estado"] != "contexto_correcto":
            raise SystemExit(1)
    elif argumentos.comando in ("arp", "descubrir"):
        contexto = None
        consulta_contexto = None
        manual = any(valor is not None for valor in (
            argumentos.interfaz, argumentos.ipv4_local, argumentos.gateway
        ))
        if argumentos.contexto_auto and manual:
            parser.error("--contexto-auto no se puede combinar con contexto manual.")
        if argumentos.comando == "descubrir" and not manual and not argumentos.contexto_auto:
            parser.error("descubrir requiere --contexto-auto o un contexto manual.")
        if manual:
            if argumentos.interfaz is None or argumentos.ipv4_local is None:
                parser.error("Para clasificar se requieren --interfaz y --ipv4-local juntos.")
            try:
                contexto = crear_contexto_arp(
                    argumentos.interfaz, argumentos.ipv4_local, argumentos.gateway
                )
            except ValueError as error:
                parser.error(str(error))
        if argumentos.desde_stdin and sys.stdin.isatty():
            parser.error(
                f"El comando {argumentos.comando} --desde-stdin necesita texto "
                "desde una tubería o archivo redirigido."
            )

        if argumentos.contexto_auto:
            consulta_contexto = consultar_contexto_ipv4(configuracion.limite_contexto_s)
            contexto = consulta_contexto["contexto"]

        lectura = None
        texto = None
        if argumentos.desde_sistema:
            lectura = consultar_arp_sistema()
            if lectura["estado"] in ("error_recoleccion", "sin_datos_visibles"):
                registrar_resultado(logger, "recoleccion_arp", lectura)
                print(json.dumps(lectura, indent=2, ensure_ascii=False, allow_nan=False))
                raise SystemExit(1)
            tabla = {"entradas": lectura["entradas"], "errores": lectura["errores"]}
        else:
            texto = sys.stdin.read()
            tabla = interpretar_tabla_arp(texto)
        if argumentos.comando == "descubrir":
            opciones = {
                "contexto": contexto if consulta_contexto is None else None,
                "consulta_contexto": consulta_contexto,
            }
            if lectura is None:
                resultado = observar_arp(texto, **opciones)
            else:
                resultado = observar_tabla_arp(
                    tabla, **opciones, fuente=lectura["fuente"],
                    inicio_captura=lectura["inicio_captura"], fin_captura=lectura["fin_captura"],
                )
            registrar_resultado(logger, argumentos.comando, resultado)
            print(json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False))
            if resultado["estado"] not in ("observacion_correcta", "sin_entradas"):
                raise SystemExit(1)
            return

        resultado = {
            **(lectura if lectura is not None else {}),
            "fuente": lectura["fuente"] if lectura is not None else "texto_arp_stdin",
            "entradas": tabla["entradas"],
            "errores": tabla["errores"],
        }

        if consulta_contexto is not None:
            resultado["consulta_contexto"] = consulta_contexto
        if contexto is not None:
            resultado["contexto"] = contexto
            resultado["entradas"] = clasificar_entradas_arp(
                tabla["entradas"], contexto["interfaz"],
                contexto["ipv4_local"], contexto["gateway"],
            )
        registrar_resultado(logger, argumentos.comando, resultado)
        print(json.dumps(resultado, indent=2, ensure_ascii=False, allow_nan=False))
        if (consulta_contexto is not None and consulta_contexto["estado"] != "contexto_correcto") or (
            lectura is not None and lectura["errores"]
        ):
            raise SystemExit(1)
    else:
        print("Backend del Sistema de Análisis de Redes iniciado.")


if __name__ == "__main__":
    main()
