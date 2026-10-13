<!-- Recibe resultados DNS/HTTPS de api.js mediante useResumen; muestra fechas y fallos separados de ICMP, sin calcular salud global. -->
<script setup>
import { computed } from 'vue'
import { consultarWeb } from '../api.js'
import { useResumen } from '../useResumen.js'
const { respuesta, error, cargando, recuperada } = useResumen(consultarWeb)
const datos = computed(() => respuesta.value?.datos)
const estados = { esperando_contexto: 'Esperando contexto de red', sin_contexto: 'Contexto no disponible',
  midiendo: 'Comprobando DNS y HTTPS', en_espera: 'Esperando la siguiente comprobación',
  detenido: 'Monitor detenido', desactivada: 'Comprobaciones desactivadas', error: 'Fallo del monitor' }
const resultados = { correcto: 'Comprobación correcta', sin_direcciones: 'Sin direcciones IPv4',
  error_resolucion: 'No se pudo resolver el nombre', certificado_invalido: 'Certificado TLS no válido',
  error_tls: 'Falló la conexión TLS', tiempo_agotado: 'Tiempo de espera agotado',
  error_conexion: 'Falló la conexión', http_inesperado: 'Respuesta HTTP distinta de la esperada',
  error_medicion: 'Error al ejecutar la comprobación' }
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'No disponible' }
function numero(valor, unidad) { return valor == null ? 'No disponible' : `${valor} ${unidad}` }
</script>
<template>
  <section aria-labelledby="servicios-web">
    <h2 id="servicios-web">¿Se resuelven los nombres y responde el servicio HTTPS?</h2>
    <div role="status" aria-live="polite">
      <p v-if="cargando">Cargando comprobaciones DNS/HTTPS…</p>
      <p v-else-if="error" class="aviso">{{ error }} Se reintentará automáticamente. Los datos conservados y sus edades están congelados; no describen el momento actual.</p>
      <p v-else-if="recuperada">Consulta DNS/HTTPS recuperada.</p>
    </div>
    <template v-if="datos">
      <p><strong>{{ estados[datos.estado] ?? datos.estado }}</strong></p>
      <p v-if="datos.detalle">{{ datos.detalle }}</p>
      <p v-if="!datos.resultados.length">Sin comprobaciones conservadas para este contexto.</p>
      <article v-for="fila in datos.resultados" :key="`${datos.id_contexto}-${fila.tipo}`">
        <h3>{{ fila.tipo === 'dns' ? 'DNS · resolución IPv4 del sistema' : 'HTTPS · respuesta del servicio' }}</h3>
        <p>Destino: <code>{{ fila.destino }}</code></p>
        <p><strong>{{ resultados[fila.estado] ?? fila.estado }}</strong> · {{ error ? 'Dato conservado sin actualizar' : fila.vigencia === 'vigente' ? 'Dato dentro de vigencia' : 'Dato antiguo' }}</p>
        <p v-if="fila.tipo === 'dns'">IPv4 obtenidas: {{ fila.direcciones.length ? fila.direcciones.join(', ') : 'No disponible' }}.</p>
        <p v-else>Código HTTP recibido: {{ fila.codigo_http ?? 'No disponible' }}. Esperado: {{ datos.codigo_https_esperado }}. No se siguen redirecciones.</p>
        <p>Duración de la operación: {{ numero(fila.duracion_ms, 'ms') }}. No es RTT de ping.</p>
        <p>Último intento: {{ fecha(fila.fin) }}. Antigüedad al consultar: {{ numero(fila.antiguedad_s == null ? null : fila.antiguedad_s.toFixed(1), 's') }}.</p>
      </article>
      <p v-if="datos.intervalo_s">Una comprobación de cada tipo por ciclo; siguiente ciclo {{ datos.intervalo_s }} segundos después de terminar. Límite por comprobación: {{ datos.limite_s }} segundos. Vigencia: {{ datos.vigencia_s }} segundos.</p>
    </template>
    <details><summary>Qué comprueban DNS y HTTPS</summary>
      <p>DNS convierte un nombre en direcciones. Usamos la resolución configurada en el Mac: puede responder desde caché o desde otras fuentes del sistema. El tiempo no mide exclusivamente un servidor DNS.</p>
      <p>HTTPS resuelve su destino de forma independiente, establece una conexión segura con certificado válido y recibe las cabeceras. No descarga la página completa. Puede usar IPv4 o IPv6 según el sistema; DNS aquí consulta IPv4.</p>
      <p>Un código 204 significa respuesta correcta sin contenido. Un fallo afecta a esta comprobación y destino: no demuestra que todo Internet esté inaccesible. Estas pruebas no miden velocidad del Wi‑Fi.</p>
    </details>
  </section>
</template>
