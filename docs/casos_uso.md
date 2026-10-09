# Casos de uso del sistema

- **Invitado:** persona que accede desde la red doméstica observada y consulta la información disponible sin credenciales administrativas.
- **Administrador:** el mismo Invitado mientras dispone de autorización administrativa temporal para un router y su sesión. Conserva todas las capacidades de consulta.

### CU-01. Consultar el estado general de la red

**Actor:** Invitado o Administrador.

**Objetivo:** conocer el estado observado de la red mediante un resumen comprensible.

**Precondiciones:** la persona tiene acceso al sistema desde la red doméstica de prueba. No se requiere autorización administrativa.

**Flujo principal:**

1. La persona accede al sistema; si no tiene autorización administrativa, lo hace como Invitado.
2. El sistema identifica automáticamente el entorno de red e inicia o continúa la observación compartida, sin crear un recolector por visitante.
3. El sistema obtiene los datos accesibles, los procesa y analiza automáticamente.
4. El dashboard muestra el resumen del estado observado, su última actualización y las condiciones relevantes disponibles.
5. La persona consulta el resumen y puede acceder a dispositivos, métricas o resultados del análisis.
6. El sistema actualiza los resultados conforme obtiene nuevas observaciones.

**Alternativas o errores:**

- **A1. Primeras mediciones pendientes:** se muestra que se están obteniendo datos; no se presenta un estado saludable sin información suficiente.
- **A2. Red o fuente inaccesible:** se informa la limitación, se identifican los resultados anteriores y se mantienen las consultas que no dependan de la fuente afectada.
- **A3. Dato que requiere acceso autenticado:** se indica que no está disponible la consulta. No se exige proporcionar credenciales para acceder al dashboard.

**Resultado esperado:** la persona conoce el estado con los datos disponibles. La consulta no modifica la red.

### CU-02. Consultar dispositivos y su información disponible

**Actor:** Invitado o Administrador.

**Objetivo:** conocer los dispositivos observados y revisar su información de identificación y presencia.

**Precondiciones:** la persona ha accedido al dashboard y el proceso automático de descubrimiento está habilitado, aunque todavía pueda estar obteniendo resultados.

**Flujo principal:**

1. La persona abre la consulta de dispositivos.
2. El sistema presenta los dispositivos observados y la referencia temporal de la información.
3. El sistema muestra los campos disponibles, como IP, MAC, nombre, disponibilidad observada, última observación y tipo de conexión.

**Alternativas o errores:**

- **A1. Sin dispositivos observados:** se informa si el descubrimiento sigue en curso, no produjo resultados o falló. Una lista vacía no demuestra que no existan dispositivos conectados.
- **A2. Campos incompletos:** se muestran los datos accesibles sin inventar valores. La falta de nombre no clasifica al dispositivo como desconocido, malicioso o no autorizado.

**Resultado esperado:** la persona identifica qué dispositivos fueron observados y su información.

### CU-03. Consultar resultados del análisis y recomendaciones

**Actor:** Invitado o Administrador.

**Objetivo:** comprender una situación detectada y decidir qué hacer a partir de la información y orientación disponibles.

**Precondiciones:** el sistema tiene reglas de análisis definidas y evalúa automáticamente los datos disponibles. No es necesario que haya detectado una condición relevante para acceder a la consulta.

**Flujo principal:**

1. La persona consulta los resultados del análisis desde el dashboard.
2. El sistema muestra las condiciones detectadas y su referencia temporal.
3. La persona abre el detalle de una condición.
4. El sistema explica las observaciones.
5. El sistema presenta una recomendación aplicable y, cuando corresponda, indica si una posible acción es compatible y requiere autorización.

**Alternativas o errores:**

- **A1. Datos insuficientes o desactualizados:** se señala la limitación y no se presenta una causa confirmada ni una situación actual sin sustento.
- **A2. Sin recomendación aplicable:** se muestra la explicación disponible sin inventar una acción.
- **A3. Acción no compatible:** se informa la limitación y no se ofrece su ejecución como disponible.
- **A4. Sin condiciones detectadas:** se informa que no se identificaron condiciones con los datos y reglas disponibles, sin garantizar que toda la red esté libre de problemas.
- **A5. La persona decide no actuar:** continúa consultando la red sin solicitar credenciales ni realizar modificaciones.

