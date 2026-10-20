# Requisitos del sistema

## 1. Propósito

El MVP comprende descubrimiento de dispositivos, monitoreo de conectividad, procesamiento, análisis y presentación de resultados, además de operaciones administrativas compatibles con el router de prueba.

El acceso inicial será como Invitado, sin cuentas propias ni credenciales administrativas. Las modificaciones requerirán autorización temporal y confirmación explícita. El MVP deberá ejecutar y verificar al menos una de las operaciones administrativas definidas en el alcance.

## 2. Convenciones y aplicación

- **RF:** requisito funcional; describe un comportamiento del sistema.
- **RNF:** requisito no funcional; establece una condición de calidad o una restricción.
- **Obligatorio:** necesario para dar por cumplido el MVP.
- **Condicionado:** obligatorio cuando se cumple la condición de aplicabilidad indicada. Su exclusión requiere documentar la evidencia de que dicha condición no se cumple.
- **Propuesta posterior:** capacidad fuera de los compromisos del MVP, pendiente de especificación en otro incremento.

## 3. Requisitos funcionales

### RF-01. Identificar el entorno de monitoreo

**Aplicación:** obligatorio.

El sistema deberá identificar automáticamente la red local accesible al equipo recolector, su interfaz y su puerta de enlace cuando esté disponible, sin depender de una dirección fija de router. Si existe ambigüedad entre interfaces, solicitará la selección correspondiente.

### RF-02. Configurar la comunicación con un router compatible

**Aplicación:** condicionado al mecanismo disponible para el router probado.

El sistema deberá permitir configurar los parámetros de comunicación necesarios para consultar información y ejecutar operaciones compatibles. La configuración distinguirá las capacidades verificadas de las no disponibles.

### RF-03. Autenticar la comunicación con el router

**Aplicación:** condicionado a que el mecanismo de comunicación requiera autenticación.

El sistema deberá autenticar la comunicación cuando la operación lo requiera. La autenticación técnica ante el router no concederá privilegios a todos los visitantes ni será una condición para acceder al dashboard. Los datos inaccesibles sin autenticación se mostrarán como no disponibles.

### RF-04. Descubrir dispositivos observables

**Aplicación:** obligatorio.

El sistema deberá descubrir dispositivos visibles en la red seleccionada utilizando las fuentes compatibles con el entorno. La lista proporcionada por el router podrá utilizarse cuando esté disponible, sin ser la única fuente admisible.

### RF-05. Presentar información de los dispositivos

**Aplicación:** obligatorio; la disponibilidad de cada campo depende de la fuente.

El sistema deberá mostrar los dispositivos observados y los datos disponibles de identificación, incluyendo IP, MAC, nombre, disponibilidad observada, última observación y tipo de conexión cuando puedan obtenerse.

### RF-06. Ejecutar mediciones periódicas de conectividad

**Aplicación:** obligatorio.

El sistema deberá medir periódicamente la conectividad hacia los destinos definidos, registrando origen, destino, momento de captura y resultado de cada intento. Deberá obtener los datos necesarios para calcular latencia de ida y vuelta y disponibilidad observada.

### RF-07. Identificar cambios de presencia observada

**Aplicación:** obligatorio.

El sistema deberá comparar observaciones sucesivas para informar cambios en la presencia de dispositivos según los criterios definidos para la fuente utilizada.

### RF-08. Validar y normalizar los datos

**Aplicación:** obligatorio.

El sistema deberá validar y normalizar los datos antes de utilizarlos, conservando su fuente y momento de captura y distinguiendo valores válidos, ausentes, desactualizados y errores de recolección.

### RF-09. Calcular indicadores de conectividad

**Aplicación:** obligatorio.

El sistema deberá calcular los indicadores definidos a partir de las mediciones válidas y las ventanas de observación establecidas. Cada resultado deberá conservar su unidad, periodo, destino o conjunto observado y estado de disponibilidad de datos.

### RF-10. Detectar condiciones relevantes

**Aplicación:** obligatorio.

El sistema deberá evaluar automáticamente condiciones mediante reglas documentadas y métricas observables. Cada resultado estará relacionado con los datos que lo sustentan. No clasificará dispositivos como desconocidos, maliciosos o no autorizados por su identidad.

