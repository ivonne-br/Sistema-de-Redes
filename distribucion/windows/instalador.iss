; Instalación de usuario: recibe Origen/Salida desde construir.py y crea acceso directo.
; No modifica red, firewall ni inicia un servicio; paquete experimental sin firma.
#ifndef Origen
  #error Definir Origen con la carpeta construida por PyInstaller.
#endif
#ifndef Salida
  #error Definir Salida con la carpeta de entrega.
#endif
[Setup]
AppId=SistemaDeRedesLocal
AppName=Sistema de Redes (experimental)
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\Sistema de Redes
DefaultGroupName=Sistema de Redes
PrivilegesRequired=lowest
OutputDir={#Salida}
OutputBaseFilename=Sistema-de-Redes-experimental-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Sistema de Redes.exe
[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Sistema de Redes"; Filename: "{app}\Sistema de Redes.exe"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"
