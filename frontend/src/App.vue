<!-- Integra el estado de la API, conectividad pública y telemetría privada.
     Entrada: consultas a Python y confirmación de cierre. Salida: resumen navegable
     y cierre del servicio propietario, separado de los permisos del router. -->
<script setup>
import { ref, onUnmounted } from 'vue'
import Router from './components/Router.vue'
import Conectividad from './components/Conectividad.vue'
import ServiciosWeb from './components/ServiciosWeb.vue'
import Paneles from './components/Paneles.vue'
import Observaciones from './components/Observaciones.vue'
import { consultarEstado, solicitarCierre } from './api.js'
import { useResumen } from './useResumen.js'
const { respuesta, error, cargando, recibida, recuperada, detener } = useResumen(consultarEstado)
const confirmarCierre = ref(false)
const enviandoCierre = ref(false)
const cierreSolicitado = ref(false)
const errorCierre = ref('')
let controladorCierre
async function cerrarAplicacion() {
  if (enviandoCierre.value || cierreSolicitado.value || !confirmarCierre.value) return
  enviandoCierre.value = true
  errorCierre.value = ''
  controladorCierre = new AbortController()
  const limite = setTimeout(() => controladorCierre.abort(), 8000)
  try {
    await solicitarCierre(respuesta.value.monitoreo.id_ejecucion, controladorCierre.signal)
    detener()
    cierreSolicitado.value = true
    confirmarCierre.value = false
  } catch (fallo) {
    errorCierre.value = 'No pudimos confirmar el cierre. Puede que el servicio ya se esté cerrando. No se repetirá automáticamente. '
      + (fallo.name === 'AbortError' ? 'Se agotó la espera.' : fallo.message)
  } finally {
    clearTimeout(limite)
    enviandoCierre.value = false
  }
}
onUnmounted(() => controladorCierre?.abort())
const estados = { activo: 'En ejecución', no_iniciado: 'No iniciado', detenido: 'Detenido', error: 'Con error' }
const catalogo = [
  { id: 'observaciones', titulo: 'Qué está pasando', ancho: 'completo', pregunta: '¿Qué pasa y qué puedo hacer?', descripcion: 'Reúne las comprobaciones y explica qué puedes revisar, sin asegurar una causa cuando faltan datos.' },
  { id: 'internet', titulo: 'Acceso a Internet', pregunta: '¿Puedo abrir páginas?', descripcion: 'Comprueba si esta computadora pudo llegar al sitio de prueba. No necesita acceso al router.' },
  { id: 'respuesta', titulo: 'Tiempo de respuesta', pregunta: '¿Por qué noto esperas?', descripcion: 'Muestra cuánto tardaron los mensajes de prueba. Ayuda a observar esperas; no mide la velocidad de descarga ni confirma su causa.' },
  { id: 'equipos', titulo: 'Equipos y uso de Internet', ancho: 'completo', pregunta: '¿Qué equipos y uso puedo ver?', descripcion: 'Muestra los equipos y el tráfico que permite consultar el router. Requiere autorizar su lectura; lo que no informe aparecerá como no disponible.' },
]
const vistas = [
  { id: 'conexion', titulo: 'Revisar mi conexión', paneles: ['observaciones', 'internet', 'respuesta'] },
  { id: 'equipos', titulo: 'Consultar equipos y uso', paneles: ['equipos'] },
  { id: 'todo', titulo: 'Ver todos los paneles', paneles: catalogo.map(p => p.id) },
]
</script>

