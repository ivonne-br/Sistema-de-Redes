# Métricas de monitoreo

## 1. Condiciones de medición

Toda observación deberá identificar:

- Fuente y método de obtención.
- Equipo recolector e interfaz utilizada.
- Destino, dispositivo o interfaz observados.
- Momento de captura y, para resultados agregados, inicio y fin del periodo.
- Valor y unidad, cuando exista una medición válida.
- Resultado del intento: respuesta válida, sin respuesta, error de recolección o dato no disponible.
- Contexto de acceso: información consultable como Invitado o información restringida a una sesión autorizada.

Los intervalos y duraciones se calcularán con un reloj monotónico del recolector; las marcas de tiempo para presentación conservarán su zona horaria. Se compararán muestras del mismo método, destino y punto de observación. Un cambio de interfaz, red o método iniciará una serie diferenciada.

### Información accesible

La consulta del dashboard no requerirá credenciales administrativas. Si una métrica necesita una fuente autenticada y no existe una alternativa disponible en ese contexto, se mostrará como no disponible. Los datos obtenidos mediante una sesión administrativa no se publicarán automáticamente a todos los visitantes.

## 2. Catálogo inicial

| ID | Métrica o indicador | Unidad | Aplicación |
| --- | --- | --- | --- |
| M-01 | Latencia de ida y vuelta | ms | Obligatoria, por destino de prueba. |
| M-02 | Disponibilidad observada mediante sondas | % de intentos evaluables con respuesta | Obligatoria, por destino y ventana. |
| M-03 | Cantidad de dispositivos observados | Dispositivos | Obligatoria, limitada a la fuente y red observadas. |
| M-04 | Presencia y cambios de presencia | Estado y eventos | Obligatoria, por dispositivo observado. |
| M-05 | Antigüedad y cobertura de las mediciones | s y % | Indicadores de calidad necesarios para interpretar las métricas. |
| M-06 | Volumen de datos observado | bytes o MB decimales | Condicionado a contadores accesibles y verificables. |
| M-07 | Tasa de transferencia observada | Mbps | Condicionada a M-06 y a intervalos comparables. |
| M-08 | Participación de un dispositivo en el tráfico observado | % | Condicionada a contadores comparables por dispositivo. |

IP, MAC, nombre, tipo de conexión y SSID son atributos de identificación o configuración; no son por sí mismos métricas de rendimiento. Se conservarán únicamente cuando puedan obtenerse y relacionarse de forma confiable con su fuente.

## 3. Métricas del MVP

### M-01. Latencia de ida y vuelta

Medir el tiempo de respuesta entre el recolector y un destino mediante una solicitud y su respuesta correspondiente.

**Cálculo:** `RTT_ms = (tiempo_respuesta - tiempo_envío) × 1000` (con tiempos en segundos). Para la ventana se presentará el promedio de RTT válidos, junto con el número de respuestas utilizadas.

Un intento sin respuesta no tiene RTT válido; no se asignará cero ni se utilizará el timeout como si fuera una medición. Si no hay respuestas, el promedio será no disponible.

