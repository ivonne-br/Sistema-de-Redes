<!-- Consulta series ICMP mediante api.js/useResumen; resume respuestas y RTT, con métricas e historial desplegables calculados por Python y fallos separados. -->
<script setup>
import { computed } from 'vue'
import { consultarConectividad } from '../api.js'
import { useResumen } from '../useResumen.js'

const { respuesta, error, cargando, recuperada } = useResumen(consultarConectividad)
const datos = computed(() => respuesta.value?.datos)
const historial = computed(() => [...(datos.value?.historial ?? [])].reverse().flatMap(serie =>
  serie.destinos.map(fila => ({ ...fila, clave: `${serie.id_serie}-${fila.tipo}-${fila.ipv4}` }))))
const estados = { esperando_contexto: 'Esperando contexto de red', sin_contexto: 'Contexto de red no disponible',
  midiendo: 'Medición en curso', en_espera: 'Esperando la siguiente serie', detenido: 'Medición detenida',
  desactivada: 'Medición desactivada', error: 'Fallo del monitor' }
const calidades = { completa: 'Serie completa', parcial: 'Serie parcial', no_disponible: 'Sin medición utilizable' }
function numero(valor, unidad = '') { return valor == null ? 'No disponible' : `${valor}${unidad}` }
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'No disponible' }
function edad(valor) { return valor == null ? 'No disponible' : `${valor.toFixed(1)} s` }
</script>

