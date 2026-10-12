<!-- Recibe sondas, asociaciones y vigencia HTTP de App; prioriza respuestas recientes y oculta el historial en un detalle desplegable. -->
<script setup>
import { computed } from 'vue'
const props = defineProps({ busqueda: Object, actualizada: { type: Boolean, default: true }, asociaciones: { type: Array, default: () => [] } })
const conocidas = computed(() => new Set(props.asociaciones.map(fila => fila.ipv4)))
const filas = computed(() => (props.busqueda?.resultados ?? []).filter(fila => fila.respondio_alguna_vez || conocidas.value.has(fila.ipv4)))
// Python decide la vigencia. Un fallo HTTP impide presentar la copia anterior como reciente.
const recientes = computed(() => props.actualizada ? filas.value.filter(fila => fila.estado === 'respuesta_valida' && fila.vigencia === 'vigente') : [])
const nombres = { respuesta_valida: 'Respondió a ICMP', sin_respuesta: 'Sin respuesta a ICMP', error_recoleccion: 'Error de comprobación' }
const estados = { esperando_contexto: 'Esperando contexto de red', buscando: 'Buscando y comprobando', en_espera: 'Barrido terminado; esperando el siguiente', interrumpida: 'Barrido interrumpido', omitida: 'Búsqueda omitida', detenida: 'Búsqueda detenida', error: 'Fallo de búsqueda', desactivada: 'Búsqueda desactivada' }
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'No disponible' }
</script>

<template>
  <section aria-labelledby="busqueda">
    <h2 id="busqueda">¿Qué vecinos han respondido recientemente?</h2>
    <p v-if="!busqueda">Esta API todavía no publica búsqueda activa. Reinicia Python para cargar la versión nueva.</p>
    <template v-else>
      <p><strong>{{ estados[busqueda.estado] ?? busqueda.estado }}</strong></p>
      <p v-if="busqueda.detalle" class="aviso">{{ busqueda.detalle }}</p>
      <p v-if="busqueda.contexto">Alcance: {{ busqueda.contexto.subred ?? busqueda.contexto.ipv4_local }} · interfaz {{ busqueda.contexto.interfaz ?? 'no disponible' }}.
        IP del Mac: {{ busqueda.contexto.ipv4_local }}. No se buscan redes Wi‑Fi cercanas.</p>
      <p v-if="busqueda.destinos_total != null">{{ busqueda.consultados }} de {{ busqueda.destinos_total }} IPv4 comprobadas en este barrido.</p>
      <p>Se comprueba la subred local: puede incluir equipos por Wi‑Fi y por cable. Estas respuestas no permiten conocer el nombre del Wi‑Fi de cada equipo.</p>
      <p v-if="busqueda.vigencia_s != null">Se muestran respuestas de menos de {{ busqueda.vigencia_s }} segundos, siempre que la última comprobación haya sido positiva. No es una confirmación permanente de conexión.</p>
      <p v-if="!actualizada" class="aviso">No hay datos actuales de la API. Las comprobaciones anteriores están disponibles en el detalle.</p>
      <p v-else-if="!recientes.length">Sin respuestas recientes disponibles. No significa que la red esté vacía.</p>
      <div v-else class="tabla recientes" tabindex="0" role="region" aria-label="Respuestas recientes; tabla desplazable">
        <table>
          <caption>Vecinos con respuesta ICMP reciente en la subred local</caption>
          <thead><tr><th scope="col">IPv4</th><th scope="col">Evidencia</th><th scope="col">Respuesta</th><th scope="col">Hace</th></tr></thead>
          <tbody><tr v-for="fila in recientes" :key="fila.ipv4">
            <td class="mono">{{ fila.ipv4 }}</td><td>Respondió a ICMP</td>
            <td>{{ fecha(fila.fin_comprobacion) }}</td>
            <td>{{ fila.antiguedad_s == null ? 'No disponible' : `${fila.antiguedad_s.toFixed(1)} s` }}</td>
          </tr></tbody>
        </table>
      </div>
      <p>Un equipo puede ignorar ICMP: «sin respuesta» no confirma desconexión. Una respuesta a una IPv4 no valida que pertenezca a una MAC histórica.</p>
      <p v-if="busqueda.intervalo_s != null">El siguiente barrido empieza {{ busqueda.intervalo_s }} segundos después de terminar el anterior.
        Último fin de barrido: {{ fecha(busqueda.fin_barrido) }}.</p>
      <details>
      <summary>Ver últimas comprobaciones, incluidas las que ya no tienen respuesta reciente</summary>
      <p v-if="!filas.length">Todavía no hay comprobaciones de asociaciones conocidas ni IPv4 que hayan respondido en este contexto.</p>
      <div v-else class="tabla" tabindex="0" role="region" aria-label="Comprobaciones IPv4; tabla desplazable">
        <table>
          <caption>Última comprobación por IPv4 conocida en ARP o que respondió durante esta ejecución</caption>
          <thead><tr><th scope="col">IPv4</th><th scope="col">Resultado</th><th scope="col">Comprobación</th><th scope="col">Antigüedad</th><th scope="col">Última respuesta ICMP</th></tr></thead>
          <tbody><tr v-for="fila in filas" :key="fila.ipv4">
            <td class="mono">{{ fila.ipv4 }}</td>
            <td>{{ nombres[fila.estado] ?? fila.estado }}<span v-if="fila.vigencia === 'desactualizado'"> · Comprobación antigua</span></td>
            <td>{{ fecha(fila.fin_comprobacion) }}</td>
            <td>{{ fila.antiguedad_s == null ? 'No disponible' : `${fila.antiguedad_s.toFixed(1)} s` }}</td>
            <td>{{ fecha(fila.ultima_respuesta) }}</td>
          </tr></tbody>
        </table>
      </div>
      </details>
    </template>
  </section>
</template>