### RF-11. Proporcionar orientación al usuario

**Aplicación:** obligatorio.

El sistema deberá presentar explicaciones y recomendaciones sustentadas en el análisis. Cuando sugiera una operación administrativa, indicará su disponibilidad y necesidad de autorización. La recomendación no ejecutará cambios automáticamente.

### RF-12. Presentar un resumen del estado observado

**Aplicación:** obligatorio.

La interfaz deberá reunir el resumen del estado observado, los dispositivos, los indicadores principales, la última actualización y las condiciones y explicaciones derivadas del análisis.

### RF-13. Gestionar interrupciones y recuperación

**Aplicación:** obligatorio.

El sistema deberá informar la interrupción de una fuente de recolección, mantener identificados los últimos resultados disponibles y permitir reanudar las consultas cuando se restablezcan las condiciones necesarias.

### RF-14. Mantener los datos necesarios durante la ejecución

**Aplicación:** obligatorio.

El sistema deberá conservar durante la ejecución del recolector las observaciones necesarias para las ventanas de cálculo y comparación definidas, con una política acotada de retención.

### RF-15. Permitir el acceso como Invitado

**Aplicación:** obligatorio.

El sistema deberá permitir consultar el dashboard y la información disponible sin registro de cuentas propias ni credenciales administrativas. La observación y el análisis se iniciarán o continuarán automáticamente, sin requerir solicitudes individuales del usuario.

### RF-16. Obtener autorización administrativa temporal

**Aplicación:** obligatorio.

El sistema deberá validar las credenciales administrativas del router cuando una persona solicite una modificación y no disponga de autorización vigente. Una validación satisfactoria habilitará temporalmente las capacidades de Administrador únicamente para esa sesión y ese router.

### RF-17. Confirmar las modificaciones

**Aplicación:** obligatorio para toda operación administrativa.

Antes de ejecutar una modificación, el sistema deberá mostrar el objetivo, el cambio solicitado y sus posibles efectos sobre la conectividad. Exigirá confirmación explícita y comprobará nuevamente la autorización y la compatibilidad antes del envío.

### RF-18. Cambiar la contraseña Wi-Fi

**Aplicación:** condicionado al soporte comprobado del router.

El sistema deberá permitir cambiar la contraseña de la red Wi-Fi seleccionada, validando el formato admitido y la confirmación del nuevo valor. Informará sobre la posible desconexión de dispositivos. Esta operación no modificará las credenciales administrativas del router.

### RF-19. Cambiar el nombre de la red Wi-Fi

**Aplicación:** condicionado al soporte comprobado del router.

El sistema deberá permitir modificar el SSID de la red seleccionada, validando el nombre admitido e identificando las redes o bandas afectadas. Informará sobre la posible necesidad de reconectar los dispositivos.

### RF-20. Bloquear un dispositivo

**Aplicación:** condicionado al soporte comprobado del router.

El sistema deberá permitir aplicar una restricción a un dispositivo identificado por la persona. Antes de confirmarla, mostrará el dispositivo objetivo y el alcance real del bloqueo que permite el router.

### RF-21. Desbloquear un dispositivo

**Aplicación:** condicionado al soporte comprobado del router.

El sistema deberá permitir consultar y retirar restricciones compatibles, identificando el dispositivo o la regla correspondiente aunque el equipo no aparezca entre los conectados. La retirada de una restricción no se presentará como confirmación de que el dispositivo se ha reconectado.

### RF-22. Informar y verificar el resultado de las modificaciones

**Aplicación:** obligatorio para toda operación administrativa.

El sistema deberá comunicar el resultado de la solicitud y obtener nuevas observaciones para verificar su efecto. Distinguirá entre rechazo, solicitud aceptada, efecto verificado y resultado incierto. La aceptación del router no se considerará por sí sola una verificación del cambio.

### RF-23. Finalizar la autorización administrativa

**Aplicación:** obligatorio.

El sistema deberá retirar los privilegios administrativos cuando la persona finalice la autorización o esta expire. La sesión conservará las capacidades de Invitado y necesitará una nueva autorización para realizar modificaciones. El cierre no implicará revertir operaciones ya enviadas.

