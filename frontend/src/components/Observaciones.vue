<!-- Presenta explicaciones del análisis Python con evidencia opcional.
     Entrada: API pública mediante useResumen. Salida: hechos y pasos sencillos;
     prioriza una orientación, despliega evidencia y oculta las conclusiones anteriores si falla la actualización, sin acceder al router. -->
<script setup>
import { computed } from 'vue'
import { consultarObservaciones } from '../api.js'
import { useResumen } from '../useResumen.js'
const { respuesta, error, cargando } = useResumen(consultarObservaciones)
const datos = computed(() => respuesta.value?.datos)
const principal = computed(() => datos.value?.principal ?? datos.value)
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'Sin fecha disponible' }
</script>
<template>
  <section aria-labelledby="observaciones">
    <h2 id="observaciones">Qué está pasando y qué puedes hacer</h2>
    <p v-if="cargando">Estamos esperando las primeras comprobaciones.</p>
    <div v-else-if="error" role="status">
      <p>No están llegando nuevos resultados. Por ahora no podemos decir cómo está tu conexión.</p>
      <p>No cambies la configuración de tu red basándote en información anterior.</p>
      <details><summary>Ver el problema de la aplicación</summary><p>{{ error }}</p></details>
    </div>
    <template v-else-if="datos">
      <p class="resultado-principal">{{ principal.titulo }}</p>
      <p>{{ principal.explicacion }}</p>
      <h3>Qué puedes intentar</h3><p>{{ principal.orientacion }}</p>
      <p v-if="principal.fecha || datos.ultima_comprobacion" class="secundario">Comprobado: {{ fecha(principal.fecha || datos.ultima_comprobacion) }}<span v-if="principal.fuente"> · {{ principal.fuente }}</span></p>
      <div v-if="datos.diagnostico">
        <h3>Qué encontramos</h3>
        <ul><li v-for="(hallazgo, i) in datos.diagnostico.hallazgos" :key="i">{{ hallazgo }}</li></ul>
        <h3>Cómo comprobar si mejora</h3><p>{{ datos.diagnostico.comprobar }}</p>
        <h3>Qué falta comprobar</h3><p>{{ datos.diagnostico.falta }}</p>
      </div>
      <div v-if="datos.incidencias?.estado === 'observado'">
        <h3>¿Ha ocurrido más de una vez?</h3>
        <p>{{ datos.incidencias.mensaje }}</p>
        <details><summary>Ver qué pasó en los últimos diez minutos</summary>
          <p>Primero aparece lo más reciente. Son comprobaciones puntuales: no indican cuánto duró un problema. Los momentos sin pruebas quedan sin información.</p>
          <p v-if="datos.incidencias.errores_medicion">También hubo {{ datos.incidencias.errores_medicion }} pruebas que la aplicación no pudo realizar. No se cuentan como fallos de Internet.</p>
          <ol><li v-for="evento in datos.incidencias.eventos" :key="evento.id">{{ fecha(evento.fecha) }} · {{ evento.descripcion }} <span class="secundario">Destino: {{ evento.destino }}</span></li></ol>
        </details>
      </div>
      <details>
        <summary>Entender las pruebas y comparar los últimos minutos</summary>
        <div v-if="datos.nombres">
          <h3>¿Se pudo encontrar el sitio por su nombre?</h3>
          <p>{{ datos.nombres.titulo }}</p><p>{{ datos.nombres.explicacion }}</p><p>{{ datos.nombres.orientacion }}</p>
          <p v-if="datos.nombres.fecha" class="secundario">{{ fecha(datos.nombres.fecha) }} · Nombre consultado: {{ datos.nombres.destino }}</p>
        </div>
      <div v-if="datos.recorrido" class="orientacion-recorrido">
        <h3>¿Dónde puedo empezar a revisar?</h3>
        <p><strong>{{ datos.recorrido.titulo }}</strong></p>
        <p>{{ datos.recorrido.explicacion }}</p>
        <p>{{ datos.recorrido.orientacion }}</p>
        <details v-if="datos.recorrido.evidencia.length"><summary>Ver las comprobaciones que usamos</summary>
          <ul><li v-for="fila in datos.recorrido.evidencia" :key="fila.nombre">{{ fila.nombre }}: {{ fila.respuestas }} respuestas de {{ fila.intentos }} intentos. {{ fecha(fila.fecha) }}.</li></ul>
          <p>Son comprobaciones realizadas en momentos cercanos desde esta computadora. Un mensaje sin respuesta no confirma una desconexión. No identifican qué dispositivo consume más Internet.</p>
        </details>
      </div>
      <div v-if="datos.comparacion">
        <h3>¿Ha cambiado en los últimos minutos?</h3>
        <p>{{ datos.comparacion.mensaje }}</p>
        <details><summary>Ver en qué nos basamos</summary>
          <p>Últimos cinco minutos: {{ datos.comparacion.reciente.no_correctos }} comprobaciones con problemas de {{ datos.comparacion.reciente.intentos }} realizadas.</p>
          <p>Cinco minutos anteriores: {{ datos.comparacion.anterior.no_correctos }} con problemas de {{ datos.comparacion.anterior.intentos }} realizadas.</p>
          <p>Se necesitan al menos tres comprobaciones utilizables en cada periodo. Los momentos sin comprobaciones no cuentan como aciertos ni como fallos. Esto no mide cuánto tiempo estuviste sin Internet.</p>
          <ul><li v-for="(fila, i) in datos.evidencia" :key="i">{{ fecha(fila.fecha) }} · {{ fila.resultado === 'correcto' ? 'El sitio respondió correctamente' : 'La comprobación no terminó correctamente' }} · {{ fila.destino }}</li></ul>
        </details>
      </div>
      <div v-if="datos.tiempos_respuesta?.length">
        <h3>¿Está tardando más en responder?</h3>
        <p>Es el tiempo que tarda un mensaje de prueba en ir y volver. Menos tiempo significa menos espera en esa prueba. No mide la rapidez de tus descargas.</p>
        <div v-for="fila in datos.tiempos_respuesta" :key="fila.destino + fila.nombre" class="resumen-destino">
          <h4>{{ fila.nombre }}</h4>
          <p>{{ fila.mensaje }}</p>
          <dl v-if="fila.estado === 'comparable'" class="indicadores">
            <div><dt>Cinco minutos anteriores</dt><dd>{{ fila.anterior.promedio_ms }} ms</dd></div>
            <div><dt>Últimos cinco minutos</dt><dd>{{ fila.reciente.promedio_ms }} ms</dd></div>
          </dl>
          <p v-if="fila.estado === 'comparable'">«ms» significa milisegundos: 1.000 ms equivalen a un segundo. Una diferencia pequeña puede no notarse al usar Internet.</p>
          <p>{{ fila.orientacion }}</p>
          <details><summary>Ver de dónde sale esta comparación</summary>
            <p>Destino probado: {{ fila.destino }}. Última comprobación: {{ fecha(fila.ultima_comprobacion) }}.</p>
            <template v-for="periodo in ['anterior', 'reciente']" :key="periodo">
              <p v-if="fila[periodo]">{{ periodo === 'anterior' ? 'Cinco minutos anteriores' : 'Últimos cinco minutos' }}:
                {{ fila[periodo].respuestas }} respuestas y {{ fila[periodo].sin_respuesta }} mensajes sin respuesta.
                Tiempo promedio: {{ fila[periodo].promedio_ms == null ? 'No disponible' : `${fila[periodo].promedio_ms} ms` }}.
              </p>
            </template>
            <p>Solo calculamos tiempos con las respuestas recibidas. Los mensajes sin respuesta no cuentan como cero. Se necesitan tres grupos de pruebas y seis respuestas por periodo, y al menos ocho de cada diez intentos previstos deben haberse podido comprobar. Los periodos sin mediciones quedan sin datos.</p>
          </details>
        </div>
      </div>
      </details>
      <p class="secundario">{{ datos.limite }}</p>
    </template>
  </section>
</template>
