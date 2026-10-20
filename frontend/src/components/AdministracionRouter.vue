<!-- Administración explícita: recibe sesión/contexto del Router y consulta la API.
     Salida: acciones y planes confirmables, sin explicación interna del acceso y resultados verificados; secretos solo en memoria.
     No envía cambios al montar ni guarda configuración en el navegador. -->
<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
const props = defineProps({ clave: { type: String, default: '' }, contexto: String, estado: Object })
const permiso = ref(false), consentimiento = ref(false), limite = ref(0), ahora = ref(Date.now())
const ocupado = ref(false), aviso = ref(''), configuracion = ref(null), plan = ref(null), resultado = ref(null)
const operacion = ref('nombre'), banda = ref('2.4'), valor = ref(''), direccion = ref(''), confirmar = ref(false)
let revision = 0
const activo = computed(() => permiso.value && ahora.value < limite.value)
const cronometro = setInterval(() => { ahora.value = Date.now() }, 1000)
const estados = {
  verificado: 'El router informa la configuración solicitada. Comprueba ahora el efecto en el dispositivo.',
  aceptado_sin_verificar: 'El router aceptó la solicitud, pero todavía no se verificó el cambio. No lo repitas: comprueba el resultado.',
  incierto: 'Se perdió la confirmación del resultado. El cambio podría haberse aplicado. Reconecta esta computadora si hace falta y comprueba el resultado.',
  rechazado: 'El router no confirmó la aceptación. Revisa su configuración antes de intentar otro cambio.',
  sin_operacion: 'No hay un cambio pendiente de comprobación.',
}
function limpiar() {
  revision++; consentimiento.value = false; permiso.value = false; limite.value = 0; configuracion.value = null
  plan.value = null; resultado.value = null; valor.value = ''; direccion.value = ''; confirmar.value = false
}
watch(() => props.contexto, limpiar)
watch(() => props.estado, e => {
  if (!e?.autorizada) { if (permiso.value) limpiar(); return }
  permiso.value = true
  limite.value = Date.now() + e.restante_s * 1000
  if (e.resultado) resultado.value = e.resultado
}, { immediate: true })
watch(configuracion, c => {
  if (!c) return
  if (!c.wifi && c.bloqueo) operacion.value = 'bloquear'
  else if (!c.bloqueo && c.wifi) operacion.value = 'nombre'
  if (c.wifi && !c.wifi.some(r => r.banda === banda.value && r.activa)) banda.value = c.wifi.find(r => r.activa)?.banda ?? '2.4'
})
watch(activo, a => { if (!a) { valor.value = ''; plan.value = null; configuracion.value = null; confirmar.value = false } })
watch([operacion, banda], () => { valor.value = ''; direccion.value = ''; plan.value = null; confirmar.value = false })
onUnmounted(() => { clearInterval(cronometro); limpiar() })
async function pedir(accion, datos = {}) {
  const control = new AbortController(), temporizador = setTimeout(() => control.abort(), 60000)
  try {
    const r = await fetch(`/api/v1/router/administracion/${accion}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Red-Accion': 'administrar-router',
        ...(props.clave ? { 'X-Router-Authorization': props.clave } : {}) },
      credentials: 'same-origin', cache: 'no-store', signal: control.signal, body: JSON.stringify(datos) })
    const cuerpo = await r.json()
    if (!r.ok) throw new Error(cuerpo.error?.detalle ?? 'No se pudo completar la operación.')
    if (cuerpo.version_esquema !== 1 || !cuerpo.datos) throw new Error('Respuesta no compatible.')
    return cuerpo.datos
  } finally { clearTimeout(temporizador); if ('valor' in datos) datos.valor = '' }
}
async function ejecutar(accion) {
  if (ocupado.value) return
  ocupado.value = true; aviso.value = ''
  const actual = revision
  try {
    if (accion === 'autorizar') {
      const r = await pedir(accion, { confirmado: consentimiento.value })
      if (actual !== revision) return
      permiso.value = r.autorizada; limite.value = Date.now() + r.restante_s * 1000
      consentimiento.value = false
      const config = await pedir('consultar')
      if (actual === revision) configuracion.value = config
    } else if (accion === 'preparar') {
      const datos = ['nombre', 'password'].includes(operacion.value)
        ? { operacion: operacion.value, banda: banda.value, valor: valor.value }
        : { operacion: operacion.value, mac: direccion.value }
      valor.value = ''; plan.value = null; confirmar.value = false
      const r = await pedir(accion, datos)
      if (actual === revision) plan.value = { ...r, vence: Date.now() + r.restante_s * 1000 }
    } else if (accion === 'confirmar') {
      const id = plan.value?.id
      plan.value = null
      const r = await pedir(accion, { id, confirmado: confirmar.value })
      if (actual === revision) { resultado.value = r; configuracion.value = null }
      confirmar.value = false
    } else if (accion === 'finalizar') {
      await pedir(accion)
      limpiar(); aviso.value = 'Permiso administrativo retirado. Los cambios ya enviados se conservan.'
    } else if (accion === 'cancelar') {
      await pedir(accion); plan.value = null; confirmar.value = false
    } else if (accion === 'consultar') {
      const r = await pedir(accion)
      if (actual === revision) configuracion.value = r
    } else {
      const r = await pedir('verificar')
      if (actual === revision) resultado.value = r
    }
  } catch (e) {
    if (actual === revision) aviso.value = e.name === 'AbortError'
      ? 'La espera terminó. Si confirmaste un cambio, podría haberse enviado: usa Comprobar resultado antes de repetirlo.'
      : e.message
  } finally { ocupado.value = false }
}
</script>

<template>
  <section aria-labelledby="administracion-titulo">
    <h3 id="administracion-titulo">Administrar mi router</h3>
    <p>Cambia el nombre o la contraseña de Wi-Fi, o administra las restricciones de acceso compatibles. Leer datos no autoriza estos cambios.</p>
    <p v-if="aviso" role="status">{{ aviso }}</p>
    <p v-if="ocupado" role="status">Comprobando con el router…</p>
    <form v-if="!activo" @submit.prevent="ejecutar('autorizar')">
      <label><input v-model="consentimiento" type="checkbox" required /> Tengo permiso para administrar este router y autorizo cambios durante cinco minutos. Revisaré y confirmaré cada cambio.</label>
      <button :disabled="ocupado || !consentimiento">Autorizar administración</button>
    </form>
    <template v-else>
      <p>Administración autorizada: quedan {{ Math.max(0, Math.ceil((limite - ahora) / 1000)) }} segundos.</p>
      <button :disabled="ocupado" @click="ejecutar('finalizar')">Finalizar administración</button>
      <button :disabled="ocupado" @click="ejecutar('consultar')">Consultar configuración</button>
      <div v-if="resultado" role="status">
        <p>{{ resultado.resumen }}</p><p>{{ estados[resultado.estado] ?? 'Resultado pendiente de comprobación.' }}</p>
      </div>
      <button :disabled="ocupado" @click="ejecutar('verificar')">Comprobar resultado</button>
      <template v-if="configuracion">
        <p v-for="texto in configuracion.avisos" :key="texto">{{ texto }}</p>
        <form v-if="!plan && (configuracion.wifi || configuracion.bloqueo)" @submit.prevent="ejecutar('preparar')">
          <fieldset :disabled="ocupado">
            <legend>¿Qué quieres cambiar?</legend>
            <label>Acción <select v-model="operacion">
              <option v-if="configuracion.wifi" value="nombre">Nombre de la red Wi-Fi</option>
              <option v-if="configuracion.wifi" value="password">Contraseña de la red Wi-Fi</option>
              <option v-if="configuracion.bloqueo" value="bloquear">Bloquear acceso Wi-Fi de un dispositivo</option>
              <option v-if="configuracion.bloqueo" value="desbloquear">Retirar un bloqueo Wi-Fi</option>
            </select></label>
            <template v-if="['nombre', 'password'].includes(operacion)">
              <label>Red <select v-model="banda"><option v-for="red in configuracion.wifi ?? []" :key="red.banda" :value="red.banda" :disabled="!red.activa">{{ red.nombre ?? 'Banda apagada' }} ({{ red.banda }} GHz)</option></select></label>
              <label v-if="operacion === 'nombre'">Nuevo nombre <input v-model="valor" maxlength="32" autocomplete="off" required /></label>
              <label v-else>Nueva contraseña Wi-Fi <input v-model="valor" type="password" minlength="8" maxlength="63" autocomplete="new-password" required /></label>
              <p>Guarda los nuevos datos antes de continuar: puedes necesitarlos para reconectarte. La contraseña Wi-Fi es distinta de la contraseña de administración del router.</p>
            </template>
            <template v-else-if="operacion === 'bloquear'">
              <label>Dirección MAC del dispositivo <input v-model="direccion" placeholder="02:00:00:00:00:01" maxlength="17" autocomplete="off" required /></label>
              <p>Comprueba esa dirección en el propio dispositivo. El nombre o el tráfico total no permiten afirmar que ese equipo esté consumiendo más.</p>
            </template>
            <label v-else>Restricción que quieres retirar <select v-model="direccion" required><option value="" disabled>Selecciona una regla</option><option v-for="regla in configuracion.bloqueo?.lista ?? []" :key="regla.macfilter_mac" :value="regla.macfilter_mac">{{ regla.macfilter_name }} · {{ regla.macfilter_mac }}</option></select></label>
            <button type="submit">Revisar cambio</button>
          </fieldset>
        </form>
      </template>
      <div v-if="plan" role="group" aria-label="Confirmación del cambio">
        <p><strong>{{ plan.resumen }}</strong></p><p>{{ plan.efecto }}</p>
        <p v-if="ahora >= plan.vence">La confirmación caducó. Cancela y prepara el cambio otra vez.</p>
        <label><input v-model="confirmar" type="checkbox" /> Confirmo este cambio y entiendo su efecto.</label>
        <button :disabled="ocupado || !confirmar || ahora >= plan.vence" @click="ejecutar('confirmar')">Aplicar cambio confirmado</button>
        <button :disabled="ocupado" @click="ejecutar('cancelar')">Cancelar cambio</button>
      </div>
    </template>

  </section>
</template>