**Resultado esperado:** la persona distingue observación, interpretación y recomendación, y conserva la decisión sobre cualquier cambio. La consulta de una recomendación no autoriza su ejecución.

### CU-04. Obtener autorización administrativa

**Actor:** Invitado que desea realizar una modificación compatible.

**Objetivo:** habilitar temporalmente las capacidades administrativas de su sesión para el router correspondiente.

**Precondiciones:** la persona ha solicitado una modificación; el router y su mecanismo de validación son compatibles.

**Flujo principal:**

1. El sistema explica que la operación solicitada requiere autorización administrativa.
2. La persona proporciona las credenciales administrativas del router.
3. El sistema valida las credenciales mediante el mecanismo compatible, sin modificar la configuración del equipo.
4. Tras una validación satisfactoria, el sistema habilita las capacidades de Administrador únicamente para esa sesión y ese router.

**Alternativas o errores:**

- **A1. Credenciales inválidas:** se informa el rechazo sin revelar los valores utilizados; la persona conserva las capacidades de Invitado y la modificación no se ejecuta.
- **A2. Router inaccesible o validación inconclusa:** no se concede autorización. Se informa el problema y puede repetirse la validación cuando se restablezca la comunicación.

**Resultado esperado:** la sesión obtiene autorización o conserva únicamente las capacidades de Invitado. La autenticación no ejecuta por sí sola la operación ni concede permisos a otros visitantes.

### CU-05. Cambiar la contraseña Wi-Fi

**Actor:** Administrador.

**Objetivo:** modificar la contraseña de acceso a la red Wi-Fi seleccionada. Esta contraseña es distinta de las credenciales administrativas del router.

**Precondiciones:** el router permite modificar la contraseña mediante un mecanismo compatible y el sistema identifica la red Wi-Fi o banda a la que se aplicará el cambio. Se requiere autorización administrativa vigente antes de ejecutar la modificación.

**Flujo principal:**

1. La persona selecciona la red Wi-Fi y solicita cambiar su contraseña.
2. El sistema comprueba que la operación está soportada y verifica la autorización; si no está vigente, se realiza CU-04.
3. La persona introduce la nueva contraseña y su confirmación.
4. El sistema valida la coincidencia y los requisitos de contraseña admitidos por el router, e informa que los dispositivos pueden desconectarse y necesitar la nueva contraseña para reconectarse.
5. El Administrador confirma el cambio sobre la red seleccionada.
6. El sistema comprueba nuevamente la autorización y envía la modificación sin exponer la contraseña en registros o mensajes de resultado.
7. El sistema informa la respuesta del router y, cuando dispone de conexión, comprueba el resultado mediante el mecanismo de verificación disponible, sin mostrar la contraseña almacenada.

**Alternativas o errores:**

- **A1. Operación no soportada:** se informa la limitación y no se intenta modificar la contraseña.
- **A2. Contraseñas distintas o formato no admitido:** se solicita corregir los datos antes del envío.
- **A3. Cancelación o autorización inválida:** no se envía el cambio. Si se requiere una nueva autorización, se realiza CU-04 y se solicita confirmar nuevamente.
- **A4. Router rechaza la modificación:** se informa el rechazo sin anunciar que la contraseña cambió.
- **A5. Pérdida de conexión durante el cambio:** se indica que puede ser necesario reconectar el equipo con la nueva contraseña. El resultado queda pendiente de verificación; no se repite automáticamente la modificación.

**Resultado esperado:** la contraseña de la red seleccionada queda modificada y verificada cuando es posible, o la persona recibe un estado explícito de rechazo o verificación pendiente. No se modifican las credenciales administrativas del router.

### CU-06. Cambiar el nombre de la red Wi-Fi

**Actor:** Administrador.

