<!-- Organiza paneles recibidos como slots, sin consultar datos ni manejar sesiones.
     Entrada: catálogo de identificadores/títulos. Salida: orden, ancho, altura, navegación y visibilidad;
     guarda solo esas preferencias en el navegador y mantiene los componentes montados. -->
<script setup>
import { computed, nextTick, ref, watch } from 'vue'
const props = defineProps({ catalogo: { type: Array, required: true }, vistas: { type: Array, default: () => [] } })
const almacenamiento = 'red-paneles-v1'
const inicial = () => props.catalogo.map(p => ({ id: p.id, visible: true, ancho: p.ancho ?? 'medio', alto: 'automatico' }))
const mensaje = ref(''), editando = ref(false)
function leer() {
  try {
    const dato = JSON.parse(localStorage.getItem(almacenamiento))
    if (!Array.isArray(dato)
      || new Set(dato.map(p => p?.id)).size !== dato.length
      || dato.some(p => typeof p?.id !== 'string' || typeof p.visible !== 'boolean'
        || !['medio', 'completo'].includes(p.ancho)
        || (p.alto !== undefined && !['automatico', 'compacto', 'amplio'].includes(p.alto)))) return inicial()
    const conservados = dato.filter(p => props.catalogo.some(c => c.id === p.id))
      .map(({ id, visible, ancho, alto }) => ({ id, visible, ancho, alto: alto ?? 'automatico' }))
    return [...conservados, ...inicial().filter(p => !conservados.some(c => c.id === p.id))]
  } catch { return inicial() }
}
const paneles = ref(leer())
const visibles = computed(() => paneles.value.filter(p => p.visible))
const titulo = id => props.catalogo.find(p => p.id === id)?.titulo
watch(paneles, valor => {
  try { localStorage.setItem(almacenamiento, JSON.stringify(valor.map(({ id, visible, ancho, alto }) => ({ id, visible, ancho, alto })))) }
  catch { mensaje.value = 'La distribución se aplica, pero el navegador no permite guardarla.' }
}, { deep: true })
function mover(id, destino) {
  const desde = paneles.value.findIndex(p => p.id === id)
  const hasta = paneles.value.findIndex(p => p.id === destino)
  if (desde < 0 || hasta < 0 || desde === hasta) return
  const [panel] = paneles.value.splice(desde, 1)
  paneles.value.splice(hasta, 0, panel)
  mensaje.value = `${titulo(id)} cambió de posición.`
}
function desplazar(id, paso) {
  const indice = visibles.value.findIndex(p => p.id === id)
  mover(id, visibles.value[indice + paso]?.id)
}
let arrastrado = null
function iniciar(evento, id) {
  arrastrado = id
  evento.dataTransfer?.setData('text/plain', id)
  if (evento.dataTransfer) evento.dataTransfer.effectAllowed = 'move'
}
function soltar(id) { if (editando.value && arrastrado) mover(arrastrado, id); arrastrado = null }
function aplicarVista(vista) {
  paneles.value = paneles.value.map(p => ({ ...p, visible: vista.paneles.includes(p.id) }))
  mensaje.value = `Vista «${vista.titulo}» aplicada. Conservamos el orden y los tamaños.`
}
async function ir(id) {
  const panel = paneles.value.find(p => p.id === id)
  if (!panel) return
  panel.visible = true
  await nextTick()
  const destino = document.getElementById(`panel-${id}`)
  destino?.focus({ preventScroll: true })
  destino?.scrollIntoView?.({ block: 'start' })
  mensaje.value = `Mostrando ${titulo(id)}.`
}
function restablecer() { paneles.value = inicial(); mensaje.value = 'Distribución inicial restablecida.' }
</script>
<template>
  <nav aria-label="Ir a la información de tu red" class="accesos-paneles">
    <button v-for="p in catalogo" :key="p.id" type="button" @click="ir(p.id)">{{ p.pregunta ?? p.titulo }}</button>
  </nav>
  <p>Elige una pregunta para ir a su panel. Si estaba oculto, volverá a mostrarse.</p>
  <button type="button" aria-controls="opciones-paneles" :aria-expanded="editando" @click="editando = !editando">{{ editando ? 'Terminar de organizar' : 'Organizar mis paneles' }}</button>
  <div v-if="editando" id="opciones-paneles" class="opciones-paneles">
    <p>Arrastra desde «Mover» o usa los botones Anterior y Siguiente. Elige qué ver y cuánto espacio ocupa cada panel.</p>
    <fieldset v-if="vistas.length"><legend>Empezar con una vista preparada</legend>
      <button v-for="vista in vistas" :key="vista.id" type="button" @click="aplicarVista(vista)">{{ vista.titulo }}</button>
      <p>Solo cambia qué paneles se ven. Puedes volver a añadir cualquiera abajo.</p>
    </fieldset>
    <label v-for="p in paneles" :key="p.id"><input type="checkbox" v-model="p.visible" /> Mostrar {{ titulo(p.id) }}<span class="secundario ayuda-panel">{{ catalogo.find(c => c.id === p.id)?.descripcion }}</span></label>
    <button type="button" @click="restablecer">Restablecer distribución</button>
    <p class="secundario">Se guarda solo la distribución en este navegador, sin mediciones ni credenciales. Ocultar un panel no detiene las comprobaciones ni finaliza el acceso al router.</p>
  </div>
  <p role="status" aria-live="polite">{{ mensaje }}</p>
  <p v-if="!visibles.length">No hay paneles visibles. Usa «Organizar mis paneles» para añadirlos.</p>
  <div class="tablero">
    <div v-for="p in paneles" :key="p.id" v-show="p.visible" :data-panel="p.id" :class="['panel', { completo: p.ancho === 'completo' }]"
      @dragover.prevent @drop.prevent="soltar(p.id)">
      <div v-if="editando" class="controles-panel">
        <button type="button" draggable="true" @dragstart="iniciar($event, p.id)" @dragend="arrastrado = null" :aria-label="`Mover ${titulo(p.id)}`">Mover {{ titulo(p.id) }}</button>
        <button type="button" :disabled="visibles[0]?.id === p.id" @click="desplazar(p.id, -1)" :aria-label="`Mover ${titulo(p.id)} antes`">Anterior</button>
        <button type="button" :disabled="visibles.at(-1)?.id === p.id" @click="desplazar(p.id, 1)" :aria-label="`Mover ${titulo(p.id)} después`">Siguiente</button>
        <label>Ancho de {{ titulo(p.id) }} <select v-model="p.ancho"><option value="medio">Medio</option><option value="completo">Completo</option></select></label>
        <label>Altura de {{ titulo(p.id) }} <select v-model="p.alto"><option value="automatico">Todo el contenido</option><option value="compacto">Compacta, con desplazamiento</option><option value="amplio">Amplia, con desplazamiento</option></select></label>
      </div>
      <div :id="`panel-${p.id}`" :class="['contenido-panel', `alto-${p.alto}`]" tabindex="0" role="region" :aria-label="titulo(p.id)">
        <slot :name="p.id" />
      </div>
    </div>
  </div>
</template>
