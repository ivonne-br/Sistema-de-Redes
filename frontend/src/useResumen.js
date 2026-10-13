// Estado de la pantalla: consulta secuencialmente la API y cancela temporizadores/HTTP al desmontar.
import { onMounted, onUnmounted, ref } from 'vue'
import { consultarResumen } from './api.js'

export function useResumen(consultar = consultarResumen, intervalo = 5000) {
  const respuesta = ref(null)
  const error = ref('')
  const cargando = ref(true)
  const recuperada = ref(false)
  const recibida = ref(null)
  let activo = false
  let temporizador, limite, controlador

  async function actualizar() {
    if (!activo || controlador) return
    clearTimeout(temporizador)
    const intento = new AbortController()
    controlador = intento
    limite = setTimeout(() => intento.abort(), 8000)
    try {
      const nueva = await consultar(intento.signal)
      if (!activo) return
      recuperada.value = Boolean(error.value)
      respuesta.value = nueva // Sustituye toda la ventana: no acumula eventos ni contextos.
      recibida.value = new Date()
      error.value = ''
    } catch (fallo) {
      if (!activo) return
      error.value = fallo.name === 'AbortError' ? 'La consulta superó 8 segundos.' : fallo.message
      recuperada.value = false
    } finally {
      clearTimeout(limite)
      controlador = null
      if (activo) {
        cargando.value = false
        temporizador = setTimeout(actualizar, intervalo)
      }
    }
  }
  onMounted(() => { activo = true; actualizar() })
  onUnmounted(() => { activo = false; clearTimeout(temporizador); clearTimeout(limite); controlador?.abort() })
  return { respuesta, error, cargando, recuperada, recibida }
}
