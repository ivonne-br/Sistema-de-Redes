// Simula HTTP y tiempo para verificar métricas independientes de ARP, recuperación, recuentos, historial y contexto y cancelación de la vista ICMP.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Conectividad from '../src/components/Conectividad.vue'
import App from '../src/App.vue'
import { consultarConectividad } from '../src/api.js'

const fila = () => ({ tipo: 'router', ipv4: '192.0.2.1', calidad: 'completa', vigencia: 'vigente',
  programadas: 5, realizadas: 5, respuestas: 4, sin_respuesta: 1, errores: 0, omitidas: 0,
  perdida_observada_pct: 20, rtt_ms: { muestras: 4, minimo: 0, promedio: 10, maximo: 20 },
  fin: '2026-10-10T12:00:00Z', antiguedad_s: 3 })
const base = () => ({ version_esquema: 1, datos: { estado: 'en_espera', id_contexto: 'A',
  muestras_por_serie: 5, intervalo_s: 30, vigencia_s: 90, destinos: [fila()] } })
const ok = dato => ({ ok: true, json: async () => structuredClone(dato) })
let vista
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })

test('presenta respuestas y RTT cero sin inventar salud ni pérdidas cuando hay errores', async () => {
  vi.useFakeTimers()
  let dato = base()
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(Conectividad)
  expect(vista.text()).toContain('Cargando mediciones')
  await flushPromises()
  expect(vista.text()).toContain('20 %')
  expect(vista.text()).toContain('0 ms')
  const anterior = fila()
  dato.datos.destinos[0] = { ...fila(), calidad: 'parcial', errores: 1, perdida_observada_pct: null,
    vigencia: 'desactualizado', anterior_completa: anterior }
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Serie parcial')
  expect(vista.text()).toContain('Dato antiguo')
  expect(vista.text()).toContain('Última serie completa anterior')
  expect(vista.findAll('dd')[2].text()).toBe('No disponible')
})

test('fallo HTTP conserva dato identificado como congelado y se recupera', async () => {
  vi.useFakeTimers()
  const pedir = vi.fn().mockResolvedValue(ok(base()))
  vi.stubGlobal('fetch', pedir)
  vista = mount(Conectividad)
  await flushPromises()
  pedir.mockRejectedValueOnce(new Error('API inaccesible'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('congelados')
  expect(vista.findAll('article')).toHaveLength(1)
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Consulta de conectividad recuperada')
  expect(vista.text()).not.toContain('congelados')
})

test('retención y cambio de contexto sustituyen datos, no acumulan series', async () => {
  vi.useFakeTimers()
  let dato = base()
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(Conectividad)
  await flushPromises()
  dato = { version_esquema: 1, datos: { estado: 'sin_contexto', id_contexto: null, destinos: [] } }
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('article')).toHaveLength(0)
  expect(vista.text()).toContain('Sin series conservadas')
  dato = base()
  dato.datos.id_contexto = 'B'
  dato.datos.destinos[0].ipv4 = '198.51.100.1'
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('article')).toHaveLength(1)
  expect(vista.text()).not.toContain('192.0.2.1')
})

test('fallo de la consulta ARP no oculta las métricas independientes', async () => {
  vi.stubGlobal('fetch', vi.fn(async url => url.endsWith('/conectividad') ? ok(base()) : { ok: false, status: 500 }))
  vista = mount(App)
  await flushPromises()
  expect(vista.text()).toContain('API inaccesible')
  expect(vista.text()).toContain('20 %')
})

test('cancela al desmontar y no superpone consultas', async () => {
  vi.useFakeTimers()
  let signal
  const pedir = vi.fn((_, opciones) => { signal = opciones.signal; return new Promise(() => {}) })
  vi.stubGlobal('fetch', pedir)
  vista = mount(Conectividad)
  await vi.advanceTimersByTimeAsync(6000)
  expect(pedir).toHaveBeenCalledTimes(1)
  vista.unmount()
  expect(signal.aborted).toBe(true)
})

test('endpoint ausente o esquema inválido da un error explícito', async () => {
  const pedir = vi.fn().mockResolvedValueOnce({ ok: false, status: 404 }).mockResolvedValueOnce(ok({ version_esquema: 1, datos: { estado: 'activo', destinos: [{}] } }))
  vi.stubGlobal('fetch', pedir)
  await expect(consultarConectividad()).rejects.toThrow('HTTP 404')
  await expect(consultarConectividad()).rejects.toThrow('formato no compatible')
})

test('historial sustituye ventanas sin duplicar; conserva errores y no convierte null en cero', async () => {
  vi.useFakeTimers()
  const dato = base()
  dato.datos.capacidad_series = 100
  dato.datos.retencion_s = 600
  dato.datos.historial = [
    { id_serie: 'primera', destinos: [fila()] },
    { id_serie: 'segunda', destinos: [{ ...fila(), calidad: 'no_disponible', respuestas: 0,
      errores: 5, sin_respuesta: 0, rtt_ms: { promedio: null } }] },
  ]
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(Conectividad)
  await flushPromises()
  const historial = () => vista.findAll('.historial-icmp tbody tr')
  expect(historial()).toHaveLength(2)
  expect(historial()[0].text()).toContain('Sin medición utilizable')
  expect(historial()[0].text()).toContain('No disponible')
  expect(vista.get('.historial-icmp [role="region"]').attributes('tabindex')).toBe('0')
  await vi.advanceTimersByTimeAsync(5000)
  expect(historial()).toHaveLength(2)
  dato.datos.historial = [dato.datos.historial[1]]
  await vi.advanceTimersByTimeAsync(5000)
  expect(historial()).toHaveLength(1)
  dato.datos.historial = []
  dato.datos.id_contexto = 'B'
  await vi.advanceTimersByTimeAsync(5000)
  expect(historial()).toHaveLength(0)
})

test('presenta recuentos del backend sin sumarlos otra vez y retira incidencias expiradas', async () => {
  vi.useFakeTimers()
  const dato = base()
  dato.datos.resumen_ventana = [{ tipo: 'router', destino: '192.0.2.1', series: 2,
    programadas: 10, realizadas: 9, respuestas: 7, sin_respuesta: 1, errores: 1, omitidas: 1,
    series_con_silencios: 1, series_con_errores_u_omisiones: 1, series_sin_incidencias: 1,
    respuesta_completa_posterior: true }]
  const pedir = vi.fn(async () => ok(dato))
  vi.stubGlobal('fetch', pedir)
  vista = mount(Conectividad)
  await flushPromises()
  expect(vista.get('.resumen-icmp').text()).toContain('7 respuestas de 9 sondas realizadas')
  expect(vista.get('.resumen-icmp').text()).toContain('Errores: 1. Omitidas: 1')
  expect(vista.get('.resumen-icmp').text()).toContain('Hubo incidencias anteriores')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.resumen-icmp').text()).toContain('7 respuestas de 9 sondas realizadas')
  pedir.mockRejectedValueOnce(new Error('API inaccesible'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.resumen-icmp').text()).toContain('Resumen conservado sin actualizar')
  dato.datos.resumen_ventana = []
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.find('.resumen-icmp').exists()).toBe(false)
})
