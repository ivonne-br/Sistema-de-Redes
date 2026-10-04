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

### Finalizar el uso del entorno

```bash
deactivate
```

Este comando desactiva el entorno en la terminal actual; no elimina sus archivos.

### Archivos locales

La carpeta `.venv` no se incorpora al repositorio.
Las credenciales y los datos privados de la red tampoco deben incorporarse.