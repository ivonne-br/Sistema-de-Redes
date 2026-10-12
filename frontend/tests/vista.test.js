// Datos artificiales entran por fetch; verifica la pantalla, la ventana retenida y el ciclo HTTP sin red real.
import { beforeEach, afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'
import { consultarResumen } from '../src/api.js'

const base = () => ({ version_esquema: 1, monitoreo: { estado: 'activo' }, datos: {
  calidad: { calidad_fuente: 'completa', vigencia: 'vigente', antiguedad_s: 2, id_contexto: 'A', id_ultima_utilizable: 'o1', vigencia_s: 90 },
  vecinos: { cantidad: 2, resolucion_mac: { resuelta: 1, incompleta: 1 }, fin_captura: '2026-10-09T12:00:00Z' },
  presencia: { id_contexto: 'A', ausencias_requeridas: 3,
    asociaciones: [{ ipv4: '192.0.2.1', mac: 'aa:bb:cc:dd:ee:ff', estado: 'observado', antiguedad_s: 2 }],
    eventos_en_memoria: [{ id_evento: 'e1', tipo: 'referencia_inicial', ipv4: '192.0.2.1', mac: 'aa:bb:cc:dd:ee:ff', ciclo: 1 }] },
} })
const ok = dato => ({ ok: true, json: async () => dato })
let vista
beforeEach(() => { window.history.replaceState({}, '', '/?diagnostico=1') })
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/') })

test('la vista habitual no incluye tablas ARP ni eventos de diagnóstico', async () => {
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('fetch', vi.fn(async () => ok(base())))
  vista = mount(App, { global: { stubs: { Conectividad: true } } })
  await flushPromises()
  expect(vista.find('details.diagnostico').exists()).toBe(false)
  expect(vista.find('.eventos').exists()).toBe(false)
  expect(vista.text()).not.toContain('aa:bb:cc:dd:ee:ff')
})

test('carga, cuenta filas y reemplaza eventos; retención y A → B → A no mezclan tramos', async () => {
  vi.useFakeTimers()
  let dato = base()
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(App, { global: { stubs: { Conectividad: true } } })
  expect(vista.text()).toContain('Cargando')
  await flushPromises()
  expect(vista.get('details.diagnostico').attributes('open')).toBeUndefined()
  expect(vista.findAll('tbody tr')).toHaveLength(1)
  expect(vista.findAll('.eventos li')).toHaveLength(1)
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('.eventos li')).toHaveLength(1)
  for (const contexto of ['B', 'A']) {
    dato = base()
    dato.datos.calidad.id_contexto = contexto
    dato.datos.presencia = { id_contexto: contexto, ausencias_requeridas: 3, asociaciones: [], eventos_en_memoria: [] }
    await vi.advanceTimersByTimeAsync(5000)
    expect(vista.findAll('.eventos li')).toHaveLength(0)
    expect(vista.findAll('tbody tr')).toHaveLength(0)
  }
})

test('distingue parcial, fallo con dato anterior, antiguo, API caída y recuperación', async () => {
  vi.useFakeTimers()
  let dato = base()
  dato.datos.calidad.calidad_fuente = 'parcial'
  const fetchMock = vi.fn(async () => ok(dato))
  vi.stubGlobal('fetch', fetchMock)
  vista = mount(App, { global: { stubs: { Conectividad: true } } })
  await flushPromises()
  expect(vista.text()).toContain('Lectura parcial')
  dato = base()
  Object.assign(dato.datos.calidad, { calidad_fuente: 'error_fuente', estado_ultimo_intento: 'sin_datos_visibles', vigencia: 'desactualizado', antiguedad_s: 100 })
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('cero bytes')
  expect(vista.text()).toContain('Dato antiguo')
  expect(vista.text()).toContain('Se muestra el dato anterior')
  fetchMock.mockRejectedValueOnce(new TypeError('Sin conexión'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('congelados')
  expect(vista.findAll('tbody tr')).toHaveLength(1)
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Comunicación con la API recuperada')
})

test('sin observaciones conserva null como no disponible', async () => {
  const dato = base()
  Object.assign(dato.datos.calidad, { calidad_fuente: 'no_disponible', id_ultima_utilizable: null, antiguedad_s: null })
  dato.datos.vecinos = { cantidad: null, resolucion_mac: null }
  dato.datos.presencia.asociaciones = []
  dato.datos.presencia.eventos_en_memoria = []
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(App, { global: { stubs: { Conectividad: true } } })
  await flushPromises()
  expect(vista.text()).toContain('Sin observaciones')
  expect(vista.findAll('dd').slice(-3).map(n => n.text())).toEqual(Array(3).fill('No disponible'))
})

test('no superpone peticiones y cancela al desmontar sin programar otra', async () => {
  vi.useFakeTimers()
  let signal
  let terminar
  const fetchMock = vi.fn((_, opciones) => {
    signal = opciones.signal
    return new Promise(resolve => { terminar = resolve })
  })
  vi.stubGlobal('fetch', fetchMock)
  vista = mount(App, { global: { stubs: { Conectividad: true } } })
  await vi.advanceTimersByTimeAsync(6000)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  vista.unmount()
  expect(signal.aborted).toBe(true)
  terminar(ok(base()))
  await flushPromises()
  await vi.advanceTimersByTimeAsync(20000)
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('el timeout permite reintentar y recuperar la vista', async () => {
  vi.useFakeTimers()
  const fetchMock = vi.fn().mockImplementationOnce((_, { signal }) => new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Cancelada', 'AbortError')))
  })).mockResolvedValue(ok(base()))
  vi.stubGlobal('fetch', fetchMock)
  vista = mount(App, { global: { stubs: { Conectividad: true } } })
  await vi.advanceTimersByTimeAsync(8000)
  expect(vista.text()).toContain('superó 8 segundos')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Comunicación con la API recuperada')
})

test('rechaza HTTP fallido, JSON inválido y esquema incompatible', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockResolvedValueOnce({ ok: false, status: 503 })
  await expect(consultarResumen()).rejects.toThrow('HTTP 503')
  fetchMock.mockResolvedValueOnce({ ok: true, json: async () => { throw new SyntaxError('JSON inválido') } })
  await expect(consultarResumen()).rejects.toThrow('JSON inválido')
  fetchMock.mockResolvedValueOnce(ok({ version_esquema: 2 }))
  await expect(consultarResumen()).rejects.toThrow('formato no compatible')
})
