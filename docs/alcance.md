# Alcance del proyecto

## 1. Alcance general

El proyecto contempla el diseño, desarrollo y evaluación de un sistema orientado al monitoreo y análisis de redes domésticas, con el propósito de proporcionar al usuario información comprensible sobre el estado y comportamiento de su red y facilitar la identificación de situaciones que puedan afectar su funcionamiento.

El sistema obtendrá información de la red local y de los dispositivos observables mediante mecanismos de comunicación y monitoreo disponibles en el entorno de ejecución. Los datos serán procesados y analizados para generar indicadores, estados y explicaciones que permitan interpretar el comportamiento de la red sin requerir conocimientos técnicos avanzados.

El sistema también permitirá realizar operaciones administrativas compatibles con el router, mediante una decisión explícita del usuario y una autorización administrativa temporal. Después de una modificación, volverá a observar la red para verificar el resultado y presentar su estado actualizado.

## 2. Alcance inicial

La primera etapa estará enfocada en construir un prototipo funcional capaz de operar dentro de una red doméstica controlada, utilizando como entorno principal de desarrollo y pruebas una red con servicio Telmex Infinitum.

El producto mínimo viable (MVP) integrará la observación de la red, el análisis automático, la presentación de resultados y recomendaciones, y la ejecución de modificaciones autorizadas que sean compatibles con el router de prueba, utilizando datos reales del entorno.

El acceso inicial será como Invitado, sin registro de cuentas propias ni credenciales administrativas. La identificación de la red, el descubrimiento y el monitoreo se realizarán automáticamente. Las credenciales del router se solicitarán cuando la persona decida ejecutar una modificación y no disponga de autorización vigente.

El uso inicial de Telmex no implica que el sistema sea exclusivo de dicho proveedor. Se separarán las funciones generales de monitoreo y análisis de aquellas que dependan del modelo de router o del mecanismo de acceso disponible. La compatibilidad demostrada se limitará a los equipos y configuraciones efectivamente probados.

### 2.1. Descubrimiento de la red

El sistema identificará automáticamente la red local accesible al equipo recolector, su puerta de enlace cuando esté disponible y los dispositivos visibles mediante mecanismos compatibles con el entorno. Si existen varias interfaces y no puede determinarse la red de manera inequívoca, solicitará la selección correspondiente. No dependerá de una dirección de administración fija para todos los routers.

Se obtendrá la información básica que pueda verificarse mediante las fuentes disponibles, como:

- Dirección IP.
- Dirección MAC.
- Nombre o hostname.
- Disponibilidad observada y última observación.
- Tipo de conexión u otros datos de identificación, cuando sean accesibles.

La disponibilidad de estos campos dependerá del dispositivo, la configuración de la red y los permisos o protocolos disponibles.

### 2.2. Monitoreo de conectividad

El sistema realizará mediciones periódicas hacia destinos definidos para observar la conectividad desde el equipo recolector. Se contemplan inicialmente:

- Disponibilidad observada respecto de los destinos consultados.
- Latencia de ida y vuelta.
- Cambios en la presencia observada de dispositivos.

Las mediciones incluirán su momento de captura y resultado. La falta de respuesta se distinguirá de un fallo del mecanismo de recolección y no se interpretará por sí sola como desconexión confirmada del dispositivo o caída de Internet.

Las unidades, fuentes, destinos, frecuencias, ventanas de cálculo y criterios de interpretación se describen en el [documento de métricas](metricas.md); los parámetros piloto deberán validarse en el entorno de prueba.

### 2.3. Obtención de información del router

El proyecto investigará los mecanismos disponibles para consultar información del router o gateway. Se podrán evaluar protocolos estándar, interfaces locales, servicios expuestos por el equipo y otros métodos de consulta controlada, sin depender exclusivamente de una API oficial del proveedor.