**Interpretación:** describe la respuesta del destino al método utilizado, no el tiempo de descarga ni el desempeño de todas las aplicaciones. La definición de ida y vuelta y el tratamiento de respuestas ausentes toman como referencia [RFC 2681](https://www.rfc-editor.org/rfc/rfc2681.html); la implementación del prototipo no se presenta como una medición certificada de ese estándar.

### M-02. Disponibilidad observada mediante sondas

Expresar qué proporción de los intentos evaluables recibió respuesta dentro del tiempo de espera.

Se definen:

- `R`: intentos con respuesta válida dentro del tiempo de espera.
- `S`: intentos enviados cuya espera terminó sin respuesta válida.
- `E = R + S`: intentos evaluables.
- `F`: intentos con error local de recolección, separados de E.

**Cálculo:** `disponibilidad_observada = 100 × R / E`. Si `E = 0`, el resultado será no disponible.

Las respuestas tardías se registrarán como tales sin convertirlas en respuestas dentro del tiempo de espera. Los duplicados no incrementarán R. Un fallo de permisos, un error de ejecución o un intento omitido no se contarán como una sonda sin respuesta.

**Interpretación:** Se mostrará junto con E y la cobertura para no ocultar periodos sin recolección. `100 × S / E` puede describirse como porcentaje de sondas sin respuesta; no acredita pérdida general del tráfico ni la causa de esa ausencia.

### M-03. Cantidad de dispositivos observados

Indicar cuántos dispositivos tienen presencia observada vigente mediante las fuentes seleccionadas.

**Fuente:** ciclos de descubrimiento y, cuando sea accesible, información de dispositivos del router.

**Cálculo:** número de identificadores internos únicos con presencia vigente para la fuente y red seleccionadas. La referencia temporal será la del último ciclo utilizable, no la del momento en que se abre el dashboard.

Una misma observación no deberá duplicarse por aparecer varias veces en la misma fuente. La asociación entre fuentes se hará solo cuando exista evidencia suficiente. Si no puede resolverse, se mantendrán inventarios separados en lugar de sumar equipos posiblemente duplicados.

**Interpretación:** representa dispositivos observados, no una garantía de todos los dispositivos conectados. Una dirección IP puede cambiar y una MAC no se tratará como identificador universal e inmutable de una persona o equipo.

### M-04. Presencia y cambios de presencia

Identificar nuevas observaciones y cambios en la visibilidad de un dispositivo.

**Fuente:** ciclos sucesivos y comparables de descubrimiento, conservando el método y el alcance de cada ciclo.

**Estados:**

- **Observado:** existe una observación reciente válida.
- **No observado recientemente:** el dispositivo falta en el número establecido de ciclos completados y comparables.
- **Indeterminado:** la fuente falló, cambió el entorno o no hay evidencia suficiente para evaluar la presencia.

**Cálculo:** comparar los conjuntos de dispositivos de ciclos válidos. Se generará un evento de primera observación o reaparición cuando corresponda, y uno de ausencia observada al cumplir la condición configurada. La primera carga del inventario se marcará como inicial, sin afirmar que todos esos equipos acaban de conectarse.

Solo cuentan como ausencias los ciclos que pudieron evaluar el mismo ámbito; un ciclo fallido, parcial, cancelado u omitido interrumpirá la racha de ausencias consecutivas y reiniciará el contador, sin confirmar ausencia. Una nueva observación también reiniciará ese contador.

No observar un equipo no confirma que esté apagado o desconectado. El descubrimiento no permite etiquetarlo como malicioso o no autorizado.

### M-05. Antigüedad y cobertura

Expresar si existen suficientes datos recientes para interpretar los indicadores.

**Antigüedad:** `instante_actual - instante_de_la_última_observación_utilizable`, en segundos dentro de la misma ejecución. Para M-01 se utiliza la última respuesta válida; para M-02, el último resultado evaluable; para el inventario, el último ciclo utilizable, conservando la última observación de cada dispositivo. Si no existe esa referencia, la antigüedad será no disponible.

**Cobertura de sondas:** `100 × E / P`, donde P es el número de intentos programados cuya hora de finalización esperada ya pasó dentro de la ventana. Los errores y omisiones se informarán por separado. Un intento aún pendiente no entra en P ni en E hasta su plazo de cierre; R y S se asociarán a esas mismas posiciones del calendario. Los reintentos no inflarán la cobertura y, si se permiten, deberán registrarse separados.

Si `P = 0`, la cobertura será no disponible. No se programará retrospectivamente actividad anterior al inicio de la sesión, pero se indicará cuando la ventana todavía sea parcial.

**Estados:** vigente, desactualizado, insuficiente, error de fuente y no disponible. Un valor puede existir y estar desactualizado; esas condiciones se almacenarán separadas del resultado numérico.

## 4. Métricas complementarias de tráfico y uso

Su incorporación queda condicionada a disponer de fuentes compatibles y verificables.

### M-06. Volumen de datos observado

Contadores acumulados de bytes de una interfaz o de un dispositivo, cuya procedencia y dirección estén documentadas.

**Cálculo:** `volumen_bytes = contador_final - contador_inicial`; `volumen_MB = volumen_bytes / 1 000 000`. Se calcularán envío y recepción por separado desde la perspectiva de la fuente.

Solo se compararán contadores de la misma entidad, dirección y generación de contador. Un reinicio, cambio de interfaz, desbordamiento no resuelto o descenso del contador invalidará el intervalo y establecerá una nueva referencia. No se convertirán diferencias negativas a valores absolutos.

Los contadores locales obtenidos con `psutil.net_io_counters` describen el equipo recolector y pueden desglosarse por interfaz; no proporcionan automáticamente el tráfico de los demás dispositivos. Según la [documentación oficial de psutil](https://psutil.readthedocs.io/stable/#psutil.net_io_counters).

### M-07. Tasa de transferencia observada

**Cálculo:** `tasa_Mbps = 8 × volumen_bytes / (intervalo_segundos × 1 000 000)`, con intervalo mayor que cero.

Se mostrarán transmisión y recepción por separado. En un adaptador de router se documentará si esas direcciones se expresan desde el dispositivo cliente, la interfaz LAN o la interfaz WAN antes de denominarlas subida o bajada.

Es una tasa promedio durante el intervalo, no la capacidad máxima del enlace ni una prueba de velocidad del servicio contratado. No se sumarán interfaces que puedan contar dos veces el mismo tráfico.

### M-08. Participación de un dispositivo

**Cálculo:** `participación_i = 100 × volumen_i / suma_volúmenes_del_conjunto_observado`. Si el denominador es cero o faltan datos necesarios para esa comparación, el resultado será no disponible.

Los volúmenes deberán corresponder a la misma ventana, dirección y fuente comparable, con atribución por dispositivo sin duplicados. No se mezclarán contadores locales del recolector con contadores de otros ámbitos.

La interfaz identificará el conjunto de referencia. Si no representa a toda la red, el mensaje será «participación en el tráfico observado», sin afirmar que expresa el porcentaje total de consumo de Internet.

Una participación elevada puede darse con poco tráfico total. Para señalar consumo elevado se requerirá también una tasa o volumen absoluto y criterios documentados; el porcentaje por sí solo no justificará una alerta ni una acción administrativa.

### Información Wi-Fi por investigar

El canal, banda, intensidad de señal y otros atributos solo se incorporarán si existe una fuente que especifique su significado, unidad y punto de medición. No se equiparará la señal recibida por el recolector con la de todos los dispositivos ni el canal utilizado con su ocupación.

## 5. Parámetros iniciales para la prueba piloto

Los siguientes valores son propuestas configurables para comenzar con un conjunto pequeño de destinos. Deberán registrarse en cada prueba y revisarse si la carga, los permisos o el comportamiento del equipo los hacen inadecuados.

| Parámetro | Valor inicial propuesto | Uso |
| --- | --- | --- |
| Intervalo de sondas por destino | 5 s | M-01 y M-02. |
| Tiempo de espera por sonda | 1 s | Separar respuesta en plazo y ausencia de respuesta. |
| Ventana móvil de conectividad | 60 s | Resultados por destino, con aproximadamente 12 intentos en régimen estable. |
| Mínimo para interpretar M-02 | 6 intentos evaluables y cobertura de al menos 80 % | Evitar conclusiones basadas en pocos intentos o recolección incompleta. |
| Mínimo para interpretar el promedio de M-01 | 6 RTT válidos y cobertura de al menos 80 % | El promedio parcial puede mostrarse antes, identificado como insuficiente para clasificar. |
| Intervalo de descubrimiento | 30 s | M-03 y M-04; sin superponer ciclos de una misma fuente. |
| Ausencias consecutivas para M-04 | 3 ciclos completados y comparables | Informar que no fue observado recientemente. |
| Vigencia de sondas | 15 s desde el último resultado evaluable | Vigencia de M-02; para M-01 se utiliza la última respuesta válida. |
| Vigencia del inventario | 90 s desde el último ciclo utilizable | Si la fuente deja de funcionar, el inventario pasa a desactualizado. |
| Lectura de contadores, si existen | 5 s | M-06 a M-08; siempre usar el tiempo real entre lecturas. |
| Retención de observaciones | 10 min en memoria | Ventanas y comparaciones; sin historial entre ejecuciones. |

Las reglas de vigencia y presencia se evaluarán por separado: un inventario actualizado puede informar que un dispositivo no fue observado recientemente. Los ciclos omitidos o fallidos no confirmarán ausencias.

La frecuencia del dashboard no modifica la frecuencia de captura. Los datos vencidos por retención se descartarán y la aplicación volverá a indicar información insuficiente cuando no disponga de las muestras necesarias. Después de un reinicio se iniciarán ventanas nuevas.

## 6. Reglas iniciales de interpretación

| Situación | Condición propuesta | Mensaje o tratamiento |
| --- | --- | --- |
| Primeras mediciones | Muestras por debajo del mínimo definido | «Recopilando datos; resultado preliminar». |
| Recolección incompleta | Cobertura inferior al mínimo o fuente con errores | Informar la calidad de datos; no clasificar la red como saludable. |
| Intentos sin respuesta | S mayor que cero en una ventana utilizable | Informar cuántos intentos no tuvieron respuesta y a qué destino. |
| Cambio de presencia | Condición de M-04 cumplida | Informar primera observación, reaparición o ausencia observada. |
| Datos desactualizados | Antigüedad superior al límite de vigencia | Mostrar último valor con su tiempo y el aviso correspondiente. |
| Latencia elevada | Umbral específico por destino y duración de persistencia, pendientes de calibrar | No habilitar esta etiqueta hasta documentar y probar la regla. |
| Consumo elevado de un dispositivo | Fuente atribuible, tasa o volumen absoluto, participación comparable y persistencia, pendientes de definir | No habilitar esta etiqueta con solo identidad, porcentaje o datos del recolector. |

Los umbrales de latencia y consumo se fijarán después de la prueba piloto y se documentarán por destino o ámbito. No se impondrá un único límite a gateway, equipos locales y destinos externos.

Cada condición conservará la regla aplicada, sus parámetros y las observaciones que la sustentan. Las recomendaciones permanecerán separadas de las modificaciones: ninguna métrica disparará un bloqueo o cambio de configuración sin decisión, autorización y confirmación de la persona.

## 7. Observaciones posteriores a modificaciones

| Operación | Evidencia de verificación |
| --- | --- |
| Cambiar SSID | Consulta posterior del nombre configurado para la red o banda seleccionada. |
| Cambiar contraseña Wi-Fi | Método de comprobación compatible pendiente de investigar, sin registrar ni mostrar la contraseña. |
| Bloquear un dispositivo | Consulta de la restricción aplicada; su efecto sobre la conectividad se observa por separado. |
| Desbloquear un dispositivo | Consulta de la retirada de la regla; no exige que el dispositivo se conecte inmediatamente. |

## 8. Comprobación de cálculos

Los siguientes ejemplos son sintéticos y sirven para verificar la implementación; no son resultados obtenidos en la red de prueba.

| Entrada | Resultado esperado |
| --- | --- |
| RTT válidos de 10, 20 y 30 ms | Promedio de 20 ms con 3 respuestas; todavía insuficiente para la clasificación propuesta. |
| P = 12, R = 9, S = 1 y 2 errores locales | Disponibilidad de 90 % sobre E = 10; cobertura aproximada de 83.33 %; los errores se muestran separados. |
| Ningún intento evaluable | Disponibilidad no disponible, no 0 %. |
| Un ciclo de descubrimiento fallido | No aumenta el contador de ausencias ni convierte el inventario en cero. |
| Incremento de 1 000 000 bytes en 5 s | Volumen de 1 MB y tasa de 1.6 Mbps para esa entidad y dirección. |
| Contador menor que en la lectura anterior sin explicación validada | Intervalo inválido y nueva referencia de contador. |


## 9. Reglas del panel de observaciones

El análisis público utiliza las capturas en memoria de los monitores web y de
conectividad. Consultar `/api/v1/observaciones` no inicia mediciones ni utiliza
la sesión privada del router. Los parámetros de esta sección describen las
reglas implementadas del panel; los valores piloto de la sección 5 no deben
interpretarse como configuración ya aplicada.

| Resultado | Evidencia y criterio |
| --- | --- |
| Orientación principal | Se prioriza un problema de conexión segura, una visita fallida, fallos anteriores a una visita correcta y una búsqueda de nombre fallida. Sin una lectura web vigente no se afirma acceso actual. Una búsqueda de nombre puede explicarse por separado. |
| Búsqueda de nombres | Una única lectura DNS vigente, de menos de 120 s, del contexto activo. Una búsqueda correcta no prueba que la página abra; un fallo no invalida una visita HTTPS correcta. Los destinos de ambas pruebas pueden diferir. |
| Recorrido dentro/fuera de la red | Contextos normalizados iguales, una prueba HTTPS y una serie completa por cada ámbito, todas de menos de 90 s y separadas como máximo 30 s. La coincidencia temporal no atribuye causas. |
| Comparación de pruebas web | Dos ventanas: edades `[0, 300)` y `[300, 600)` s; al menos tres intentos evaluables por ventana, del mismo contexto y destino, con identificadores únicos. Compara proporciones de intentos no correctos, no duración de una caída. |
| Comparación de tiempos de respuesta | Las mismas ventanas, separadas por destino del monitor de conectividad. Exige tres series, seis respuestas y al menos 80 % de intentos evaluables sobre programados en cada ventana. Promedio ponderado por número de respuestas; los silencios no tienen RTT. Se exige una serie actual vigente de menos de 90 s. |
| Problemas repetidos | Dos o más intentos HTTPS no correctos en los últimos diez minutos, del mismo contexto y destino y con identificadores únicos. No implica fallos consecutivos ni una interrupción continua. |
| Respuesta posterior | Lectura HTTPS actual correcta y al menos un intento fallido estrictamente anterior por edad continua. Se informa que el sitio respondió después; no se declara recuperación definitiva. |
| Evidencia reciente | Intentos ordenados por edad continua, mostrando fecha y destino. Los errores de medición se identifican aparte y no cuentan como fallos de Internet. No se rellenan huecos. |

Una diferencia entre promedios describe las muestras recibidas; no clasifica la
red como sana, saturada o averiada ni mide capacidad de descarga. Si faltan datos,
la comparación permanece no disponible. Al caducar la fuente o fallar la consulta
de la API, la interfaz no presenta sus conclusiones anteriores como actuales.

Las recomendaciones son pasos manuales de comprobación. No cambian DNS, Wi-Fi,
router ni permisos. Relacionar consumo con problemas requiere evidencia de tráfico
autorizada, periodos compatibles y reglas adicionales; estas observaciones públicas
no identifican qué dispositivo consume más ni causan operaciones administrativas.


## 10. Cantidades observadas en conexiones del router

El resumen autorizado de tráfico ofrece ventanas de 60, 300 y 600 segundos,
calculadas con el reloj continuo. Para cada fuente, familia IP e interfaz suma
las diferencias de bytes de intervalos comparables completos dentro de la ventana.
No reparte proporcionalmente un intervalo que cruce su comienzo. Las cantidades
exactas se entregan como cadenas de bytes; MB usa 1.000.000 de bytes.

Un intervalo requiere dos lecturas separadas por más de cero y como máximo 20
segundos, sin descenso de ninguno de los contadores. El inicio, los reinicios,
las pausas y los fallos de lectura no aportan una cantidad estimada. Sin intervalos
válidos, la cantidad es `null`; con intervalos válidos sin incremento, es cero.

Cada resumen informa segundos medidos, segundos del periodo sin medición
utilizable, intervalos válidos y puntos excluidos. El tiempo sin medición incluye
el anterior al inicio del recolector: no equivale a tiempo sin Internet. La fecha
de la última lectura se conserva aunque falle la siguiente consulta.

El selector de periodo controla las cantidades y las gráficas del router. Cada
punto de tasa se sitúa al final de su intervalo; puede aparecer junto al inicio
de una ventana sin contribuir a su suma, si parte del intervalo queda fuera.
La elección de subida o bajada en la gráfica no modifica el total de ambas
mostrado en las tarjetas. La consulta no genera nuevas lecturas del router.

No se agregan interfaces ni familias IP entre sí mientras no esté comprobado su
alcance. Tampoco se atribuyen estos datos a dispositivos. Todos estos resúmenes
requieren la misma autorización temporal que las tablas y series del router;
el Invitado no los recibe. Solo el periodo elegido se guarda como preferencia.
