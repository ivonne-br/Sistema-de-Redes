// Entradas: API simulada. Verifica síntesis, recomendaciones reactivas y retirada
// de conclusiones de Observaciones.vue ante errores o cambios de contexto.
import { afterEach, expect, test, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Observaciones from '../src/components/Observaciones.vue'
let vista
const base = () => ({ estado: 'observado', titulo: 'La prueba respondió.', explicacion: 'Esta computadora llegó al sitio de prueba.',
  orientacion: 'Abre otra página.', evidencia: [], limite: '',
  incidencias: { mensaje: 'Resumen del backend', estado: 'observado', correctos: 10, fallos: 0, errores_medicion: 0, eventos: [] } })
async function preparar(datos) {
  vi.useFakeTimers()
  const pedir = vi.fn(async () => ({ ok: true, json: async () => structuredClone({ version_esquema: 1, datos }) }))
  vi.stubGlobal('fetch', pedir)
  vista = mount(Observaciones)
  await flushPromises()
  return pedir
}
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })
test('resume diez aciertos sin registros, duplicaciones ni recomendaciones innecesarias', async () => {
  await preparar(base())
  expect(vista.text().split('La prueba respondió.')).toHaveLength(2)
  expect(vista.text()).toContain('respondió en las comprobaciones realizadas')
  expect(vista.find('ol').exists()).toBe(false)
  for (const texto of ['Recomendación', 'Qué falta comprobar', 'Qué encontramos', 'Abre otra página.']) expect(vista.text()).not.toContain(texto)
})
test('ante fallo ofrece acción y verificación; recuperarse no oculta fallos recientes', async () => {
  const datos = base()
  datos.principal = { fuente: 'Sitio de prueba', estado: 'atencion', titulo: 'No se completó el acceso.', explicacion: 'No hubo respuesta.', orientacion: 'Abre otra página.' }
  datos.incidencias.fallos = 2
  await preparar(datos)
  expect(vista.text()).toContain('2 pruebas no lograron completar el acceso al sitio de prueba')
  expect(vista.text()).toContain('Recomendación')
  expect(vista.text()).toContain('Abre otra página.')
  expect(vista.text()).toContain('Después, vuelve a intentar')
  datos.principal = { ...datos.principal, estado: 'observar', titulo: 'Respondió ahora, hubo fallos antes.' }
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Respondió ahora, hubo fallos antes.')
  expect(vista.text()).toContain('2 pruebas')
})
test('errores de ejecución no se presentan como pruebas de acceso fallidas', async () => {
  const datos = base(); datos.incidencias.errores_medicion = 2
  await preparar(datos)
  expect(vista.text()).toContain('Algunas pruebas no pudieron realizarse')
  expect(vista.text()).not.toContain('2 pruebas no lograron completar')
})
test('retira conclusiones al fallar la API y al cambiar de contexto sin muestras', async () => {
  const datos = base(); const pedir = await preparar(datos)
  pedir.mockRejectedValueOnce(new Error('Sin servicio'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('La prueba respondió.')
  expect(vista.text()).toContain('No están llegando nuevos resultados')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('La prueba respondió.')
  Object.assign(datos, { estado: 'sin_datos', titulo: 'Esperando pruebas de esta red.', explicacion: '', incidencias: null })
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('La prueba respondió.')
  expect(vista.text()).not.toContain('últimos diez minutos')
})
test('solo presenta comparaciones suficientes y rechaza contratos incompletos', async () => {
  const datos = base(); datos.comparacion = { estado: 'insuficiente', mensaje: 'Faltan periodos', reciente: { intentos: 1, no_correctos: 0 }, anterior: { intentos: 0, no_correctos: 0 } }
  await preparar(datos)
  expect(vista.text()).not.toContain('Faltan periodos')
  datos.comparacion.estado = 'comparable'; datos.comparacion.mensaje = 'Ahora hubo menos fallos.'
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Ahora hubo menos fallos.')
  datos.incidencias.eventos = [null]
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('No están llegando nuevos resultados')
  expect(vista.text()).not.toContain('Ahora hubo menos fallos.')
})
