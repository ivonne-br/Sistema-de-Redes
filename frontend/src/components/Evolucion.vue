<!-- Visualiza series ya calculadas: recibe edades, valores, fechas y unidad común.
     No consulta fuentes ni calcula tasas. Comparte filtros y tabla accesible entre
     conectividad y router; guarda solo periodo y presentación, nunca datos o destinos. -->
<script setup>
import { computed, ref, watch } from 'vue'
const props = defineProps({ series: { type: Array, required: true }, unidad: { type: String, required: true },
  titulo: { type: String, required: true }, preferencia: { type: String, required: true },
  periodo: { type: Number, default: null }, hueco: { type: Number, default: 90 } })
const emit = defineEmits(['update:periodo'])
const clave = `red-grafica-${props.preferencia}-v1`
function leer() {
  try { const p = JSON.parse(localStorage.getItem(clave)); return {
    periodo: [60, 300, 600].includes(p?.periodo) ? p.periodo : 300,
    vista: ['grafica', 'valores', 'tabla'].includes(p?.vista) ? p.vista : 'grafica' } }
  catch { return { periodo: 300, vista: 'grafica' } }
}
const ajustes = ref(leer()), seleccion = ref(''), aviso = ref('')
// Si el padre controla el periodo, comparte el mismo límite con las cantidades.
const periodoVisible = computed({
  get: () => props.periodo ?? ajustes.value.periodo,
  set: valor => { ajustes.value.periodo = valor; emit('update:periodo', valor) }
})
function restablecer() { ajustes.value.vista = 'grafica'; periodoVisible.value = 300; seleccion.value = '' }
watch(ajustes, p => {
  try { localStorage.setItem(clave, JSON.stringify({ periodo: p.periodo, vista: p.vista })) }
  catch { aviso.value = 'Los filtros funcionan, pero este navegador no permite guardarlos.' }
}, { deep: true })
watch(() => props.series.map(s => s.id), ids => { if (!ids.includes(seleccion.value)) seleccion.value = '' })
const grupos = computed(() => props.series.filter(s => !seleccion.value || s.id === seleccion.value).map(s => ({ ...s,
  puntos: s.puntos.filter(p => Number.isFinite(p.edad) && p.edad >= 0 && p.edad < periodoVisible.value)
    .map(p => ({ ...p, valor: Number.isFinite(p.valor) && p.valor >= 0 ? p.valor : null }))
    .sort((a, b) => b.edad - a.edad) })))
const maximo = computed(() => Math.max(1, ...grupos.value.flatMap(s => s.puntos.map(p => p.valor ?? 0))))
const x = p => 40 + (1 - p.edad / periodoVisible.value) * 540
const y = p => 170 - p.valor / maximo.value * 140
const colores = ['#2166ac', '#a34500', '#396b36', '#70469c']
function segmentos(puntos) {
  return puntos.slice(1).flatMap((p, i) => {
    const a = puntos[i], distancia = a.edad - p.edad
    return a.valor != null && p.valor != null && distancia > 0 && distancia <= props.hueco
      ? [{ x1: x(a), y1: y(a), x2: x(p), y2: y(p) }] : []
  })
}
const hayValores = computed(() => grupos.value.some(s => s.puntos.some(p => p.valor != null)))
const fecha = f => f ? new Date(f).toLocaleString('es-MX') : 'Sin fecha'
const valor = v => v == null ? 'No disponible' : `${v.toLocaleString('es-MX', { maximumFractionDigits: 3 })} ${props.unidad}`
</script>
<template>
  <div class="evolucion">
    <h3>{{ titulo }}</h3>
    <div class="filtros-grafica">
      <label>Periodo <select v-model="periodoVisible"><option :value="60">Último minuto</option><option :value="300">Últimos 5 minutos</option><option :value="600">Últimos 10 minutos</option></select></label>
      <label>Qué ver <select v-model="seleccion"><option value="">Todas las series</option><option v-for="s in series" :key="s.id" :value="s.id">{{ s.nombre }}</option></select></label>
      <label>Presentación <select v-model="ajustes.vista"><option value="grafica">Gráfica</option><option value="valores">Últimos valores</option><option value="tabla">Tabla</option></select></label>
      <button type="button" @click="restablecer">Restablecer gráfica</button>
    </div>
    <p v-if="aviso" role="status">{{ aviso }}</p>
    <p>Periodo contado al consultar la fuente. Los espacios sin mediciones no significan cero. Los filtros no cambian las mediciones.</p>
    <p v-if="!hayValores" role="status">No hay valores disponibles en este periodo. Prueba un periodo más amplio o espera nuevas mediciones.</p>
    <template v-if="ajustes.vista === 'grafica' && hayValores">
      <svg viewBox="0 0 620 210" role="img" :aria-label="`${titulo}; últimos ${periodoVisible / 60} minutos. Valores exactos disponibles en la presentación Tabla.`">
        <line x1="40" y1="170" x2="580" y2="170" stroke="gray" />
        <text x="40" y="20">{{ valor(maximo) }}</text><text x="8" y="175">0</text>
        <g v-for="(s, i) in grupos" :key="s.id" :stroke="colores[i % colores.length]">
          <line v-for="(linea, j) in segmentos(s.puntos)" :key="j" v-bind="linea" stroke-width="2" :stroke-dasharray="i % 2 ? '6 3' : undefined" />
          <template v-for="(p, j) in s.puntos" :key="`p${j}`"><circle v-if="p.valor != null" :cx="x(p)" :cy="y(p)" r="3" :fill="colores[i % colores.length]"><title>{{ s.nombre }} · {{ fecha(p.fecha) }} · {{ valor(p.valor) }}</title></circle></template>
        </g>
        <text x="40" y="200">Hace {{ periodoVisible / 60 }} min</text><text x="485" y="200">Al consultar</text>
      </svg>
      <ul><li v-for="(s, i) in grupos" :key="s.id"><span :style="{ color: colores[i % colores.length] }">●</span> {{ s.nombre }} · {{ i % 2 ? 'línea discontinua' : 'línea continua' }}</li></ul>
    </template>
    <dl v-if="ajustes.vista === 'valores'" class="indicadores">
      <div v-for="s in grupos" :key="s.id"><dt>{{ s.nombre }}</dt><dd>{{ valor(s.puntos.at(-1)?.valor) }}</dd><p v-if="s.puntos.length">{{ fecha(s.puntos.at(-1).fecha) }} · hace {{ Math.round(s.puntos.at(-1).edad) }} s al consultar.</p></div>
    </dl>
    <div v-if="ajustes.vista === 'tabla'" class="tabla" tabindex="0" role="region" :aria-label="`Valores de ${titulo}`">
      <table><caption>{{ titulo }} · {{ unidad }} · cada fila corresponde a una medición</caption><thead><tr><th scope="col">Serie</th><th scope="col">Fecha</th><th scope="col">Valor</th></tr></thead><tbody>
        <template v-for="s in grupos" :key="s.id"><tr v-for="(p, i) in [...s.puntos].reverse()" :key="i"><td>{{ s.nombre }}</td><td>{{ fecha(p.fecha) }}</td><td>{{ valor(p.valor) }}</td></tr></template>
      </tbody></table>
    </div>
  </div>
</template>