<template>
  <main>
    <header>
      <p class="ceja">Instalación local</p>
      <h1>Mi red doméstica</h1>
      <p>¿Puedes navegar? ¿Cuánto tarda en responder la conexión? ¿Qué equipos y tráfico informa tu router?</p>
      <p>Las comprobaciones describen la red a la que está conectada esta computadora ahora. No necesitas la contraseña del router para consultar la conexión.</p>
    </header>
    <section v-if="cierreSolicitado" role="status" aria-live="polite">
      <h2>Cierre solicitado</h2>
      <p>La aplicación está terminando sus tareas. Puedes cerrar esta pestaña; no necesitas escribir nada en la terminal.</p>
      <p>Para volver a usarla, abre «Iniciar Red.command». Comenzará una nueva sesión de mediciones.</p>
    </section>
    <template v-else>
    <section id="resumen" aria-labelledby="titulo-resumen">
      <h2 id="titulo-resumen">Estado de la aplicación</h2>
      <div role="status" aria-live="polite">
        <p v-if="cargando">Conectando con el servicio de medición…</p>
        <template v-else-if="error">
          <p class="aviso">La aplicación no está recibiendo mediciones. Esto no demuestra una caída de Internet. Se reintentará automáticamente.</p>
          <details><summary>Cómo recuperar la conexión con la aplicación</summary>
            <p>Abre de nuevo «Iniciar Red.command» en la carpeta de la aplicación. Si ya está abierta, reutilizará el servicio; si encuentra un problema, te explicará qué revisar.</p>
            <p>Si cerraste la ventana de inicio, las mediciones se detuvieron. Vuelve a abrirla y espera nuevas observaciones para comprobar si mejora.</p>
            <details><summary>Para desarrollo y detalle técnico</summary>
              <p>Los comandos independientes siguen disponibles desde la raíz:</p>
              <pre>.venv/bin/python -B -m backend servir-api</pre><pre>npm --prefix frontend run dev</pre>
              <p>Revisa la terminal del proceso existente antes de abrir otro. Detalle: {{ error }}</p>
            </details>
          </details>
        </template>
        <p v-else>{{ recuperada ? 'Comunicación con el servicio de medición recuperada.' : 'La aplicación está recibiendo información.' }} El resultado de tu conexión aparece en los paneles de abajo.</p>
      </div>
      <p v-if="recibida" class="secundario">Última consulta correcta: {{ recibida.toLocaleString('es-MX') }}{{ error ? ' · sin actualizar' : '' }}.</p>
      <details v-if="respuesta && !error"><summary>Detalles técnicos del servicio</summary>
        <p>{{ estados[respuesta.monitoreo.estado] ?? respuesta.monitoreo.estado }}. Este estado corresponde a ARP; las comprobaciones de Internet y el router tienen sus propios estados.</p>
        <p v-if="respuesta.monitoreo.error">{{ respuesta.monitoreo.error }}</p>
      </details>
      <button v-if="respuesta?.cierre_disponible && !error && !confirmarCierre" type="button" @click="confirmarCierre = true">Cerrar aplicación</button>
      <section v-if="confirmarCierre" role="alertdialog" aria-labelledby="titulo-cierre" aria-describedby="efecto-cierre">
        <h3 id="titulo-cierre">¿Cerrar la aplicación?</h3>
        <p id="efecto-cierre">Se detendrán las mediciones para todas las pestañas de esta aplicación y se perderán las muestras y los permisos temporales del router. No se apagará Internet ni se cambiará la configuración del router.</p>
        <button type="button" :disabled="enviandoCierre" @click="confirmarCierre = false; errorCierre = ''">Cancelar</button>
        <button type="button" :disabled="enviandoCierre" @click="cerrarAplicacion">{{ enviandoCierre ? 'Solicitando cierre…' : 'Confirmar cierre' }}</button>
        <p v-if="errorCierre" role="alert">{{ errorCierre }}</p>
      </section>
    </section>
    <Paneles :catalogo="catalogo" :vistas="vistas">
      <template #observaciones><Observaciones /></template>
      <template #internet><ServiciosWeb /></template>
      <template #respuesta><Conectividad /></template>
      <template #equipos><Router /></template>
    </Paneles>
    <footer>Las muestras recientes se conservan temporalmente en memoria. No hay historial persistente.
      <details><summary>Cómo cerrar la aplicación</summary>
        <p>Cerrar esta pestaña no detiene las mediciones. Usa «Cerrar aplicación» y confirma el cierre. Terminar la autorización del router es una acción distinta: permite seguir consultando la conexión.</p>
        <p v-if="respuesta && !respuesta.cierre_disponible">Este servicio se abrió por separado o con una versión anterior. No permite cerrarlo desde esta pantalla; su responsable debe cerrarlo desde la ventana donde lo inició.</p>
      </details>
    </footer>
    </template>
  </main>
</template>
