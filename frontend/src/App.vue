<!-- Presenta estado y diagnóstico ARP desde la API existente; no inicia sondas ni calcula métricas. diagnostico=1 muestra ARP técnico, no es autorización. -->
<script setup>
import { computed } from 'vue'
import { useResumen } from './useResumen.js'
import MemoriaArp from './components/MemoriaArp.vue'

const { respuesta, error, cargando, recuperada, recibida } = useResumen()
const datos = computed(() => respuesta.value?.datos)
const mostrarDiagnostico = new URLSearchParams(window.location.search).get('diagnostico') === '1'
const calidad = computed(() => datos.value?.calidad)
const etiquetas = { completa: 'Lectura ARP sin errores de interpretación', parcial: 'Lectura parcial', error_fuente: 'Fallo o falta de datos de la fuente', no_disponible: 'Sin observaciones' }
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'No disponible' }
function numero(valor) { return valor ?? 'No disponible' }
</script>

<template>
  <main>
    <header><p class="ceja">Consulta como invitado · instalación local</p><h1>Observación de red local</h1>
      <p>Consulta del servicio local y de la calidad de sus observaciones. La caché ARP no es una lista de equipos conectados ni una medida del rendimiento de la red.</p>
    </header>
    <div role="status" aria-live="polite" class="aviso">
      <p v-if="cargando">Cargando la primera consulta…</p>
      <template v-else-if="error"><strong>API inaccesible o respuesta no utilizable</strong><p>{{ error }} Se reintentará automáticamente.</p>
        <p v-if="respuesta">Se conserva la última respuesta recibida el {{ fecha(recibida) }}. Sus estados y antigüedades están congelados: no describen el momento actual.</p>
      </template>
      <p v-else-if="recuperada">Comunicación con la API recuperada. Ya se muestra una nueva respuesta.</p>
      <p v-else>API accesible. Una consulta correcta no significa que la red esté saludable.</p>
    </div>
    <template v-if="datos">
      <section aria-labelledby="estado"><h2 id="estado">¿Están disponibles el servicio y los datos?</h2>
        <dl class="indicadores">
          <div><dt>Monitoreo</dt><dd>{{ respuesta.monitoreo.estado }}</dd></div>
          <div><dt>Último intento de lectura</dt><dd>{{ etiquetas[calidad.calidad_fuente] ?? calidad.calidad_fuente }}</dd></div>
          <div><dt>Última captura utilizable</dt><dd>{{ fecha(datos.vecinos.fin_captura) }}</dd></div>
          <div><dt>Antigüedad al consultar</dt><dd>{{ calidad.antiguedad_s == null ? 'No disponible' : `${calidad.antiguedad_s.toFixed(1)} s` }}</dd></div>
        </dl>
        <p v-if="respuesta.monitoreo.error" class="aviso">{{ respuesta.monitoreo.error }}</p>
        <p v-if="calidad.calidad_fuente === 'no_disponible'">Sin observaciones en la memoria disponible. No equivale a cero vecinos.</p>
        <p v-if="calidad.calidad_fuente === 'parcial'" class="aviso">Lectura parcial: solo hay evidencia de las filas interpretables; no confirma ausencias.</p>
        <p v-if="calidad.calidad_fuente === 'error_fuente'" class="aviso">El último intento no aportó una lectura utilizable ({{ calidad.estado_ultimo_intento }}).
          <span v-if="calidad.id_ultima_utilizable">Se muestra el dato anterior, conservando su fecha.</span>
        </p>
        <p v-if="calidad.estado_ultimo_intento === 'sin_datos_visibles'">macOS devolvió cero bytes. No se puede distinguir caché vacía de visibilidad restringida; no se presenta como una red vacía.</p>
        <p v-if="calidad.vigencia === 'desactualizado'" class="aviso">Dato antiguo: superó la vigencia de {{ calidad.vigencia_s }} segundos.</p>
        <p v-if="calidad.estado_ultima_utilizable === 'observacion_parcial'">El dato conservado procede de una lectura parcial.</p>
        <p class="contexto">Contexto: <code>{{ calidad.id_contexto ?? 'No disponible' }}</code>. Cada tramo se mantiene separado, incluso al volver a una red anterior.</p>
        <p class="secundario">Respuesta recibida: {{ fecha(recibida) }}. Actualización: 5 segundos después de terminar cada consulta. La antigüedad la calcula Python.</p>
      </section>
      <details v-if="mostrarDiagnostico" class="diagnostico">
      <summary>Diagnóstico: caché ARP y eventos de la memoria (no es una lista de equipos conectados)</summary>
      <p>Este detalle conserva observaciones para investigar cambios. Reiniciar Vue vuelve a consultar la misma memoria de Python; la caché de macOS también tiene su propio ciclo de vida.</p>
      <section aria-labelledby="vecinos"><h2 id="vecinos">¿Cuántas filas son vecinos candidatos?</h2>
        <dl class="indicadores">
          <div><dt>Filas de vecinos candidatos</dt><dd>{{ numero(datos.vecinos.cantidad) }}</dd></div>
          <div><dt>Con MAC resuelta</dt><dd>{{ numero(datos.vecinos.resolucion_mac?.resuelta) }}</dd></div>
          <div><dt>Con MAC incompleta</dt><dd>{{ numero(datos.vecinos.resolucion_mac?.incompleta) }}</dd></div>
        </dl>
        <p>Se cuentan filas, incluidas las incompletas. La tabla de asociaciones deduplica IPv4–MAC resueltas: ambos recuentos pueden diferir. «No disponible» nunca significa cero.</p>
      </section>
      <MemoriaArp :presencia="datos.presencia" />
      </details>
    </template>
    <footer>Los resultados se conservan temporalmente en Python. Reiniciar la vista no reinicia el monitoreo. No hay historial persistente.</footer>
  </main>
</template>
