# Identificación inicial del entorno de red local


1. Consultar la ruta predeterminada:

   ```bash
   route -n get default
   ```

   Registrar localmente gateway e interface.

2. Relacionar la interfaz con el puerto de hardware:

   ```bash
   networksetup -listallhardwareports
   ```

3. Consultar la dirección y máscara de la interfaz identificada:

   ```bash
   ifconfig en0
   ```

   Sustituir en0 si la interfaz identificada es otra.

## Resultado

Se identificaron interfaz, dirección IPv4, máscara y puerta de enlace.
La máscara observada corresponde a /24.
Se comprobó que la dirección local y la puerta de enlace pertenecen
a la misma subred.

Las direcciones reales y MAC se omiten de esta evidencia compartida.

## Limitaciones

- Las consultas muestran configuración, no prueban conectividad.
- No se descubrieron otros dispositivos.
- No se comprobó el fabricante, modelo ni capacidades del router.
- La selección debe revisarse si cambian la conexión, las rutas o una VPN.
- Esta prueba manual no implementa todavía la identificación automática.

## Observación adicional de la caché ARP

La consulta ARP descrita en esta sección se realizó en una red
escolar con máscara /19. La identificación inicial corresponde
a la red doméstica con máscara /24; son observaciones de
entornos diferentes.

### Procedimiento

Se consultó la tabla local mediante `arp -an`.

Para interpretar sus entradas se consultaron también la ruta
predeterminada mediante `route -n get default` y la configuración
de la interfaz mediante `ifconfig en0`.

Estos comandos consultan información local; no realizan un
barrido de dispositivos ni prueban su conectividad.

### Hallazgos

- Las entradas mostraban direcciones IPv4, direcciones MAC,
  interfaz y marcas como `ifscope` y `permanent`.
- Se identificaron entradas correspondientes al propio recolector,
  a la puerta de enlace, a difusión y a grupos multicast.
- Una misma MAC aparecía asociada a dos direcciones IPv4.
  La consulta no permitió determinar la causa.
- Algunas MAC omitían ceros iniciales en sus componentes.
  Esa diferencia de representación no implica direcciones distintas.
- No se observaron entradas marcadas como `incomplete`
  en la salida consultada.

Las direcciones IP y MAC reales se omiten de esta evidencia.

### Limitaciones y consecuencias para el diseño

Una entrada en la caché ARP no demuestra que el dispositivo siga
disponible. La tabla tampoco garantiza incluir todos los equipos
conectados.

No se contará cada fila como un dispositivo: deberán distinguirse
las entradas del recolector, difusión, multicast y las asociaciones
utilizables dentro del contexto seleccionado.

La marca `permanent` no demuestra conexión permanente.
La indicación `[ethernet]` tampoco permite determinar si el equipo
remoto utiliza cable o Wi-Fi.

La salida consultada no proporciona la fecha de última presencia
de cada equipo. El momento de lectura de la caché no se presentará
como momento de última respuesta del dispositivo.

El sistema deberá identificar la interfaz, dirección local,
máscara y puerta de enlace sin fijarlas en el código. Un cambio
de red deberá iniciar un contexto de observación distinto.

## Criterios propuestos para interpretar las entradas ARP

### Datos que se conservarán

Por consulta se registrarán la fuente, el momento de lectura
y el contexto seleccionado: interfaz, IPv4 local, subred
y puerta de enlace cuando esté disponible.

Por entrada se conservarán:

- Dirección IPv4.
- Dirección MAC, si está disponible.
- Interfaz.
- Marcas mostradas por la fuente.
- Clasificación y motivo del tratamiento aplicado.

Las MAC válidas se representarán con seis componentes
hexadecimales de dos caracteres, separados por dos puntos.
Esta normalización no permite identificar de forma universal
un dispositivo.

### Límites de identidad y tiempo

Varias IPv4 asociadas a una MAC no se fusionarán automáticamente
como un único dispositivo. Tampoco se afirmará que representan
equipos distintos únicamente por tener direcciones IPv4 diferentes.

El momento de lectura indica cuándo se consultó la caché.
No equivale a la última respuesta ni a una presencia recién
comprobada del dispositivo.

Una consulta fallida no se representará como una lista vacía
obtenida correctamente. Una consulta sin entradas tampoco
demuestra que no existan dispositivos en la red.
