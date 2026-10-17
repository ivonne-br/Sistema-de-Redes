<!-- Consulta memoria protegida y conecta identificación, lectura y administración.
     Entradas: API local y usuario/contraseña del panel introducidos aquí; salida: equipos, ayuda contextual, tiempo restante, tasas y cantidades por conexión y fuente, con explicación cotidiana antes de los detalles técnicos desplegables.
     El inventario DHCP no aporta consumo individual; la vista expresa esa limitación.
     Contraseña solo durante el envío; permiso local en cookie HttpOnly de sesión,
     nunca en preferencias. Admite la clave en memoria de versiones anteriores. -->
<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import AdministracionRouter from './AdministracionRouter.vue'
import Evolucion from './Evolucion.vue'
import { useResumen } from '../useResumen.js'

// Preferencia visual compartida por cantidades y gráficas; no contiene datos de red.
function leerPeriodo() {
  try { const p = Number(localStorage.getItem('red-trafico-periodo-v1')); return [60, 300, 600].includes(p) ? p : 600 }
  catch { return 600 }
}
const periodo = ref(leerPeriodo()), avisoPeriodo = ref('')
watch(periodo, p => {
  try { localStorage.setItem('red-trafico-periodo-v1', String(p)) }
  catch { avisoPeriodo.value = 'El periodo se aplica, pero no se pudo guardar en este navegador.' }
})
const clave = ref(''), confirmado = ref(false)
const sesionCookie = ref(false)
const acceso = computed(() => Boolean(clave.value || sesionCookie.value))
let revision = 0
let retiradaLocal = false
const usuario = ref(''), password = ref('')
const pendiente = ref(false), mensaje = ref(''), vence = ref(0), ahora = ref(Date.now())
const reloj = setInterval(() => { ahora.value = Date.now() }, 1000)
onUnmounted(() => { clearInterval(reloj); password.value = ''; clave.value = '' })
const { respuesta, error, cargando } = useResumen(async signal => {
  const enviada = clave.value, consultaRevision = revision
  const headers = enviada ? { 'X-Router-Authorization': enviada } : {}
  const r = await fetch('/api/v1/router', { signal, headers, cache: 'no-store', credentials: 'same-origin' })
  if (!r.ok) throw new Error(`Consulta del router: HTTP ${r.status}.`)
  const cuerpo = await r.json()
  if (consultaRevision !== revision) throw new Error('El acceso cambió durante la consulta; actualizando.')
  if (cuerpo.version_esquema !== 1 || typeof cuerpo.datos?.autorizada !== 'boolean'
      || !cuerpo.datos.tablas || !Array.isArray(cuerpo.datos.series)) throw new Error('Respuesta del router no compatible.')
  if (retiradaLocal) {
    cuerpo.datos = { ...cuerpo.datos, autorizada: false, tablas: {}, series: [] }
  }
  if (cuerpo.datos.autorizada) {
    if (!clave.value) {
      if (!Number.isFinite(cuerpo.datos.restante_s) || cuerpo.datos.restante_s < 0 || cuerpo.datos.restante_s > 1800) throw new Error('Caducidad de sesión no compatible.')
      sesionCookie.value = true
    }
    if (Number.isFinite(cuerpo.datos.restante_s)) {
      const limiteServidor = Date.now() + cuerpo.datos.restante_s * 1000
      vence.value = vence.value ? Math.min(vence.value, limiteServidor) : limiteServidor
    }
    if (cuerpo.datos.estado !== 'verificando_compatibilidad') mensaje.value = ''
  } else {
    clave.value = ''; sesionCookie.value = false; vence.value = 0
  }
  return cuerpo
})
const datos = computed(() => respuesta.value?.datos)
const visible = computed(() => !error.value && acceso.value && datos.value?.autorizada && ahora.value < vence.value)
const buscarEquipo = ref('')
const cantidades = computed(() => {
  if (!visible.value) return []
  return datos.value.trafico_por_periodo?.[String(periodo.value)]
    ?? (periodo.value === 600 ? datos.value.resumen_trafico : null) ?? []
})
const inventario = computed(() => visible.value ? datos.value.tablas['dhcp-json'] : null)
// Filtro local de registros ya autorizados; no se guarda la búsqueda ni la identidad.
const equiposVisibles = computed(() => {
  const texto = buscarEquipo.value.trim().toLocaleLowerCase('es')
  return (inventario.value?.equipos ?? []).filter(e => [e.nombre, e.ipv4, e.mac].some(v => String(v ?? '').toLocaleLowerCase('es').includes(texto)))
})
const etapas = { script_lectura: 'leer el script de estadísticas del router',
  validacion_sesion: 'validar la sesión mediante user_data.json', pagina_login: 'abrir la página de acceso', compatibilidad: 'comprobar compatibilidad',
  preparacion_login: 'preparar el acceso', ocupacion: 'comprobar si el router está ocupado',
  envio_login: 'enviar el inicio de sesión', apertura_sesion: 'abrir el panel tras el login', lectura_tablas: 'consultar las tablas' }
