<!-- Consulta memoria protegida del backend y autoriza lectura temporal del router.
     Entradas: API local y sesión del panel introducida aquí; salida: DHCP y series WAN.
     El inventario DHCP no aporta consumo individual; la vista expresa esa limitación.
     Contraseña solo durante el envío; permiso local en cookie HttpOnly de sesión,
     nunca en preferencias. Admite la clave en memoria de versiones anteriores. -->
<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { useResumen } from '../useResumen.js'

const clave = ref(''), cookie = ref(''), csrf = ref(''), confirmado = ref(false)
const sesionCookie = ref(false)
const acceso = computed(() => Boolean(clave.value || sesionCookie.value))
let revision = 0
let retiradaLocal = false
const usuario = ref(''), password = ref(''), avanzado = ref(false)
const pendiente = ref(false), mensaje = ref(''), vence = ref(0), ahora = ref(Date.now())
const reloj = setInterval(() => { ahora.value = Date.now() }, 1000)
onUnmounted(() => { clearInterval(reloj); password.value = ''; clave.value = ''; cookie.value = ''; csrf.value = '' })
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
const inventario = computed(() => visible.value ? datos.value.tablas['dhcp-json'] : null)
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
function tasa(v) { return v == null ? 'Sin intervalo válido' : `${v.toFixed(3)} Mb/s` }
async function autorizar() {
  pendiente.value = true; mensaje.value = ''
  const cuerpo = { ...(avanzado.value ? { cookie: cookie.value, csrf: csrf.value } : { usuario: usuario.value, password: password.value }), confirmado: confirmado.value, id_contexto: datos.value?.id_contexto }
  cookie.value = ''; csrf.value = ''; password.value = ''; confirmado.value = false
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
    const id = `${punto.familia_ip} · ${punto.interfaz}`
    if (!grupos.has(id)) grupos.set(id, [])
    grupos.get(id).push(punto)
  }
  return Array.from(grupos, ([id, puntos]) => {
    const maximo = Math.max(1, ...puntos.flatMap(p => [p.bajada_mbps ?? 0, p.subida_mbps ?? 0]))
    const fin = ahora.value, inicio = fin - 600000
    const segmentos = campo => puntos.slice(1).flatMap((p, i) => {
      const a = puntos[i], dt = Date.parse(p.fecha) - Date.parse(a.fecha)
      if (a[campo] == null || p[campo] == null || dt <= 0 || dt > 20000) return []
      const x = v => Math.max(0, Math.min(600, (Date.parse(v.fecha) - inicio) / 1000))
      return [{ x1: x(a), y1: 100 - a[campo] / maximo * 90, x2: x(p), y2: 100 - p[campo] / maximo * 90 }]
    })
    return { id, puntos, maximo, bajada: segmentos('bajada_mbps'), subida: segmentos('subida_mbps') }
  })
})
</script>

