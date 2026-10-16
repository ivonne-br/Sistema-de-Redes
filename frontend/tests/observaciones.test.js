// Verifica orientación visible y retirada de conclusiones ante fallos con API simulada.
import { afterEach, expect, test, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Observaciones from '../src/components/Observaciones.vue'
let vista
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })
test('explica, muestra evidencia a petición y oculta conclusiones antiguas hasta recuperarse', async () => {
  vi.useFakeTimers()
  const dato = { version_esquema: 1, datos: { estado: 'observado', titulo: 'La última comprobación pudo llegar a Internet.',
    explicacion: 'El sitio de prueba respondió.', orientacion: 'Prueba abrir otra página.', limite: 'No prueba todos los sitios.',
    recorrido: { estado: 'observado', titulo: 'Hubo respuestas dentro y fuera de tu red.',
      explicacion: 'No garantiza que todas las aplicaciones funcionen.', orientacion: 'Prueba otra página.',
      evidencia: [{ nombre: 'Dentro de tu red', respuestas: 3, intentos: 3, fecha: '2026-10-15T12:00:00Z' }] },
    evidencia: [{ fecha: '2026-10-15T12:00:00Z', resultado: 'correcto', destino: 'https://example.test' }],
    comparacion: { mensaje: 'Aún no hay suficientes comprobaciones.', reciente: { intentos: 1, no_correctos: 0 }, anterior: { intentos: 0, no_correctos: 0 } } } }
  const pedir = vi.fn(async () => ({ ok: true, json: async () => dato }))
  vi.stubGlobal('fetch', pedir)
  vista = mount(Observaciones)
  await flushPromises()
  expect(vista.text()).toContain('Prueba abrir otra página')
  expect(vista.text()).toContain('¿Dónde puedo empezar a revisar?')
  expect(vista.text()).toContain('3 respuestas de 3 intentos')
  expect(vista.findAll('details').every(d => d.attributes('open') === undefined)).toBe(true)
  pedir.mockRejectedValueOnce(new Error('Sin servicio'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('pudo llegar a Internet')
  expect(vista.text()).not.toContain('Hubo respuestas dentro y fuera')
  expect(vista.text()).not.toContain('Prueba abrir otra página')
  expect(vista.text()).toContain('No están llegando nuevos resultados')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Prueba abrir otra página')
})


test('explica la comparación de tiempos, distingue ausencia de datos y retira resultados al fallar', async () => {
  vi.useFakeTimers()
  const datos = { estado: 'sin_datos', titulo: 'Esperando la prueba web', explicacion: '', orientacion: '', limite: '', evidencia: [],
    tiempos_respuesta: [{ nombre: 'Fuera de tu red', destino: '1.1.1.1', estado: 'comparable',
      mensaje: 'Las respuestas tardaron más, en promedio.', orientacion: 'Comprueba si las pausas se repiten.',
      anterior: { promedio_ms: 20, respuestas: 9, sin_respuesta: 0 }, reciente: { promedio_ms: 40, respuestas: 9, sin_respuesta: 0 } }] }
  const pedir = vi.fn(async () => ({ ok: true, json: async () => JSON.parse(JSON.stringify({ version_esquema: 1, datos })) }))
  vi.stubGlobal('fetch', pedir)
  vista = mount(Observaciones)
  await flushPromises()
  expect(vista.text()).toContain('¿Está tardando más en responder?')
  expect(vista.get('dl').text()).toContain('20 ms')
  expect(vista.get('dl').text()).toContain('40 ms')
  expect(vista.text()).toContain('No mide la rapidez de tus descargas')
  datos.tiempos_respuesta[0].estado = 'insuficiente'
  datos.tiempos_respuesta[0].mensaje = 'Todavía faltan comprobaciones'
  datos.tiempos_respuesta[0].reciente.promedio_ms = null
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.find('dl').exists()).toBe(false)
  expect(vista.text()).toContain('No disponible')
  pedir.mockRejectedValueOnce(new Error('Sin servicio'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('¿Está tardando más en responder?')
  expect(vista.text()).toContain('No están llegando nuevos resultados')
})


test('prioriza una orientación, permite abrir evidencia y descarta un contrato incompleto', async () => {
  vi.useFakeTimers()
  const datos = { estado: 'observado', titulo: 'Título secundario', explicacion: '', orientacion: '', limite: '', evidencia: [],
    diagnostico: { hallazgos: ['Se observaron respuestas posteriores.'], comprobar: 'Comprueba si vuelve a funcionar.', falta: 'No garantiza recuperación definitiva.' },
    principal: { estado: 'observar', titulo: 'El sitio respondió ahora, pero hubo problemas antes.',
      explicacion: 'Hubo dos pruebas con problemas.', orientacion: 'Comprueba si tu aplicación vuelve a funcionar.', fuente: 'Visita al sitio de prueba' },
    incidencias: { estado: 'observado', mensaje: 'El problema se observó más de una vez.', errores_medicion: 1,
      eventos: [{ id: 'uno', fecha: '2026-10-15T12:00:00Z', descripcion: 'El sitio respondió correctamente.', destino: 'https://example.test' }] },
    nombres: { estado: 'sin_datos', titulo: 'Falta una búsqueda reciente', explicacion: '', orientacion: '' } }
  const pedir = vi.fn(async () => ({ ok: true, json: async () => JSON.parse(JSON.stringify({ version_esquema: 1, datos })) }))
  vi.stubGlobal('fetch', pedir)
  vista = mount(Observaciones)
  await flushPromises()
  expect(vista.get('.resultado-principal').text()).toContain('respondió ahora')
  expect(vista.text()).not.toContain('Título secundario')
  expect(vista.text()).toContain('Cómo comprobar si mejora')
  expect(vista.text()).toContain('No garantiza recuperación definitiva.')
  expect(vista.text()).toContain('más de una vez')
  const detalle = vista.findAll('details').find(d => d.text().includes('Ver qué pasó'))
  expect(detalle.attributes('open')).toBeUndefined()
  detalle.element.open = true
  expect(detalle.get('li').text()).toContain('El sitio respondió correctamente')
  expect(detalle.text()).toContain('No se cuentan como fallos de Internet')
  datos.incidencias.eventos = [null]
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('No están llegando nuevos resultados')
  expect(vista.text()).not.toContain('respondió ahora')
})