**Objetivo:** modificar el nombre de la red inalámbrica, también denominado SSID.

**Precondiciones:** el router admite el cambio de SSID mediante un mecanismo compatible y el sistema identifica la red o banda afectada. Se requiere autorización administrativa vigente antes de ejecutar la modificación.

**Flujo principal:**

1. La persona selecciona la red Wi-Fi y solicita cambiar su nombre.
2. El sistema verifica la compatibilidad y la autorización; si es necesario, se realiza CU-04.
3. El sistema muestra el nombre actual y la persona introduce el nuevo SSID.
4. El sistema valida el nombre según las restricciones del router y explica qué red o bandas se modificarán y la posible necesidad de reconectar dispositivos.
5. El Administrador confirma el cambio.
6. El sistema comprueba nuevamente la autorización y envía la modificación al router.
7. El sistema consulta el estado actualizado cuando la conexión lo permite y comprueba si el SSID coincide con el solicitado.

**Alternativas o errores:**

- **A1. Operación no soportada:** se informa la limitación sin realizar cambios.
- **A2. Nombre no admitido:** se solicita corregirlo. Si coincide con el actual, se informa que no hay un cambio que aplicar.
- **A3. Cancelación o autorización inválida:** no se envía la modificación; la reautorización se realiza mediante CU-04 antes de una nueva confirmación.
- **A4. Router rechaza el cambio:** se informa el rechazo y se conserva la última información observada, identificando su vigencia.
- **A5. Desconexión durante la operación:** se informa que puede ser necesario conectarse al nuevo nombre y se deja el resultado pendiente hasta poder consultar el estado.

**Resultado esperado:** el SSID de la red seleccionada coincide con el solicitado y se presenta su estado actualizado, o se informa el rechazo, la discrepancia o la imposibilidad de verificarlo.

### CU-07. Bloquear un dispositivo

**Actor:** Administrador.

**Objetivo:** aplicar una restricción de acceso a un dispositivo elegido por la persona, dentro de las capacidades del router.

**Precondiciones:** el router ofrece un mecanismo de bloqueo compatible y el sistema puede identificar inequívocamente el dispositivo objetivo con los datos que requiere ese mecanismo. Se requiere autorización administrativa vigente antes de aplicar la restricción.

**Flujo principal:**

1. La persona selecciona un dispositivo y solicita bloquearlo.
2. El sistema comprueba el soporte de la operación y muestra la identificación del equipo y el alcance real de la restricción, por ejemplo, acceso a Internet o conexión Wi-Fi, según el router.
3. El sistema verifica la autorización; si no está vigente, se realiza CU-04.
4. El Administrador revisa el objetivo y confirma el bloqueo. Si se identifica que afecta al equipo de acceso o al recolector, se explica la posible interrupción antes de confirmar.
5. El sistema comprueba nuevamente la autorización y la identidad del objetivo, y solicita aplicar la restricción.
6. El sistema informa la respuesta del router y consulta la regla o el estado de bloqueo disponible.
7. El sistema actualiza la información del dispositivo y distingue la regla aplicada del efecto que haya podido observar.

**Alternativas o errores:**

- **A1. Operación no soportada o dispositivo no identificable:** no se envía el bloqueo y se explica la limitación.
- **A2. Dispositivo ya bloqueado:** se informa el estado actual sin crear una restricción duplicada.
- **A3. Cancelación, autorización vencida o identificación cambiada:** no se envía la operación hasta resolver la condición y obtener una nueva confirmación cuando corresponda.
- **A4. Router rechaza la operación:** se informa el rechazo sin presentar al dispositivo como bloqueado.
- **A5. Comunicación interrumpida o resultado incierto:** se consulta el estado cuando sea posible antes de repetir cualquier operación. La desaparición del dispositivo por sí sola no demuestra que el bloqueo se aplicó.
- **A6. Efecto no verificable:** se informa si la regla fue confirmada y qué parte de su efecto no pudo comprobarse.

