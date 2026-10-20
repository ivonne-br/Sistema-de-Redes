"""Convierte la imagen elegida en un icono macOS sin modificar su diseño.

Entrada: distribucion/recursos/icono-app.png. Salida: recursos/icono-app.icns,
utilizado por construir.py; requiere sips e iconutil del equipo constructor Mac.
"""

from pathlib import Path
import subprocess
import tempfile

RAIZ = Path(__file__).resolve().parents[1]


def main():
    origen = RAIZ / 'distribucion/recursos/icono-app.png'
    destino = RAIZ / 'distribucion/recursos/icono-app.icns'
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='redes-icono-') as temporal:
        conjunto = Path(temporal) / 'app.iconset'
        conjunto.mkdir()
        for tamano in (16, 32, 128, 256, 512):
            for escala, sufijo in ((1, ''), (2, '@2x')):
                medida = str(tamano * escala)
                archivo = conjunto / f'icon_{tamano}x{tamano}{sufijo}.png'
                subprocess.run(['sips', '-z', medida, medida, str(origen), '--out', str(archivo)],
                               check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['iconutil', '-c', 'icns', str(conjunto), '-o', str(destino)], check=True)


if __name__ == '__main__':
    main()
