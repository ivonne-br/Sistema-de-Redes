#!/bin/zsh
# Abre desde Finder el iniciador Python del repositorio; recibe su ubicación
# y entrega mensajes de inicio/cierre. No instala herramientas ni cambia la red.
cd -- "${0:A:h}" || exit 1
resultado_inicio=1
if [[ ! -x .venv/bin/python || ! -f backend/inicio.py ]]; then
  print 'Falta el entorno Python o parte de la aplicación.'
  print 'Pide restaurar el proyecto completo y preparar .venv con Python 3.14.'
else
  .venv/bin/python -B -m backend.inicio
  resultado_inicio=$?
fi
if (( resultado_inicio != 0 )); then
  print 'Puedes cerrar esta ventana. Pulsa Enter para terminar.'
  read -r
fi
exit "$resultado_inicio"
