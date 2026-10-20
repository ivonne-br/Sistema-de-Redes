#!/bin/sh
# Instala el paquete extraído para el usuario y crea un acceso en Aplicaciones.
# Entrada: carpeta de este script; salida: ~/.local/opt y .desktop. Sin sudo ni red.
set -eu
origen=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
destino="$HOME/.local/opt/sistema-de-redes"
accesos="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
if [ -e "$destino" ]; then
  echo 'Ya existe una instalación. Ciérrala y conserva o retira esa carpeta antes de instalar otra copia.'
  exit 1
fi
mkdir -p "$(dirname -- "$destino")" "$accesos"
cp -R "$origen" "$destino"
chmod u+x "$destino/Sistema de Redes"
# El acceso usa una ruta fija relativa al HOME para evitar interpolar nombres en Exec.
cat > "$accesos/sistema-de-redes.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Sistema de Redes (experimental)
Exec=sh -c "exec \"\$HOME/.local/opt/sistema-de-redes/Sistema de Redes\""
Terminal=true
Categories=Network;
DESKTOP
echo 'Instalado para este usuario. Recolección Linux pendiente; no es una versión terminada.'
