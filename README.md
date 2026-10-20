# Sistema de Análisis de Redes para la Toma de Decisiones

Sistema de software orientado al monitoreo, análisis y visualización de redes domésticas. Su propósito es transformar datos técnicos sobre conectividad, dispositivos y uso de la red en información comprensible para usuarios no especializados, de modo que puedan reconocer situaciones relevantes y tomar decisiones informadas.

La propuesta parte de un problema cotidiano: el usuario percibe lentitud o interrupciones, pero cuenta con poca información para comprender qué sucede. El sistema buscará reunir las métricas disponibles, interpretarlas mediante reglas explícitas y presentar indicadores, alertas y recomendaciones en una interfaz web.
El protocolo contempla redes domésticas, escolares y de pequeña escala.

## Objetivo general

Desarrollar un sistema de soporte a la toma de decisiones que recopile, analice y visualice métricas de una red doméstica para facilitar la comprensión de su estado y apoyar la identificación de posibles problemas de conectividad y rendimiento.

### Objetivos específicos

1. Identificar las métricas y fuentes de datos para evaluar el desempeño de red.
2. Diseñar componentes separados para descubrimiento, monitoreo, análisis y visualización.
3. Obtener y normalizar información de dispositivos y mediciones de conectividad.
4. Transformar las mediciones en indicadores y explicaciones sustentadas en los datos observados.
5. Evaluar el funcionamiento del prototipo con pruebas reproducibles y datos de una red real.

## Alcance inicial

La propuesta inicial comprende:

- Investigar la comunicación con el router disponible e identificar las fuentes de información accesibles.
- Descubrir dispositivos y consultar sus datos básicos cuando la fuente los proporcione.
- Recopilar periódicamente métricas de conectividad y estado de la red.
- Validar y procesar las mediciones para identificar cambios y situaciones relevantes.
- Mostrar dispositivos, indicadores y resultados del análisis mediante un dashboard comprensible.
- Ejecutar y verificar al menos una operación administrativa compatible, con autorización temporal y confirmación del usuario.
- Validar el prototipo en la red doméstica seleccionada.

## Base tecnológica

| Componente | Tecnología o enfoque previsto | Estado de definición |
| --- | --- | --- |
| Backend y procesamiento | Python | Lenguaje definido; framework y versiones pendientes. |
| Interfaz web | Vue.js | Framework definido; diseño del dashboard pendiente. |
| Comunicación entre frontend y backend | API REST | Contratos y actualización de datos pendientes. |
| Recolección y diagnóstico | Scapy, PyShark, psutil e ICMP/ping | Su incorporación se validará según las métricas y el entorno. |
| Comunicación con el router | Adaptador específico del fabricante, modelo y firmware | Mecanismo por investigar; HTTP/HTTPS u otros protocolos dependerán del equipo. |
| Persistencia | MySQL | Propuesto en el protocolo; momento de incorporación por definir. |
| Control de versiones y seguimiento | Git y GitHub | Flujo de trabajo previsto con ramas e issues. |

## Organización conceptual del sistema

En la arquitectura inicial se propone separar las responsabilidades en componentes. Los agentes son módulos de software con tareas delimitadas.

| Componente | Responsabilidad prevista |
| --- | --- |
| Agente de descubrimiento | Identificar la red y los dispositivos observables, registrando la fuente de información. |
| Agente de monitoreo | Obtener mediciones periódicas y registrar su momento de captura y los errores de recolección. |
| Agente de análisis | Comparar datos normalizados y calcular indicadores y condiciones que sustenten recomendaciones básicas. |
| Adaptadores de router | Encapsular la comunicación y declarar las capacidades soportadas por cada equipo. |
| Backend y API | Coordinar los componentes y entregar resultados procesados a la interfaz. |
| Dashboard | Presentar el estado de la red, los dispositivos y las explicaciones para el usuario. |

La recolección deberá poder ejecutarse de forma independiente de las consultas de la interfaz.

## Métricas consideradas

Como punto de partida se consideran:

| Categoría | Datos o indicadores candidatos |
| --- | --- |
| Conectividad | Latencia, proporción de sondas sin respuesta y disponibilidad observada respecto de destinos definidos. |
| Dispositivos | Cantidad de equipos observados, identificación disponible, estado y tipo de conexión. |
| Tráfico y uso | Tasas de transferencia, volumen de datos y participación por dispositivo, condicionados a fuentes verificables. |
| Wi-Fi | Señal, canal y otros datos que puedan obtenerse del entorno y del equipo. |

## Guía de uso del sistema

El sistema se ejecuta en una computadora conectada a la red doméstica que se desea observar. Abre un dashboard en el navegador de esa misma computadora y realiza mediciones en segundo plano. No necesita una instalación en cada dispositivo de la vivienda.

Permite consultar:

