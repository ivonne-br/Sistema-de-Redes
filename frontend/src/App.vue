<!-- Integra el estado de la API, conectividad pública y telemetría privada.
     Entrada: consultas independientes a Python. Salida: resumen navegable sin mezclar autorizaciones ni calcular salud global. -->
<script setup>
import Router from './components/Router.vue'
import Conectividad from './components/Conectividad.vue'
import ServiciosWeb from './components/ServiciosWeb.vue'
import Paneles from './components/Paneles.vue'
import Observaciones from './components/Observaciones.vue'
import { consultarEstado } from './api.js'
import { useResumen } from './useResumen.js'
const { respuesta, error, cargando, recibida, recuperada } = useResumen(consultarEstado)
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
    <section id="resumen" aria-labelledby="titulo-resumen">
      <h2 id="titulo-resumen">Estado de la aplicación</h2>
      <div role="status" aria-live="polite">
        <p v-if="cargando">Conectando con el servicio de medición…</p>
        <template v-else-if="error">
          <p class="aviso">La aplicación no está recibiendo mediciones. Esto no demuestra una caída de Internet. Se reintentará automáticamente.</p>
          <details><summary>Cómo recuperar la conexión con la aplicación</summary>
            <p>Desde la raíz del proyecto, comprueba que siguen abiertos los dos procesos:</p>
            <pre>.venv/bin/python -B -m backend servir-api</pre><pre>npm --prefix frontend run dev</pre>
            <p>No inicies otra copia si ya están ejecutándose; revisa su terminal. Detalle: {{ error }}</p>
          </details>
        </template>
        <p v-else>{{ recuperada ? 'Comunicación con el servicio de medición recuperada.' : 'La aplicación está recibiendo información.' }} El resultado de tu conexión aparece en los paneles de abajo.</p>
      </div>
      <p v-if="recibida" class="secundario">Última consulta correcta: {{ recibida.toLocaleString('es-MX') }}{{ error ? ' · sin actualizar' : '' }}.</p>
      <details v-if="respuesta && !error"><summary>Detalles técnicos del servicio</summary>
        <p>{{ estados[respuesta.monitoreo.estado] ?? respuesta.monitoreo.estado }}. Este estado corresponde a ARP; las comprobaciones de Internet y el router tienen sus propios estados.</p>
        <p v-if="respuesta.monitoreo.error">{{ respuesta.monitoreo.error }}</p>
      </details>
    </section>
    <Paneles :catalogo="catalogo" :vistas="vistas">
      <template #observaciones><Observaciones /></template>
      <template #internet><ServiciosWeb /></template>
      <template #respuesta><Conectividad /></template>
      <template #equipos><Router /></template>
    </Paneles>
    <footer>Las muestras recientes se conservan temporalmente en memoria. No hay historial persistente.</footer>
  </main>
</template>