La información disponible dependerá de las capacidades y restricciones del equipo. Las funciones de consulta utilizarán las fuentes accesibles sin exigir credenciales administrativas al Invitado. Los datos que no puedan obtenerse en ese contexto se mostrarán como no disponibles.

Además de las consultas, se investigarán los mecanismos necesarios para ejecutar las operaciones administrativas definidas en este alcance. Cada operación deberá comprobarse en el modelo y firmware utilizados antes de considerarse compatible.

### 2.4. Procesamiento de información

Los datos se procesarán antes de presentarse al usuario. El procesamiento comprenderá, según las necesidades de cada indicador:

- Validación y normalización de mediciones.
- Organización de datos y cálculo de indicadores.
- Comparación de mediciones e identificación de cambios.
- Aplicación de reglas y clasificación de estados.
- Detección de condiciones relevantes.

### 2.5. Análisis de la red

El análisis inicial se basará en métricas y reglas explícitas cuyos criterios se documentarán y comprobarán mediante pruebas. Se diferenciarán tres niveles de información:

1. **Observación:** qué muestran las mediciones obtenidas.
2. **Análisis:** qué condiciones pueden estar relacionadas con el comportamiento observado.
3. **Orientación:** qué explicaciones o recomendaciones básicas de revisión pueden ayudar al usuario a decidir.

El análisis describirá comportamientos sustentados en métricas observables, sin clasificar un dispositivo como desconocido, malicioso o no autorizado por su identidad. Las recomendaciones serán informativas y no producirán cambios automáticos. La persona decidirá si solicita una operación administrativa, cuya ejecución requerirá autorización y confirmación.

### 2.6. Presentación de resultados

La interfaz web permitirá consultar, como mínimo:

- Un resumen del estado observado de la red.
- Los dispositivos detectados y sus datos disponibles.
- Los indicadores principales y su última actualización.
- Las condiciones relevantes identificadas.
- Las explicaciones derivadas del análisis.

Los valores técnicos se acompañarán de contexto sobre su significado dentro de los criterios establecidos. El resumen reflejará el alcance de las mediciones disponibles.

### 2.7. Conservación de información

El MVP podrá conservar temporalmente las mediciones necesarias para calcular indicadores y mostrar resultados durante una sesión. La consulta de historial entre sesiones y el almacenamiento indefinido no serán requisitos de esta primera implementación.

El protocolo propone MySQL y almacenamiento histórico. Su incorporación se definirá para los incrementos posteriores; esta delimitación del MVP no elimina ese componente de la propuesta general del proyecto.

### 2.8. Administración autorizada

El sistema contemplará las siguientes operaciones, condicionadas al soporte comprobado del router:

- Cambiar la contraseña de acceso a una red Wi-Fi.
- Cambiar el nombre de una red Wi-Fi (SSID).
- Bloquear un dispositivo mediante la restricción que permita el router.
- Desbloquear un dispositivo retirando una restricción compatible.

La persona obtendrá temporalmente las capacidades de Administrador mediante la validación de las credenciales administrativas del router. La autorización estará vinculada a su sesión y al router correspondiente, y finalizará al cerrarse explícitamente o expirar.

Cada modificación requerirá confirmar el objetivo y el cambio solicitado. El sistema comprobará la autorización antes de ejecutarla y consultará posteriormente el estado para verificar su efecto. Distinguirá entre una solicitud aceptada, un resultado verificado, un rechazo y un resultado incierto.

La contraseña Wi-Fi y las credenciales administrativas del router se tratarán como datos distintos. La autorización de una persona no concederá privilegios a los demás visitantes.

## 3. Arquitectura dentro del alcance

El sistema se diseñará mediante una arquitectura modular que separe adquisición de información, descubrimiento, monitoreo, procesamiento, análisis, presentación de resultados, autorización administrativa y ejecución de operaciones compatibles con el router.