**Resultado esperado:** la restricción solicitada queda aplicada al dispositivo seleccionado con el alcance soportado y el nivel de verificación disponible, o se informa por qué no pudo completarse. El bloqueo responde a una decisión explícita de la persona, no a una clasificación automática de la identidad del dispositivo.

### CU-08. Finalizar la autorización administrativa

**Actor:** Administrador.

**Objetivo:** terminar los privilegios administrativos de la sesión y continuar únicamente con las funciones de Invitado.

**Precondiciones:** la sesión tiene una autorización administrativa vigente.

**Flujo principal:**

1. La persona solicita finalizar la autorización administrativa.
2. El sistema invalida los permisos administrativos asociados a esa sesión y al router.
3. El sistema impide nuevas modificaciones con esa autorización, aunque se intenten desde una pantalla previamente abierta.
4. El sistema informa que la persona continúa como Invitado y mantiene las funciones de consulta disponibles.

**Alternativas o errores:**

- **A1. Expiración automática:** el sistema aplica la misma retirada de privilegios sin requerir una solicitud de la persona. La expiración es un evento del sistema, no un actor adicional.
- **A2. Autorización ya terminada:** se informa el estado de Invitado sin recrear ni extender privilegios.
- **A3. Operación confirmada pero no enviada:** se impide su envío con la autorización invalidada.
- **A4. Operación ya enviada:** terminar la autorización no revierte ni garantiza cancelar lo que el router ya recibió. Se conserva la información de resultado y se verifica con las fuentes disponibles; si no es posible, se informa la limitación.
- **A5. Router inaccesible al cerrar la sesión remota:** el backend retira de todas formas los permisos locales de esa sesión y comunica la limitación de cierre remoto, sin permitir nuevas operaciones.

**Resultado esperado:** la sesión vuelve a las capacidades de Invitado y cualquier nueva modificación exige otra autorización. No se revocan las sesiones de otras personas ni se promete revertir cambios ya ejecutados.

### CU-09. Desbloquear un dispositivo

**Actor:** Administrador.

**Objetivo:** retirar una restricción compatible aplicada a un dispositivo.

**Precondiciones:** el router permite consultar y retirar la restricción, y el sistema puede identificar la regla y su dispositivo objetivo. Se requiere autorización administrativa vigente antes del envío; el dispositivo no necesita aparecer entre los conectados.

**Flujo principal:**

1. La persona consulta las restricciones disponibles y selecciona la que desea retirar.
2. El sistema muestra el dispositivo, la regla y el alcance del desbloqueo, y comprueba su compatibilidad.
3. El sistema verifica la autorización; si no está vigente, se realiza CU-04.
4. El Administrador confirma la retirada de la restricción seleccionada.
5. El sistema comprueba nuevamente la autorización y la regla objetivo, y envía la solicitud al router.
6. El sistema consulta las restricciones para verificar la retirada y presenta el resultado.

**Alternativas o errores:**

- **A1. Operación no soportada o regla no identificable:** se informa la limitación y no se envía la modificación.
- **A2. Restricción ya retirada:** se informa el estado consultado sin repetir la operación.
- **A3. Cancelación, autorización vencida o regla modificada:** se detiene el envío hasta resolver la condición y obtener una nueva confirmación cuando corresponda.
- **A4. Router rechaza la operación:** se informa el rechazo sin anunciar el desbloqueo.
- **A5. Comunicación interrumpida o resultado incierto:** se informa que falta verificar la retirada; no se repite automáticamente la modificación.
- **A6. Dispositivo aún no observado:** la retirada verificada de la regla no se presenta como prueba de reconexión ni de eliminación de otras restricciones.

**Resultado esperado:** la restricción seleccionada queda retirada y verificada, o se informa el rechazo o la verificación pendiente. La conectividad del dispositivo se observa por separado.

## Límites

Estos casos corresponden al [alcance](alcance.md) y los [requisitos](requisitos.md) definidos. Las cuatro operaciones administrativas están condicionadas al soporte comprobado del router; el mínimo del MVP exige ejecutar y verificar al menos una. Los horarios de acceso corresponden a una ampliación posterior.
