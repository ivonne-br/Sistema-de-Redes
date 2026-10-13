<!-- Recibe presencia calculada por Python; muestra asociaciones y eventos sin inferir identidades ni ausencias. -->
<script setup>
defineProps({ presencia: { type: Object, required: true } })
const nombres = {
  observado: 'Visible en caché ARP', indeterminado: 'Indeterminado',
  no_observado_recientemente: 'No observado recientemente',
  referencia_inicial: 'Referencia inicial', primera_observacion: 'Primera observación',
  ausencia_observada: 'Ausencia observada', reaparicion: 'Reaparición',
}
function edad(valor) { return valor == null ? 'No disponible' : `${valor.toFixed(1)} s` }
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'No disponible' }
</script>

<template>
  <section aria-labelledby="asociaciones">
    <h2 id="asociaciones">¿Qué asociaciones se han observado?</h2>
    <p>Una asociación une IPv4 y MAC en este contexto; no identifica permanentemente un dispositivo.
      Se requieren {{ presencia.ausencias_requeridas }} ciclos completos comparables para una ausencia observada.</p>
    <p>Una fila puede permanecer en la caché después de desconectar el equipo. La antigüedad corresponde a la lectura de esa asociación, no a una respuesta del equipo.</p>
    <p v-if="!presencia.asociaciones.length">Sin asociaciones resueltas en la memoria de este contexto. Esto no confirma ausencia de equipos.</p>
    <div v-else class="tabla" tabindex="0" role="region" aria-label="Asociaciones ARP; tabla desplazable">
      <table>
        <caption>Asociaciones de la ventana retenida; antigüedad al consultar la API</caption>
        <thead><tr><th scope="col">IPv4</th><th scope="col">MAC</th><th scope="col">Estado</th><th scope="col">Última captura</th><th scope="col">Antigüedad</th></tr></thead>
        <tbody><tr v-for="fila in presencia.asociaciones" :key="`${presencia.id_contexto}:${fila.ipv4}:${fila.mac}`">
          <td class="mono">{{ fila.ipv4 }}</td><td class="mono">{{ fila.mac }}</td><td>{{ nombres[fila.estado] ?? fila.estado }}</td>
          <td>{{ fecha(fila.fin_ultima_captura) }}</td><td>{{ edad(fila.antiguedad_s) }}</td>
        </tr></tbody>
      </table>
    </div>
  </section>
  <section aria-labelledby="eventos">
    <h2 id="eventos">¿Qué cambios conserva la memoria?</h2>
    <p>La referencia inicial es el primer ciclo utilizable. Una lectura parcial no confirma ausencias.
      Fallos, lecturas parciales, resolución incompleta y pausas largas interrumpen la racha.</p>
    <p v-if="!presencia.eventos_en_memoria.length">Sin eventos en la memoria disponible.</p>
    <ol v-else class="eventos">
      <li v-for="evento in [...presencia.eventos_en_memoria].reverse()" :key="evento.id_evento">
        <strong>{{ nombres[evento.tipo] ?? evento.tipo }}</strong>
        <span class="mono">{{ evento.ipv4 }} · {{ evento.mac }}</span>
        <span>{{ fecha(evento.fin_captura) }} · ciclo {{ evento.ciclo }}</span>
      </li>
    </ol>
    <p>Estos eventos pertenecen a la ventana retenida; pueden desaparecer al expirar la memoria. Una reaparición significa que una asociación vuelve después de una ausencia observada.</p>
  </section>
</template>
