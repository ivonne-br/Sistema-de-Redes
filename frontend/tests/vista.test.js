// Integra fuentes públicas y router privado con HTTP simulado; verifica independencia, recuperación y ausencia de autorización automática.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'
import { consultarResumen, consultarEstado } from '../src/api.js'

const ok = dato => ({ ok: true, json: async () => dato })
const base = () => ({ version_esquema: 1, datos: {
  autorizada: false, estado: 'requiere_autorizacion', gateway_candidato: '192.168.50.1',
  id_contexto: 'artificial', tablas: {}, series: [],
} })
const fuentes = ruta => {
  if (ruta === '/api/v1/observaciones') return { version_esquema: 1, datos: { estado: 'sin_datos', titulo: 'Esperando resultados', explicacion: 'Faltan comprobaciones', orientacion: 'Espera', limite: 'Solo sitio de prueba', evidencia: [], comparacion: null } }
  if (ruta === '/api/v1/estado') return { version_esquema: 1, monitoreo: { estado: 'activo' } }
  if (ruta === '/api/v1/conectividad') return { version_esquema: 1, datos: { estado: 'midiendo', destinos: [] } }
  if (ruta === '/api/v1/web') return { version_esquema: 1, datos: { estado: 'en_espera', resultados: [
    { tipo: 'https', destino: 'https://example.test', estado: 'correcto', vigencia: 'vigente', direcciones: [], fin: '2026-10-15T12:00:00Z' },
  ] } }
  return base()
}
let vista
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/') })

test('integra fuentes públicas y router sin autorizar ni consultar ARP al abrir el resumen', async () => {
  vi.useFakeTimers()
  window.history.replaceState({}, '', '/?diagnostico=1')
  const consulta = vi.fn(async ruta => ok(fuentes(ruta)))
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('h2').map(n => n.text())).toEqual(['Estado de la aplicación', 'Qué está pasando y qué puedes hacer', '¿Hay acceso a Internet?', '¿Cuánto tarda en responder?', 'Dispositivos y tráfico del router'])
  for (const ruta of ['/api/v1/observaciones', '/api/v1/estado', '/api/v1/web', '/api/v1/conectividad', '/api/v1/router']) {
    expect(consulta.mock.calls.filter(([r]) => r === ruta)).toHaveLength(2)
  }
  expect(consulta.mock.calls).toHaveLength(10)
  expect(consulta.mock.calls.every(([, opciones]) => !opciones.method && !opciones.headers?.['X-Router-Authorization'])).toBe(true)
  expect(vista.text()).toContain('Sí: esta computadora pudo comunicarse')
  expect(vista.text()).toContain('Hace falta autorizar la lectura')
  expect(vista.text()).toContain('Organizar mis paneles')
  expect(vista.text()).not.toContain('vecinos han respondido')
})

test('un fallo del router no oculta la conectividad pública y se recupera por separado', async () => {
  vi.useFakeTimers()
  let fallo = true
  const consulta = vi.fn(async ruta => {
    if (ruta === '/api/v1/router' && fallo) throw new Error('Sin conexión con router')
    return ok(fuentes(ruta))
  })
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  expect(vista.text()).toContain('Sin conexión con router')
  expect(vista.text()).toContain('Sí: esta computadora pudo comunicarse')
  fallo = false
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('Sin conexión con router')
  expect(vista.text()).toContain('Hace falta autorizar la lectura')
})

test('backend inaccesible ofrece recuperación sin diagnosticar caída de Internet', async () => {
  vi.useFakeTimers()
  const consulta = vi.fn().mockRejectedValue(new Error('Sin servicio'))
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  expect(vista.text()).toContain('Esto no demuestra una caída de Internet')
  expect(vista.text()).not.toContain('Sí: esta computadora pudo comunicarse')
  expect(vista.text()).toContain('python -B -m backend servir-api')
  consulta.mockImplementation(async ruta => ok(fuentes(ruta)))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Comunicación con el servicio de medición recuperada')
  expect(vista.text()).toContain('Sí: esta computadora pudo comunicarse')
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
  fetchMock.mockResolvedValueOnce(ok({ version_esquema: 1, monitoreo: {} }))
  await expect(consultarEstado()).rejects.toThrow('estado no compatible')
})
