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

## Desarrollo local

### Entorno comprobado

- macOS.
- Python 3.14.0.
- Node.js 22.21.1.
- Git 2.51.0.

El backend inicial utiliza únicamente la biblioteca estándar de Python.
Node.js se utilizará posteriormente para el desarrollo de la interfaz Vue.

### Preparación inicial

Desde la raíz del repositorio, crear el entorno virtual:

```bash
python3 -m venv .venv
```

Este paso se realiza una vez por entorno local.

### Activación del entorno

En cada nueva terminal utilizada para desarrollar:

```bash
source .venv/bin/activate
```

Comprobar el intérprete:

```bash
python -c "import sys; print(sys.executable)"
```

La ruta debe corresponder a `.venv/bin/python` dentro del repositorio.

### Ejecución

Desde la raíz del repositorio:

```bash
python -m backend
```

Resultado esperado:

```text
Backend del Sistema de Análisis de Redes iniciado.
```

Esta ejecución comprueba el punto de entrada del paquete.
Todavía no inicia un servidor, descubre dispositivos ni mide conectividad.

### Ejecutar una sonda individual

Esta funcionalidad requiere macOS y el entorno virtual activo.

Consultar la ayuda:

```bash
python -m backend sonda --help
```

Para enviar una solicitud ICMP a un destino IPv4 autorizado:

```bash
python -m backend sonda DIRECCION_IPV4
```

Sustituir DIRECCION_IPV4 por la dirección real del destino.
No escribir literalmente ese marcador.

Para consultar la puerta de enlace actual en macOS:

```bash
route -n get default
```

El campo gateway indica la puerta de enlace de la ruta consultada.

El comando sonda devuelve un objeto JSON con:

- destino: dirección IPv4 consultada.
- inicio: fecha y hora de inicio, con zona horaria.
- metodo: mecanismo utilizado.
- espera_ms: plazo de respuesta configurado.
- estado: resultado del intento.
- rtt_ms: tiempo de ida y vuelta cuando existe una respuesta válida.
- detalle: explicación adicional, cuando corresponde.

Estados posibles:

| Estado | Significado |
| --- | --- |
| respuesta_valida | Se reconoció una respuesta dentro del plazo. |
| sin_respuesta | No se obtuvo respuesta dentro del plazo establecido. |
| error_recoleccion | Ocurrió un error al ejecutar o interpretar la prueba. |

Si no existe un RTT válido, rtt_ms es null; no se sustituye por cero.

Una dirección inválida se rechaza antes de ejecutar la sonda.
La validación del formato no demuestra que el destino exista o pertenezca
a la red local.

Una respuesta de la puerta de enlace no demuestra acceso a Internet.
Una ausencia de respuesta tampoco confirma por sí sola una desconexión.

### Configuración de la sonda

Los tiempos se definen y validan mediante `ConfiguracionSonda`,
en `backend/configuracion.py`.

| Parámetro | Valor predeterminado | Propósito |
| --- | --- | --- |
| `espera_ms` | 1000 ms | Plazo para aceptar una respuesta de la sonda. |
| `limite_proceso_s` | 5 s | Límite de espera por la finalización del proceso `ping`. |

Ambos parámetros deben ser enteros positivos; no se aceptan
booleanos. El límite del proceso, convertido a milisegundos,
debe ser mayor que la espera de respuesta.

Un tipo incorrecto produce `TypeError`. Un valor no permitido
o una relación inválida entre los tiempos produce `ValueError`.

Al llamar a `ejecutar_sonda(destino)` se utiliza la configuración
predeterminada. Desde código Python puede proporcionarse una
configuración personalizada como segundo argumento.

Ejemplo de construcción de una configuración; este fragmento
no ejecuta ninguna sonda:

```python
from backend.configuracion import ConfiguracionSonda

configuracion = ConfiguracionSonda(
    espera_ms=2000,
    limite_proceso_s=6,
)
```

Los campos no pueden reasignarse después de crear la configuración.
Para utilizar otros valores, se construye otra instancia.

El comando `python -m backend sonda DIRECCION_IPV4` utiliza los
valores predeterminados; todavía no ofrece argumentos para
personalizar estos tiempos.

Una respuesta cuyo RTT supera `espera_ms` se clasifica como
`sin_respuesta`, sin RTT válido. Si se agota el límite del proceso,
se devuelve `error_recoleccion`.

El límite del proceso no es el intervalo entre sondas.
Esta versión ejecuta una sola sonda por llamada y todavía
no implementa monitoreo periódico.

### Ejecutar las pruebas automatizadas

Desde la raíz del repositorio, con el entorno virtual activo:

```bash
python -m unittest discover -s tests -v
```

Las pruebas utilizan respuestas simuladas y no envían tráfico a la red.

El resumen debe indicar que se ejecutaron pruebas y terminar con OK.
Un resultado de cero pruebas no verifica el funcionamiento.

### Finalizar el uso del entorno

```bash
deactivate
```

Este comando desactiva el entorno en la terminal actual; no elimina sus archivos.

### Archivos locales

La carpeta `.venv` no se incorpora al repositorio.
Las credenciales y los datos privados de la red tampoco deben incorporarse.
