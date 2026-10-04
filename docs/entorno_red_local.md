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