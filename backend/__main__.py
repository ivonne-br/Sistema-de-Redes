import argparse # módulo para analizar argumentos de línea de comandos
import ipaddress
import json

from backend.sonda import ejecutar_sonda

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

    subcomandos = parser.add_subparsers(dest="comando")

    comando_sonda = subcomandos.add_parser(
        "sonda",
        help="Ejecutar una sonda ICMP hacia una dirección IPv4.",
    )

    comando_sonda.add_argument(
        "destino", # argumento posicional para la dirección IPv4
        type=validar_ipv4, # función de validación para asegurar que es una dirección IPv4 válida
        help="Dirección IPv4 que se desea consultar.",
    )

    argumentos = parser.parse_args()

    if argumentos.comando == "sonda":
        resultado = ejecutar_sonda(argumentos.destino) # Ejecuta la función de sonda con la dirección IPv4 proporcionada en un diccionario
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        print("Backend del Sistema de Análisis de Redes iniciado.")


if __name__ == "__main__":
    main()