<!-- Recibe resultados DNS/HTTPS de api.js mediante useResumen; muestra últimos intentos, recuentos e historial con fechas y fallos separados de ICMP, sin calcular salud global. -->
<script setup>
import { computed } from 'vue'
import { consultarWeb } from '../api.js'
import { useResumen } from '../useResumen.js'
const { respuesta, error, cargando, recuperada } = useResumen(consultarWeb)
const datos = computed(() => respuesta.value?.datos)
const historial = computed(() => [...(datos.value?.historial ?? [])].reverse().flatMap(serie =>
  serie.resultados.map(fila => ({ ...fila, clave: `${serie.id_serie}-${fila.tipo}` }))))
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
      <div class="resumen-web" v-if="datos.resumen_ventana?.length">
        <h3>¿Cuántas comprobaciones fueron correctas?</h3>
        <p>Recuentos de la memoria disponible de este contexto, separados por prueba y destino. No son un porcentaje de disponibilidad de Internet.</p>
        <p v-if="error" class="aviso">Resumen conservado sin actualizar mientras la API no responde.</p>
        <article v-for="grupo in datos.resumen_ventana" :key="`${grupo.tipo}-${grupo.destino}`">
          <h4>{{ grupo.tipo.toUpperCase() }} · {{ grupo.destino }}</h4>
          <p>{{ grupo.correctos }} correctas de {{ grupo.intentos }} comprobaciones. {{ grupo.no_correctos }} no correctas.</p>
          <ul><li v-for="(cantidad, estado) in grupo.por_estado" :key="estado">{{ resultados[estado] ?? estado }}: {{ cantidad }}</li></ul>
          <p v-if="grupo.correcto_posterior">Hubo comprobaciones no correctas y el último intento conservado fue correcto. No demuestra una recuperación permanente.</p>
          <p class="secundario">Intentos incluidos: {{ fecha(grupo.primer_fin) }} → {{ fecha(grupo.ultimo_fin) }}. Las cifras disminuyen al expirar los intentos.</p>
        </article>
      </div>
      <details class="historial-web">
        <summary>¿Fue un fallo aislado o se repite? Ver evolución DNS/HTTPS</summary>
        <p>Comprobaciones del contexto actual, de la más reciente a la más antigua. Se conservan hasta {{ datos.capacidad_series ?? '—' }} ciclos y {{ datos.retencion_s ?? '—' }} segundos. Reiniciar Python borra esta memoria.</p>
        <p v-if="error" class="aviso">Historial conservado sin actualizar mientras la API no responde.</p>
        <p v-if="!historial.length">Todavía no hay comprobaciones conservadas en esta ventana.</p>
        <div v-else class="tabla" tabindex="0" role="region" aria-label="Evolución DNS y HTTPS; tabla desplazable">
          <table>
            <caption>Resultados por intento; una comprobación correcta posterior no borra el fallo anterior de la ventana retenida.</caption>
            <thead><tr><th scope="col">Fin</th><th scope="col">Prueba y destino</th><th scope="col">Resultado</th><th scope="col">Duración de operación</th><th scope="col">HTTP</th></tr></thead>
            <tbody><tr v-for="fila in historial" :key="fila.clave">
              <td>{{ fecha(fila.fin) }}</td><td>{{ fila.tipo.toUpperCase() }} · {{ fila.destino }}</td><td>{{ resultados[fila.estado] ?? fila.estado }}</td>
              <td>{{ numero(fila.duracion_ms, 'ms') }}</td><td>{{ fila.tipo === 'dns' ? 'No aplica' : fila.codigo_http ?? 'No disponible' }}</td>
            </tr></tbody>
          </table>
        </div>
        <p>DNS y HTTPS tienen duraciones distintas y no equivalen al RTT de ping. No hay mediciones continuas entre filas ni un porcentaje de salud. Un cambio de contexto inicia otra ventana visible.</p>
      </details>
      <p v-if="datos.intervalo_s">Una comprobación de cada tipo por ciclo; siguiente ciclo {{ datos.intervalo_s }} segundos después de terminar. Límite por comprobación: {{ datos.limite_s }} segundos. Vigencia: {{ datos.vigencia_s }} segundos.</p>
    </template>
    <details><summary>Qué comprueban DNS y HTTPS</summary>
      <p>DNS convierte un nombre en direcciones. Usamos la resolución configurada en el Mac: puede responder desde caché o desde otras fuentes del sistema. El tiempo no mide exclusivamente un servidor DNS.</p>
      <p>HTTPS resuelve su destino de forma independiente, establece una conexión segura con certificado válido y recibe las cabeceras. No descarga la página completa. Puede usar IPv4 o IPv6 según el sistema; DNS aquí consulta IPv4.</p>
      <p>Un código 204 significa respuesta correcta sin contenido. Un fallo afecta a esta comprobación y destino: no demuestra que todo Internet esté inaccesible. Estas pruebas no miden velocidad del Wi‑Fi.</p>
    </details>
  </section>
</template>
