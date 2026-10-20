<!-- Resume el diagnóstico público de Python para decidir qué hacer.
Entradas: observaciones mediante useResumen. Salida: resultado, incidencias resumidas
 y recomendación solo ante problemas observados; no consulta ni administra el router. -->
<script setup>
import { computed } from 'vue'
import { consultarObservaciones } from '../api.js'
import { useResumen } from '../useResumen.js'
const { respuesta, error, cargando, recuperada } = useResumen(consultarObservaciones)
const datos = computed(() => respuesta.value?.datos)
const principal = computed(() => datos.value?.principal ?? datos.value)
const problema = computed(() => ['atencion', 'observar'].includes(principal.value?.estado))
const resumen = computed(() => {
  const i = datos.value?.incidencias
  if (i?.estado !== 'observado') return ''
  if (i.fallos > 0) return `En los últimos diez minutos, ${i.fallos} pruebas no lograron completar el acceso al sitio de prueba.`
  if (i.correctos > 0) return 'El sitio de prueba respondió en las comprobaciones realizadas durante los últimos diez minutos.'
  return 'No hay pruebas completadas para resumir el acceso reciente.'
})
function fecha(valor) { return valor ? new Date(valor).toLocaleString('es-MX') : 'Sin fecha disponible' }
</script>
<template>
  <section aria-labelledby="observaciones">
    <h2 id="observaciones">¿Puedo navegar?</h2>
    <p v-if="cargando" role="status">Estamos comprobando la conexión desde esta computadora. El resultado aparecerá aquí.</p>
    <div v-else-if="error" role="status">
      <p>No están llegando nuevos resultados. Por ahora no podemos decir cómo está tu conexión.</p>
      <p>Esto no demuestra una caída de Internet. Prueba abrir una página conocida. La aplicación volverá a consultar automáticamente.</p>
    </div>
    <template v-else-if="datos">
      <p v-if="recuperada" role="status">Volvieron a llegar resultados. Revisa la fecha de la comprobación.</p>
      <p class="resultado-principal"><strong>{{ principal.titulo }}</strong></p>
      <p>{{ principal.explicacion }}</p>
      <p v-if="principal.fecha || datos.ultima_comprobacion" class="secundario">Comprobado: {{ fecha(principal.fecha || datos.ultima_comprobacion) }}.</p>
      <p class="secundario">El resultado corresponde a esta computadora y al sitio de prueba.</p>
      <p v-if="resumen">{{ resumen }}</p>
      <p v-if="datos.incidencias?.errores_medicion">Algunas pruebas no pudieron realizarse. En esos momentos no sabemos si había acceso.</p>
      <template v-if="problema">
        <div v-if="datos.recorrido?.estado === 'observado'">
          <h3>¿Dónde puedo empezar a revisar?</h3>
          <p>{{ datos.recorrido.titulo }}</p><p>{{ datos.recorrido.explicacion }}</p>
        </div>
        <h3>Recomendación</h3>
        <p>{{ principal.orientacion }}</p>
        <p>Después, vuelve a intentar lo que no funcionaba y revisa si las siguientes comprobaciones responden.</p>
        <p v-if="datos.nombres?.estado === 'atencion'">También falló la búsqueda de la dirección de una página: la computadora no consiguió localizarla por su nombre.</p>
      </template>
      <p v-if="datos.comparacion?.estado === 'comparable'">{{ datos.comparacion.mensaje }}</p>
    </template>
  </section>
</template>