const etiquetas = {
  usuario_rechazado: 'El router indicó que el usuario es incorrecto. Respeta las mayúsculas del panel.',
  password_rechazada: 'El router indicó que la contraseña es incorrecta.', 
  http_invalido_router: 'El router devolvió una respuesta HTTP no compatible; no se pudo verificar el acceso.',
  error_http_router: 'El router rechazó la petición HTTP; no se confirmó el inicio de sesión.',
  tiempo_agotado_router: 'El router no respondió dentro del tiempo de espera.',
  conexion_fallida_router: 'No se pudo establecer la conexión con el router.',
  login_en_espera: 'El router exige esperar antes de otro intento', router_ocupado: 'El router está ocupado o tiene otra sesión activa',
  buscando_gateway: 'Buscando puerta de enlace', sin_contexto: 'Sin una red local compatible',
  requiere_autorizacion: 'Hace falta autorizar la lectura', verificando_compatibilidad: 'Comprobando sesión y formato del router',
  lectura_correcta: 'Último ciclo de lectura correcto', error_fuente: 'Falló una o más tablas; revisa sus fechas',
  autorizacion_expirada: 'El acceso temporal caducó', autorizacion_rechazada: 'El router rechazó la sesión',
  sesion_o_router_no_compatible: 'Sesión o formato del router no compatible', desactivado: 'Recolector no iniciado',
  error_lectura_router: 'No se pudo leer el router', error_recoleccion: 'Fallo de recolección', detenido: 'Recolector detenido',
}
function fecha(v) { return new Date(v).toLocaleString('es-MX') }
function volumen(v) { return v == null ? 'No disponible' : `${v.toLocaleString('es-MX', { maximumFractionDigits: 3 })} MB` }
function duracion(v) { return v == null ? 'No disponible' : v >= 60 ? `${(v / 60).toLocaleString('es-MX', { maximumFractionDigits: 1 })} minutos` : `${v.toLocaleString('es-MX', { maximumFractionDigits: 1 })} segundos` }
const restante = computed(() => { const s = Math.max(0, Math.ceil((vence.value - ahora.value) / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` })
function tasa(v) { return v == null ? 'Sin intervalo válido' : `${v.toFixed(3)} Mb/s` }
async function autorizar() {
  pendiente.value = true; mensaje.value = ''
  const cuerpo = { usuario: usuario.value, password: password.value, confirmado: confirmado.value, id_contexto: datos.value?.id_contexto }
  password.value = ''; confirmado.value = false
  const control = new AbortController(), limite = setTimeout(() => control.abort(), 8000)
  try {
    const r = await fetch('/api/v1/router/sesion', { method: 'POST', signal: control.signal,
      headers: { 'Content-Type': 'application/json', 'X-Router-Session': 'cookie' }, body: JSON.stringify(cuerpo), cache: 'no-store', credentials: 'same-origin' })
    if (!r.ok) throw new Error('No se aceptó el acceso: verifica la red y que no exista otra sesión local activa.')
    const resultado = await r.json()
    if (resultado.sesion !== 'cookie' && typeof resultado.clave !== 'string') throw new Error('Respuesta de autorización no compatible.')
    revision++
    retiradaLocal = false
    sesionCookie.value = resultado.sesion === 'cookie'
    clave.value = sesionCookie.value ? '' : resultado.clave; vence.value = Date.now() + 1800000
    mensaje.value = 'Acceso local creado. El recolector comprobará el router; aún no confirma una lectura correcta.'
  } catch { mensaje.value = 'No se pudo autorizar. Comprueba la sesión y la red. Si la respuesta se perdió, el permiso pendiente caduca en 30 minutos.' }
  finally { cuerpo.password = ''; cuerpo.cookie = ''; cuerpo.csrf = ''; clearTimeout(limite); pendiente.value = false }
}
async function cerrar() {
  const actual = clave.value
  revision++
  retiradaLocal = true
  clave.value = ''; sesionCookie.value = false; respuesta.value = null; mensaje.value = ''; vence.value = 0
  const control = new AbortController(), limite = setTimeout(() => control.abort(), 8000)
  try {
    const r = await fetch('/api/v1/router/sesion', { method: 'DELETE', signal: control.signal,
      headers: actual ? { 'X-Router-Authorization': actual } : {}, cache: 'no-store', credentials: 'same-origin' })
    if (!r.ok && r.status !== 401) throw new Error()
    mensaje.value = 'Acceso de la aplicación retirado. La sesión original del panel se conserva.'
  } catch { mensaje.value = 'Vista privada cerrada; no se confirmó la retirada en el backend. Caducará en un máximo de 30 minutos.' }
  finally { clearTimeout(limite) }
}
const grupos = computed(() => {
  if (!visible.value) return []
  const grupos = new Map()
  for (const punto of datos.value.series) {
    const id = JSON.stringify([punto.fuente, punto.familia_ip, punto.interfaz])
    if (!grupos.has(id)) grupos.set(id, [])
    grupos.get(id).push(punto)
  }
  return Array.from(grupos, ([id, puntos], indice) => ({ id, puntos, nombre: `Conexión informada ${indice + 1}`,
    series: [{ id: 'bajada', nombre: 'Bajada: datos que recibes', campo: 'bajada_mbps' },
             { id: 'subida', nombre: 'Subida: datos que envías', campo: 'subida_mbps' }].map(s => ({
      id: s.id, nombre: s.nombre, puntos: puntos.map(p => ({ edad: p.antiguedad_s, fecha: p.fecha, valor: p[s.campo] }))
    })) }))
})
</script>

<template>
  <section aria-labelledby="router-titulo">
    <h2 id="router-titulo">Dispositivos y tráfico del router</h2>
    <p>Aquí puedes ver los equipos que informa tu router y cuántos datos pasan por sus conexiones de Internet.</p>
    <p v-if="!acceso">La lectura del router es opcional: añade sus registros de equipos y el uso de sus conexiones de Internet. Puedes entender las comprobaciones de esta computadora sin autorizarla. Consultar información no modifica la configuración.</p>
    <p v-if="cargando">Buscando el estado del recolector…</p>
    <details v-if="error"><summary>Datos del router no disponibles. Ver detalle</summary><p role="status">{{ error }} Los datos privados se ocultan mientras no se pueda verificar el acceso.</p></details>
    <p v-if="datos" role="status">{{ !acceso && ['lectura_correcta', 'verificando_compatibilidad', 'error_fuente'].includes(datos.estado) ? 'Esta vista no tiene acceso autorizado a los datos del router.' : etiquetas[datos.estado] ?? 'Lectura no disponible' }}</p>
    <p v-if="datos && !acceso && ['lectura_correcta', 'verificando_compatibilidad', 'error_fuente'].includes(datos.estado)">Hay una lectura en curso en el backend. Si pertenece a otro navegador o a una versión anterior, espera a que caduque (máximo 30 minutos desde su inicio), o finalízala desde la vista que tenga acceso.</p>
    <p v-if="datos?.etapa_error">El fallo ocurrió al {{ etapas[datos.etapa_error] ?? 'consultar el router' }}.</p>
    <p v-if="mensaje" role="status">{{ mensaje }}</p>
    <aside v-if="datos?.gateway_candidato" aria-label="Router al que se autorizará el acceso"><h3>Router al que vas a acceder</h3><p>{{ datos.identificacion?.nombre ?? 'Comprobando el panel…' }}</p><p>Dirección del panel: <strong>{{ datos.gateway_candidato }}</strong>. Es la dirección de su panel en tu red.</p></aside>
    <p v-if="acceso && datos?.etapa_error">La sesión temporal se conserva; se volverá a intentar la consulta de lectura, sin reenviar la contraseña. Puedes finalizar el acceso.</p>
    <button v-if="acceso" type="button" @click="cerrar">Finalizar acceso de lectura</button>
    <p v-if="acceso && ahora < vence">Acceso de lectura: tiempo restante <strong>{{ restante }}</strong> (minutos:segundos). Cambiar de red retira el permiso.</p>
    <p v-if="acceso && ahora >= vence">Acceso caducado: datos ocultos.</p>
    <details v-if="datos?.gateway_candidato && !error">
      <summary>Añadir información del router · lectura opcional</summary>
      <p v-if="datos.identificacion && !datos.identificacion.adaptador">Todavía no reconocemos este panel. Puedes seguir usando las comprobaciones generales. Para investigar compatibilidad, consulta el modelo y la versión en el panel o la etiqueta del equipo; no compartas contraseñas ni el número de serie.</p>
      <p>Busca los datos de acceso al panel en la etiqueta o documentación del router, si allí se indican. Si fueron cambiados, consulta a quien administra tu red o a tu proveedor. La contraseña Wi-Fi puede ser distinta; no la supongas ni restablezcas el router para probar.</p>
      <p>Introduce el usuario y la contraseña del panel del router. Se realizará un solo intento; si falla, revisa el mensaje antes de volver a autorizar.</p>
      <p>Los valores se introducen solo aquí y se conservan en memoria durante un máximo de 30 minutos. El router observado usa HTTP: el envío al router no está cifrado. Este permiso inicia sesión y consulta las tablas. Los cambios requieren autorizar después la administración y confirmar cada operación. La contraseña se descarta tras el intento.</p>
      <p>Puedes recargar la página sin volver a introducir la contraseña mientras dure el permiso. Se comparte entre las pestañas de este perfil del navegador en la misma dirección local y caduca a los 30 minutos, aunque recargues. Usa «Finalizar acceso de lectura» para volver a la consulta como invitado y retirar también cualquier permiso administrativo.</p>
      <form @submit.prevent="autorizar">
        <fieldset :disabled="pendiente || acceso || !datos.identificacion?.adaptador">
          <label>Usuario del router <input v-model="usuario" autocomplete="off" maxlength="128" required /></label>
          <label>Contraseña del router <input v-model="password" type="password" autocomplete="off" maxlength="1024" required /></label>
        <label><input v-model="confirmado" type="checkbox" required /> Confirmo que tengo autorización para acceder al router identificado en {{ datos.gateway_candidato }} y autorizo su lectura temporal.</label>
        <button type="submit">{{ pendiente || acceso ? 'Acceso solicitado' : 'Iniciar lectura automática' }}</button>
        </fieldset>
        <p v-if="acceso" role="status">{{ etiquetas[datos.estado] ?? 'Esperando resultado del router…' }}</p>
      </form>
    </details>
    <template v-if="visible">
      <AdministracionRouter :clave="clave" :contexto="datos.id_contexto" :estado="datos.administracion" />
      <label>Periodo para cantidades y gráficas <select v-model="periodo" data-periodo-trafico><option :value="60">Último minuto</option><option :value="300">Últimos 5 minutos</option><option :value="600">Últimos 10 minutos</option></select></label>
      <p v-if="avisoPeriodo" role="status">{{ avisoPeriodo }}</p>
      <p v-if="!cantidades.length">No hay cantidades disponibles para este periodo. Espera lecturas comparables; la ausencia de datos no significa consumo cero.</p>
      <details v-if="cantidades.length"><summary>Cantidad de datos recibidos y enviados</summary>
        <p>Sirve para conocer cuántos datos se transfirieron durante el tiempo observado; no indica por sí solo si Internet funciona bien.</p>
        <p>Sumamos los datos recibidos y enviados en los intervalos completos medidos del periodo elegido ({{ periodo / 60 }} minutos). Si faltan lecturas, la cantidad es parcial: no estimamos lo que ocurrió durante esos huecos.</p>
        <article v-for="r in cantidades" :key="`${r.fuente}-${r.familia_ip}-${r.interfaz}`" class="resumen-destino">
          <h4>Cantidad observada en esta conexión</h4>
          <dl class="indicadores">
            <div><dt>Recibido (bajada)</dt><dd>{{ volumen(r.recibidos_mb) }}</dd></div>
            <div><dt>Enviado (subida)</dt><dd>{{ volumen(r.enviados_mb) }}</dd></div>
            <div><dt>Total observado en esta conexión</dt><dd>{{ volumen(r.total_mb) }}</dd></div>
          </dl>
          <p>{{ duracion(r.segundos_medidos) }} observados. No representa necesariamente todo el periodo elegido.</p>
          <p v-if="r.segundos_sin_medicion != null">{{ duracion(r.segundos_sin_medicion) }} sin información. No sabemos cuántos datos pasaron durante ese tiempo.</p>
          <p v-if="!r.intervalos_validos">Todavía no hay dos lecturas comparables para calcular una cantidad. No significa consumo cero.</p>
          <p v-if="r.antiguedad_s > 20">La última lectura es antigua; estas cantidades no incluyen lo que haya ocurrido después.</p>
          <p>Última lectura: {{ fecha(r.ultima_fecha) }}.</p>

        </article>

      </details>
      <p>Mostramos cada conexión informada por separado. Podrían incluir parte del mismo tráfico: sumarlas podría contar datos dos veces. No representan necesariamente cables o servicios distintos.</p>

      <template v-if="inventario">
        <h3>Equipos informados por el router</h3>
        <p>Leído: {{ fecha(inventario.fecha) }} · {{ inventario.vigencia }} · {{ inventario.recuento.total }} registros, {{ inventario.recuento.activo }} activos, {{ inventario.recuento.inactivo }} inactivos, {{ inventario.recuento.estado_desconocido }} desconocidos.</p>
        <p v-if="inventario.ultimo_intento === 'error'">Falló la última lectura DHCP; esta tabla conserva su fecha anterior.</p>
        <p id="estado-equipos-router">«Activo» significa que el router mantiene un registro de dirección para ese equipo. No garantiza que esté conectado ahora.</p>
        <p id="limite-consumo-dhcp">Esta fuente no permite saber cuánto consume cada equipo. El uso de las conexiones del router no se puede repartir entre los equipos de esta lista.</p>
        <label>Buscar equipo por nombre o dirección <input v-model="buscarEquipo" type="search" autocomplete="off" /></label>
        <p>{{ equiposVisibles.length }} registros coinciden con la búsqueda.</p>
        <p v-if="!equiposVisibles.length">No hay coincidencias en la tabla recibida. Esto no demuestra que un equipo esté desconectado.</p>
        <div class="tabla-router" tabindex="0" role="region" aria-label="Equipos informados por el router"><table aria-describedby="estado-equipos-router limite-consumo-dhcp"><thead><tr><th>Nombre</th><th>IP</th><th>MAC</th><th>Conexión</th><th>Estado informado</th></tr></thead>
          <tbody><tr v-for="e in equiposVisibles" :key="`${e.ipv4}-${e.mac}`"><td>{{ e.nombre ?? 'Sin nombre' }}</td><td>{{ e.ipv4 }}</td><td>{{ e.mac }}</td><td>{{ e.conexion_original }}</td><td>{{ e.estado_original ?? `Desconocido (${e.codigo_estado_original})` }}</td></tr></tbody>
        </table></div>
      </template>
      <p v-else>Inventario todavía no disponible.</p>
      <p v-if="!grupos.length">Todavía no hay mediciones de uso. Para calcular una tasa hacen falta dos lecturas compatibles; la ausencia de datos no significa uso cero.</p>
      <article v-for="g in grupos" :key="`${datos.id_contexto}-${g.id}`">
        <h3>{{ g.nombre }}</h3>
        <p>El router entrega el uso en grupos separados. Cada gráfica muestra uno de esos grupos, no un equipo ni una segunda prueba de velocidad.</p>
        <p>Úsala para ubicar momentos con más actividad y compararlos con la hora en que notaste una espera.</p>
        <details><summary>¿Qué es bajada y subida?</summary><p>Bajada: datos que recibes, como al ver un video. Subida: datos que envías, como al compartir fotos. Mb/s indica cuántos pasan por segundo; no es la velocidad máxima de tu contrato.</p></details>
        <template v-for="r in (datos.diagnostico?.comparaciones ?? []).filter(r => r.fuente === g.puntos[0].fuente && r.familia_ip === g.puntos[0].familia_ip && r.interfaz === g.puntos[0].interfaz)" :key="r.fuente">
          <p>{{ r.mensaje }} Que dos cambios coincidan no demuestra que uno cause el otro.</p>
          <p>{{ r.orientacion }}</p>
        </template>

        <p>Última muestra: {{ fecha(g.puntos.at(-1).fecha) }}. Bajada: {{ tasa(g.puntos.at(-1).bajada_mbps) }} · Subida: {{ tasa(g.puntos.at(-1).subida_mbps) }}.</p>
        <p v-if="g.puntos.at(-1).antiguedad_s > 20">Muestra desactualizada.</p>
        <Evolucion v-model:periodo="periodo" :series="g.series" unidad="Mb/s" :titulo="`Uso observado · ${g.nombre}`" preferencia="trafico" :hueco="20" />
      </article>

    </template>
  </section>
</template>

<style scoped>
form { display: grid; gap: 1rem; max-width: 48rem; }
fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 1rem; min-width: 0; }
label { display: block; }
input[type=password] { display: block; width: 100%; box-sizing: border-box; }
.tabla-router { overflow-x: auto; }
th, td { padding: .5rem; text-align: left; }
svg { width: 100%; max-height: 220px; }
</style>