Se contemplan componentes o agentes especializados, entendidos como módulos de software con responsabilidades delimitadas. La separación permitirá incorporar mecanismos de comunicación sin reconstruir el sistema completo y desacoplar la recolección periódica de las consultas de la interfaz.

## 4. Entorno inicial de pruebas y evaluación

Las pruebas se realizarán en una red doméstica autorizada con servicio Telmex Infinitum, el módem/router disponible, un conjunto identificado de dispositivos y un equipo local encargado de ejecutar el sistema.

La evaluación inicial incluirá pruebas de funcionamiento integrado, ausencia de datos, fallos de recolección y recuperación. También comprenderá autorización válida, rechazada y expirada; cancelación de operaciones; ejecución de modificaciones compatibles y verificación posterior, incluyendo posibles pérdidas de conexión durante el cambio.

Los resultados no se considerarán automáticamente representativos de todos los routers, proveedores o escenarios de uso.

## 5. Evolución del alcance

Una vez comprobado el MVP, se podrán plantear incrementos para:

- Habilitar consulta desde teléfonos en la red de la instalación, definiendo
  acceso, transporte y sesiones; mantener un recolector local activo.
- Adaptar el recolector y el empaquetado a otros sistemas operativos.
- Probar otros modelos de router y proveedores de Internet.
- Implementar almacenamiento histórico y análisis temporal.
- Mejorar las explicaciones y recomendaciones.
- Incorporar otras operaciones administrativas, como horarios de acceso, una vez comprobada su viabilidad y definidos sus requisitos.

## 6. Restricciones y consideraciones

El funcionamiento estará condicionado por el fabricante, modelo y firmware del router, el proveedor, la configuración de red, el sistema operativo, los protocolos habilitados, los permisos y las restricciones de acceso de los dispositivos.

Las credenciales administrativas se utilizarán para validar la autorización y realizar las operaciones compatibles solicitadas. No se incluirán en el repositorio, registros de ejecución, respuestas de consulta ni evidencias compartidas. Los datos identificables de la red se anonimizarán en las evidencias que se compartan.

Los cambios de contraseña, SSID o restricciones de acceso pueden interrumpir la conexión del usuario o del recolector. El sistema informará ese efecto antes de la confirmación. Si pierde comunicación durante una modificación, no declarará éxito ni repetirá automáticamente la operación sin comprobar primero su estado.

## 7. Criterio de cumplimiento del alcance inicial

Se considerará alcanzada la primera etapa funcional cuando el prototipo pueda ejecutarse en el entorno definido y permita, de manera integrada:

1. Abrir la aplicación instalada, iniciar su backend local y presentar el dashboard sin comandos manuales; reconocer la red local seleccionada para el monitoreo.
2. Detectar dispositivos observables y contrastar los resultados con el inventario de prueba.
3. Obtener y presentar información básica de los dispositivos cuando esté disponible.
4. Realizar mediciones periódicas de conectividad y calcular los indicadores definidos.
5. Procesar las mediciones y distinguir resultados válidos, ausentes, desactualizados y fallos de recolección.
6. Presentar resultados cuya interpretación pueda comprobarse mediante una evaluación básica con usuarios.
7. Permitir la consulta como Invitado sin credenciales administrativas.
8. Habilitar y finalizar la autorización administrativa temporal, impidiendo modificaciones sin permisos vigentes.
9. Ejecutar y verificar al menos una de las operaciones administrativas definidas, seleccionada tras comprobar las capacidades del router.
10. Informar los rechazos y los resultados que no hayan podido verificarse, sin presentarlos como cambios exitosos.

Las cuatro operaciones administrativas se contemplan en el diseño; su implementación dependerá de la compatibilidad comprobada. La demostración de al menos una operación verificada constituye el mínimo administrativo del MVP. Si ninguna resulta viable, deberá revisarse explícitamente este alcance antes de declarar completo el ciclo funcional.

El cumplimiento del MVP demostrará las capacidades comprobadas en el entorno inicial y permitirá planear los siguientes incrementos.