- El contexto de la red y los dispositivos observables desde la computadora.
- Resultados de conectividad, tiempos de respuesta y comprobaciones de DNS y HTTPS, con sus errores y límites.
- Indicadores y explicaciones elaborados a partir de las mediciones disponibles.
- Información del router compatible, cuando la persona autoriza temporalmente su lectura.

Las mediciones recientes se conservan temporalmente en memoria. Al cerrar el sistema se pierden.

### Qué necesita la computadora

| Necesidad | Aplicación empaquetada para la persona usuaria |
| --- | --- |
| Sistema operativo | El paquete local se comprobó en macOS 27.0.1 con Apple Silicon (`arm64`). |
| Navegador | Un navegador para mostrar el dashboard en la misma computadora. |
| Conexión local | Wi-Fi o Ethernet de la red que se quiere observar. |
| Python y Node.js | Python y el frontend compilado vienen incluidos. |
| Acceso al router | Solo para consultar información que requiera autorización, en equipos compatibles. |

La computadora debe permanecer encendida y la aplicación abierta para seguir recolectando. El sistema no modifica automáticamente la configuración de red de la computadora.

Que la API responda o el dashboard se abra **no significa que Internet funcione**. La dirección `127.0.0.1` representa la propia computadora; no permite abrir esta instalación desde un teléfono.

### Cómo obtener el instalador

En la computadora donde se generó, el archivo se encuentra en:

```text
dist/entrega-local/macos-arm64/Sistema-de-Redes-prueba.dmg
```

Esa ruta es relativa a la carpeta del proyecto. El archivo generado no se guarda en Git.

### Cómo instalar en macOS

Estos pasos corresponden al paquete de prueba, cuando ya se dispone del archivo DMG:

1. Abre `Sistema-de-Redes-prueba.dmg` con doble clic.
2. Arrastra **Sistema de Redes** a **Aplicaciones**.
3. Espera a que termine la copia y abre la aplicación desde **Aplicaciones**.
4. La aplicación inicia su servicio local y abre el dashboard en el navegador.
5. Espera las primeras mediciones. Un panel que indique que está esperando datos todavía no permite concluir que la red funcione bien o mal.

No es necesario abrir una terminal ni instalar las herramientas de desarrollo.

- **Cerrar el sistema:** en el dashboard, pulsa **Cerrar aplicación** y después **Confirmar cierre**. Espera a que termine antes de volver a abrirlo.
- **Cerrar solo la pestaña:** no detiene las mediciones ni equivale a cerrar la aplicación.
- **Finalizar el acceso al router:** retira la autorización de lectura, pero permite continuar usando los demás paneles.

### Qué credenciales se necesitan

Para abrir el dashboard y consultar las mediciones generales **no se necesita crear una cuenta del sistema ni introducir credenciales del router**.

Para consultar las tablas protegidas de un router compatible se necesitan:

- Autorización de la persona responsable de esa red.
- El **usuario de administración del router**.
- La **contraseña de acceso al panel del router**.

1. Busca el panel **Dispositivos y tráfico del router**.
2. Revisa la **Puerta de enlace candidata** que muestra la aplicación.
3. Abre **Conectar router**.
4. Escribe el **Usuario del router** y la **Contraseña del router**, respetando sus mayúsculas y minúsculas.
5. Lee el aviso y marca la confirmación de que tienes autorización para acceder al equipo y permites su lectura temporal.
6. Pulsa **Iniciar lectura automática**. Se realiza un intento de acceso; espera el resultado antes de volver a intentarlo.
7. Si el acceso y el formato son compatibles, consulta los datos disponibles.
8. Al terminar, pulsa **Finalizar acceso de lectura**, o cierra toda la aplicación si ya no vas a utilizarla.

La autorización local dura como máximo **30 minutos desde su inicio** y no se renueva al recargar la página. Un cambio de red retira el permiso. La contraseña se descarta tras el intento de acceso; la sesión necesaria para las consultas permanece temporalmente en memoria.

### Si no se puede consultar el router

| Mensaje o situación | Qué revisar |
| --- | --- |
| No aparece una puerta de enlace o se indica falta de contexto | Comprueba que la computadora esté conectada a la red que quieres observar y espera una nueva lectura. |
| Usuario o contraseña rechazados | Revisa los datos de acceso al panel, no los de conexión Wi-Fi. No repitas intentos sin revisar el mensaje. |
| Router ocupado u otra sesión activa | Espera o finaliza tu sesión anterior desde la vista donde la abriste. No cierres sesiones de otras personas. |
| Autorización expirada | Inicia una nueva lectura únicamente si todavía necesitas consultar el router y tienes permiso. |
| Sesión o formato no compatible | El adaptador no pudo validar ese equipo o su respuesta. No apliques instrucciones de otro fabricante. Puedes seguir consultando los paneles generales. |
| Datos no disponibles o desactualizados | Revisa la fecha y el estado de la fuente. La ausencia de información no demuestra que el router no tenga dispositivos ni que Internet esté caído. |