### RF-24. Iniciar la aplicación local

**Aplicación:** obligatorio.

La persona deberá poder abrir la aplicación instalada en su computadora e iniciar
backend y dashboard sin ejecutar comandos manuales. El iniciador comprobará la
disponibilidad de la API, informará errores e impedirá duplicar la recolección
prevista para una instalación. El mecanismo de empaquetado queda por implementar.

## 4. Requisitos no funcionales

Todos los requisitos de esta sección son obligatorios para el MVP. Las verificaciones específicas de credenciales se aplicarán cuando el sistema las utilice.

### RNF-01. Protección de credenciales

El sistema deberá limitar el uso de credenciales y tokens a los componentes que los necesiten y evitar su inclusión en código versionado, registros de ejecución, respuestas de consulta de la interfaz y evidencias compartidas. No se almacenarán secretos en texto plano de forma persistente; si se requiere persistirlos, el mecanismo de protección deberá definirse antes de implementarlo.

### RNF-02. Privacidad de las evidencias

Las evidencias compartidas deberán anonimizar los datos que identifiquen la red y sus dispositivos. Los datos recolectados se limitarán a los necesarios para las funciones definidas.

### RNF-03. Comprensibilidad de la interfaz

La interfaz deberá acompañar los indicadores técnicos con unidades, referencias temporales y explicaciones en lenguaje comprensible para usuarios no especializados. Los estados no dependerán exclusivamente del color.

### RNF-04. Separación de responsabilidades y extensibilidad

Las particularidades del router, tanto para consultas como para modificaciones, deberán mantenerse separadas de la lógica general de observación, análisis, autorización y presentación mediante contratos definidos.

### RNF-05. Respuesta de la interfaz y recolección desacoplada

La consulta de resultados procesados no deberá depender de completar una nueva medición. Las operaciones de recolección tendrán tiempos de espera acotados y los intentos pendientes se gestionarán sin acumulación ilimitada.

### RNF-06. Tolerancia a fallos parciales

Un fallo de una fuente o una medición inválida no deberá provocar el cierre completo de la aplicación ni convertir datos anteriores en observaciones actuales.

Si se pierde comunicación durante una modificación, el sistema deberá conservar su estado como incierto y evitar repetirla automáticamente sin comprobar primero el resultado.

### RNF-07. Mantenibilidad y verificación

Las reglas y cálculos deberán poder verificarse con entradas conocidas sin depender de una conexión activa al router. Los parámetros de monitoreo y análisis deberán estar documentados y separados de las particularidades del fabricante.

### RNF-08. Control de permisos administrativos

El backend deberá comprobar la autorización vigente para cada modificación, vinculándola a la sesión y al router correspondientes. Los controles de la interfaz no sustituirán esta comprobación. Una sesión autorizada no concederá privilegios a otros visitantes.

### RNF-09. Ciclo de vida y diagnóstico de fuentes

El cierre de la aplicación deberá detener las tareas y procesos controladamente.
El diagnóstico distinguirá no ejecución, fallo del proceso, captura vacía,
problema de decodificación y error de interpretación, sin registrar datos
identificables ni deducir una causa de permisos únicamente por salida vacía.
Una fuente fallida no desactivará silenciosamente la información sobre calidad.

## 5. Propuestas para etapas posteriores

Las siguientes ideas se conservan como referencia de evolución y no forman parte de los requisitos de aceptación del MVP:

| Propuesta | Condiciones previas para especificarla |
| --- | --- |
| Configurar horarios de acceso y otras operaciones administrativas | Comprobar soporte del router y definir los parámetros, permisos y verificación de cada operación adicional. |
| Incorporar compatibilidad con nuevos routers | Investigar los modelos y firmware, adaptar los mecanismos de comunicación y validar sus capacidades. |
| Consultar historial persistente de métricas | Definir periodos, retención y consultas; retomar la propuesta de MySQL del protocolo. |
| Conservar un registro histórico de acciones administrativas | Definir qué se registra, durante cuánto tiempo, quién puede consultarlo y cómo se protege. |

La presentación inmediata del resultado de una operación pertenece al MVP conforme a RF-22. Su conservación histórica corresponde a una ampliación posterior.