<template>
  <section aria-labelledby="router-titulo">
    <h2 id="router-titulo">Dispositivos y tráfico del router</h2>
    <p>Aquí puedes ver los equipos que informa tu router y cuántos datos pasan por sus conexiones de Internet.</p>
    <p v-if="!acceso">Necesitas permiso y acceso al router para ver estos datos. Si estás en la escuela o en una red ajena, puedes usar los otros paneles sin conectar el router.</p>
    <details><summary>¿Qué significan bajada, subida y consumo?</summary>
      <p><strong>Bajada:</strong> datos que llegan desde Internet, por ejemplo al ver un video o descargar un juego.</p>
      <p><strong>Subida:</strong> datos que envías a Internet, por ejemplo en una videollamada o al subir fotos.</p>
      <p><strong>Mb/s:</strong> cantidad de datos que pasan cada segundo. Las gráficas muestran el uso observado, no la velocidad máxima de tu contrato.</p>
      <p><strong>Consumo:</strong> cantidad acumulada durante un periodo, expresada en MB o GB. No es lo mismo que Mb/s.</p>
      <p>Un tráfico alto no significa una red en mal estado. Para investigar lentitud hay que comprobar si coincide con respuestas más lentas o cortes; la coincidencia no demuestra la causa.</p>
    </details>
    <p v-if="cargando">Buscando el estado del recolector…</p>
    <details v-if="error"><summary>Datos del router no disponibles. Ver detalle</summary><p role="status">{{ error }} Los datos privados se ocultan mientras no se pueda verificar el acceso.</p></details>
    <p v-if="datos" role="status">{{ !acceso && ['lectura_correcta', 'verificando_compatibilidad', 'error_fuente'].includes(datos.estado) ? 'Esta vista no tiene acceso autorizado a los datos del router.' : etiquetas[datos.estado] ?? 'Lectura no disponible' }}</p>
    <p v-if="datos && !acceso && ['lectura_correcta', 'verificando_compatibilidad', 'error_fuente'].includes(datos.estado)">Hay una lectura en curso en el backend. Si pertenece a otro navegador o a una versión anterior, espera a que caduque (máximo 30 minutos desde su inicio), o finalízala desde la vista que tenga acceso.</p>
    <p v-if="datos?.etapa_error">El fallo ocurrió al {{ etapas[datos.etapa_error] ?? 'consultar el router' }}.</p>
    <p v-if="mensaje" role="status">{{ mensaje }}</p>
    <p v-if="datos?.gateway_candidato">Puerta de enlace candidata: <strong>{{ datos.gateway_candidato }}</strong>. Esa dirección por sí sola no identifica el modelo.</p>
    <p v-if="acceso && datos?.etapa_error">La sesión temporal se conserva; se volverá a intentar la consulta de lectura, sin reenviar la contraseña. Puedes finalizar el acceso.</p>
    <button v-if="acceso" type="button" @click="cerrar">Finalizar acceso de lectura</button>
    <p v-if="acceso && ahora < vence">Acceso de lectura: quedan aproximadamente {{ Math.ceil((vence - ahora) / 60000) }} minutos. Cambiar de red retira el permiso.</p>
    <p v-if="acceso && ahora >= vence">Acceso caducado: datos ocultos.</p>
    <details v-if="datos?.gateway_candidato && !error">
      <summary>Conectar router Sercomm</summary>
      <p>Usa el usuario de administración con el que entras al panel del router; no el nombre de la red Wi-Fi.</p>
      <p>Introduce el usuario y la contraseña del panel del router. Se realizará un solo intento; si falla, revisa el mensaje antes de volver a autorizar.</p>
      <p>Los valores se introducen solo aquí y se conservan en memoria durante un máximo de 30 minutos. El router observado usa HTTP: el envío al router no está cifrado. La aplicación inicia sesión y después consulta las tablas; no cambia la configuración. La contraseña se descarta tras el intento.</p>
      <p>El permiso local se conserva al recargar mediante una cookie de sesión HttpOnly, sin guardar la contraseña. Se comparte entre las pestañas de este perfil del navegador en la misma dirección local y caduca a los 30 minutos, aunque recargues. Usa «Finalizar acceso de lectura» para volver a la consulta como invitado.</p>
      <label><input v-model="avanzado" type="checkbox" /> Usar una sesión existente (avanzado)</label>
      <form @submit.prevent="autorizar">
        <fieldset :disabled="pendiente || acceso">
        <template v-if="!avanzado">
          <label>Usuario del router <input v-model="usuario" autocomplete="off" maxlength="128" required /></label>
          <label>Contraseña del router <input v-model="password" type="password" autocomplete="off" maxlength="1024" required /></label>
        </template>
        <template v-else>
        <label>Cookie de la sesión del panel <input v-model="cookie" type="password" autocomplete="off" maxlength="4096" required /></label>
        <label>Token CSRF del panel <input v-model="csrf" type="password" autocomplete="off" maxlength="256" required /></label>
        </template>
        <label><input v-model="confirmado" type="checkbox" required /> Confirmo que tengo autorización para acceder al router Sercomm en {{ datos.gateway_candidato }} y autorizo su lectura temporal.</label>
        <button type="submit">{{ pendiente || acceso ? 'Acceso solicitado' : 'Iniciar lectura automática' }}</button>
        </fieldset>
        <p v-if="acceso" role="status">{{ etiquetas[datos.estado] ?? 'Esperando resultado del router…' }}</p>
      </form>
    </details>
    <template v-if="visible">
      <p>Fuente: tablas del panel Sercomm con formato comprobado. No se ha verificado automáticamente su modelo ni firmware. IPv4 e IPv6 se mantienen separados; el alcance exacto del tráfico de la interfaz sigue por comprobar.</p>
      <template v-if="inventario">
        <h3>Inventario DHCP informado</h3>
        <p>Leído: {{ fecha(inventario.fecha) }} · {{ inventario.vigencia }} · {{ inventario.recuento.total }} registros, {{ inventario.recuento.activo }} activos, {{ inventario.recuento.inactivo }} inactivos, {{ inventario.recuento.estado_desconocido }} desconocidos.</p>
        <p v-if="inventario.ultimo_intento === 'error'">Falló la última lectura DHCP; esta tabla conserva su fecha anterior.</p>
        <p>«Activo» es el estado DHCP del router, no una garantía de presencia instantánea.</p>
        <p id="limite-consumo-dhcp">La tabla DHCP consultada no aporta bytes enviados ni recibidos por dispositivo. «No disponible» no significa consumo cero. Las tasas WAN se muestran por interfaz y no se pueden repartir entre los equipos.</p>
        <div class="tabla-router"><table aria-describedby="limite-consumo-dhcp"><thead><tr><th>Nombre</th><th>IP</th><th>MAC</th><th>Conexión</th><th>Estado informado</th><th>Consumo</th></tr></thead>
          <tbody><tr v-for="e in inventario.equipos" :key="`${e.ipv4}-${e.mac}`"><td>{{ e.nombre ?? 'Sin nombre' }}</td><td>{{ e.ipv4 }}</td><td>{{ e.mac }}</td><td>{{ e.conexion_original }}</td><td>{{ e.estado_original ?? `Desconocido (${e.codigo_estado_original})` }}</td><td>No disponible</td></tr></tbody>
        </table></div>
      </template>
      <p v-else>Inventario todavía no disponible.</p>
      <article v-for="g in grupos" :key="g.id">
        <h3>Tráfico WAN · {{ g.id }}</h3>
        <p>Última muestra: {{ fecha(g.puntos.at(-1).fecha) }}. Bajada: {{ tasa(g.puntos.at(-1).bajada_mbps) }} · Subida: {{ tasa(g.puntos.at(-1).subida_mbps) }}.</p>
        <p v-if="ahora - Date.parse(g.puntos.at(-1).fecha) > 20000">Muestra desactualizada.</p>
        <svg viewBox="0 0 600 110" role="img" :aria-label="`Tráfico ${g.id} de los últimos diez minutos; huecos sin intervalos válidos`">
          <line x1="0" y1="100" x2="600" y2="100" stroke="gray" />
          <line v-for="(s, i) in g.bajada" :key="`b${i}`" v-bind="s" stroke="#2166ac" stroke-width="2" />
          <line v-for="(s, i) in g.subida" :key="`s${i}`" v-bind="s" stroke="#a34500" stroke-width="2" />
        </svg>
        <p>Hace 10 min → ahora · Escala: 0–{{ g.maximo.toFixed(3) }} Mb/s. Azul: bajada; naranja: subida. Los huecos no representan cero.</p>
        <details><summary>Valores de la gráfica</summary><div class="tabla-router"><table><thead><tr><th>Fecha</th><th>Bajada</th><th>Subida</th></tr></thead><tbody><tr v-for="(p, i) in g.puntos" :key="i"><td>{{ fecha(p.fecha) }}</td><td>{{ tasa(p.bajada_mbps) }}</td><td>{{ tasa(p.subida_mbps) }}</td></tr></tbody></table></div></details>
      </article>
      <p>Sin consumo por dispositivo. Las tasas son promedios entre lecturas, no la capacidad contratada.</p>
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