<template>
  <section aria-labelledby="conectividad">
    <h2 id="conectividad">¿Cuánto tarda en responder?</h2>
    <p>Es el tiempo que tarda un mensaje pequeño en ir y volver. Un tiempo menor significa una respuesta más rápida; no indica cuántos archivos puedes descargar.</p>
    <p v-if="datos && !datos.destinos.length">Esperando una serie de mediciones del contexto actual.</p>
    <div v-for="destino in (datos?.destinos ?? [])" :key="destino.tipo" class="resumen-destino">
      <strong>{{ destino.tipo === 'router' ? 'Hasta tu router (dentro de tu red)' : 'Hasta Internet (sitio de prueba)' }}</strong>
      <p v-if="error || destino.vigencia !== 'vigente'">Sin medición reciente disponible.</p>
      <template v-else>
        <p>Tiempo promedio: <strong>{{ numero(destino.rtt_ms.promedio, ' ms') }}</strong>. Un milisegundo (ms) es una milésima de segundo.</p>
        <p>{{ destino.respuestas }} respuestas de {{ destino.realizadas }} intentos. {{ destino.sin_respuesta }} sin respuesta.</p>
        <p v-if="destino.errores || destino.omitidas">La medición quedó incompleta; no podemos evaluar todos los intentos.</p>
        <p v-else-if="destino.sin_respuesta">Algunos mensajes no recibieron respuesta. Si notas cortes, revisa si vuelve a ocurrir; esta prueba por sí sola no confirma una desconexión.</p>
      </template>
      <p class="secundario">Última serie: {{ fecha(destino.fin) }}. {{ error ? 'Sin actualizar' : destino.vigencia === 'vigente' ? 'Reciente' : 'Antigua' }}.</p>
    </div>
    <div role="status" aria-live="polite">
      <p v-if="cargando">Cargando mediciones de conectividad…</p>
      <details v-else-if="error"><summary>No llegan nuevas mediciones. Ver detalle</summary><p>{{ error }} Se reintentará automáticamente. Los resultados conservados y sus antigüedades están congelados; no describen el momento actual.</p></details>
      <p v-else-if="recuperada">Consulta de conectividad recuperada.</p>
    </div>
    <details v-if="datos"><summary>Ver sondas, errores y evolución ICMP</summary>
      <p>Comparamos el recorrido local hasta el router con el recorrido hasta <code>1.1.1.1</code> en Internet mediante ping (ICMP). No es una prueba de velocidad del Wi-Fi.</p>
      <p><strong>{{ estados[datos.estado] ?? datos.estado }}</strong><span v-if="datos.estado === 'midiendo'"> · {{ datos.rondas_completadas }} de {{ datos.muestras_por_serie }} rondas terminadas</span></p>
      <p v-if="datos.detalle" class="aviso">{{ datos.detalle }}</p>
      <p v-if="!datos.destinos.length">Sin series conservadas para este contexto. No equivale a cero pérdidas.</p>
      <article v-for="destino in datos.destinos" :key="`${datos.id_contexto}-${destino.tipo}-${destino.ipv4}`" class="medicion">
        <h3>{{ destino.tipo === 'router' ? 'Router · recorrido local' : 'Destino externo · recorrido hacia Internet' }} · {{ destino.ipv4 ?? 'IPv4 no disponible' }}</h3>
        <p><strong>{{ calidades[destino.calidad] }}</strong> · {{ error ? 'Dato conservado sin actualizar' : destino.vigencia === 'desactualizado' ? 'Dato antiguo' : 'Dato dentro de vigencia' }}</p>
        <p v-if="destino.omision">{{ destino.omision }}</p>
        <dl class="indicadores">
          <div><dt>Respuestas / sondas realizadas</dt><dd>{{ destino.respuestas }} / {{ destino.realizadas }}</dd></div>
          <div><dt>Sondas sin respuesta</dt><dd>{{ destino.sin_respuesta }}</dd></div>
          <div><dt>Porcentaje sin respuesta ICMP</dt><dd>{{ numero(destino.perdida_observada_pct, ' %') }}</dd></div>
          <div><dt>Errores de medición / omitidas</dt><dd>{{ destino.errores }} / {{ destino.omitidas }}</dd></div>
          <div><dt>Ida y vuelta promedio (RTT)</dt><dd>{{ numero(destino.rtt_ms.promedio, ' ms') }}</dd></div>
          <div><dt>RTT mínimo / máximo</dt><dd>{{ numero(destino.rtt_ms.minimo, ' ms') }} / {{ numero(destino.rtt_ms.maximo, ' ms') }}</dd></div>
        </dl>
        <p class="secundario">Serie: {{ fecha(destino.inicio) }} → {{ fecha(destino.fin) }}. Antigüedad al consultar: {{ edad(destino.antiguedad_s) }}. RTT calculado con {{ destino.rtt_ms.muestras }} respuestas.</p>
        <p v-if="destino.calidad !== 'completa'" class="aviso">Hay errores u omisiones: el porcentaje no está disponible. Los tiempos corresponden únicamente a las respuestas válidas obtenidas.</p>
        <p v-if="destino.anterior_completa" class="aviso">Última serie completa anterior: {{ fecha(destino.anterior_completa.fin) }}; antigüedad {{ edad(destino.anterior_completa.antiguedad_s) }}. Sin respuesta: {{ numero(destino.anterior_completa.perdida_observada_pct, ' %') }}; RTT promedio: {{ numero(destino.anterior_completa.rtt_ms.promedio, ' ms') }}. Es un dato anterior, no sustituye el resultado del último intento.</p>
      </article>
      <div class="resumen-icmp" v-if="datos.resumen_ventana?.length">
        <h3>¿Qué ocurrió en las series conservadas?</h3>
        <p>Recuentos calculados por Python para este contexto. Se actualizan al llegar series y al expirar la memoria; no representan todo el tiempo transcurrido.</p>
        <p v-if="error" class="aviso">Resumen conservado sin actualizar mientras la API no responde.</p>
        <article v-for="grupo in datos.resumen_ventana" :key="`${grupo.tipo}-${grupo.destino}`">
          <h4>{{ grupo.tipo === 'router' ? 'Router' : 'Externo' }} · {{ grupo.destino ?? 'IPv4 no disponible' }}</h4>
          <p>{{ grupo.series }} series; {{ grupo.respuestas }} respuestas de {{ grupo.realizadas }} sondas realizadas ({{ grupo.programadas }} programadas).</p>
          <p>{{ grupo.sin_respuesta }} solicitudes sin respuesta, repartidas en {{ grupo.series_con_silencios }} series. Errores: {{ grupo.errores }}. Omitidas: {{ grupo.omitidas }}. Series con errores u omisiones: {{ grupo.series_con_errores_u_omisiones }}.</p>
          <p>{{ grupo.series_sin_incidencias }} series con todas las respuestas y sin errores ni omisiones.</p>
          <p v-if="grupo.respuesta_completa_posterior">Hubo incidencias anteriores y la última serie conservada obtuvo todas sus respuestas. Esto no garantiza que el problema haya desaparecido.</p>
          <p class="secundario">Finales de serie incluidos: {{ fecha(grupo.primer_fin) }} → {{ fecha(grupo.ultimo_fin) }}. Una misma serie puede tener silencios y errores; esos recuentos no se suman como series distintas.</p>
        </article>
      </div>
      <details class="historial-icmp">
        <summary>¿Se repiten las solicitudes sin respuesta? Ver evolución ICMP</summary>
        <p>Series del contexto actual, de la más reciente a la más antigua. Se conservan hasta {{ datos.capacidad_series ?? '—' }} series y {{ datos.retencion_s ?? '—' }} segundos. Reiniciar Python borra esta memoria.</p>
        <p v-if="error" class="aviso">Historial conservado sin actualizar mientras la API no responde.</p>
        <p v-if="!historial.length">Todavía no hay series conservadas en esta ventana.</p>
        <div v-else class="tabla" tabindex="0" role="region" aria-label="Evolución ICMP; tabla desplazable">
          <table>
            <caption>Una fila por destino y serie. Los errores y omisiones se muestran separados de las solicitudes sin respuesta.</caption>
            <thead><tr><th scope="col">Fin</th><th scope="col">Destino</th><th scope="col">Serie</th><th scope="col">Respuestas / realizadas</th><th scope="col">Sin respuesta</th><th scope="col">Errores / omitidas</th><th scope="col">RTT promedio</th></tr></thead>
            <tbody><tr v-for="fila in historial" :key="fila.clave">
              <td>{{ fecha(fila.fin) }}</td><td>{{ fila.tipo === 'router' ? 'Router' : 'Externo' }} · {{ fila.ipv4 ?? 'No disponible' }}</td>
              <td>{{ calidades[fila.calidad] ?? fila.calidad }}</td><td>{{ fila.respuestas }} / {{ fila.realizadas }}</td><td>{{ fila.sin_respuesta }}</td>
              <td>{{ fila.errores }} / {{ fila.omitidas }}</td><td>{{ numero(fila.rtt_ms.promedio, ' ms') }}</td>
            </tr></tbody>
          </table>
        </div>
        <p>Una fila representa una serie medida, no todo el tiempo entre dos filas. Los periodos sin medición no se rellenan con ceros. Al cambiar de contexto comienza otra ventana visible, incluso al volver a la misma red.</p>
      </details>
      <p v-if="datos.muestras_por_serie" class="secundario">{{ datos.muestras_por_serie }} sondas por destino y serie, con una pausa de 1 segundo entre rondas. La siguiente serie comienza {{ datos.intervalo_s }} segundos después de terminar. Vigencia: {{ datos.vigencia_s }} segundos. La vista consulta cada 5 segundos.</p>
    </details>
    <details><summary>Cómo interpretar estas mediciones</summary>
      <p>RTT es el tiempo que tarda una solicitud en ir y su respuesta en volver. El porcentaje cuenta solicitudes sin respuesta dentro del plazo entre las sondas de una serie completa. Con 5 sondas, cada una representa 20 puntos porcentuales: es una muestra pequeña.</p>
      <p>Una falta de respuesta puede deberse a pérdida, filtrado o baja prioridad de ICMP. No demuestra por sí sola desconexión ni pérdida de todos los tipos de tráfico. Si el router responde y el destino externo no, sabemos que el recorrido local respondió, pero aún debemos investigar el recorrido externo.</p>
      <p>Las mediciones parten de esta computadora, por su ruta de red. No describen la conexión de todos los teléfonos ni distinguen por sí solas un problema de radio Wi‑Fi.</p>
    </details>
  </section>
</template>
