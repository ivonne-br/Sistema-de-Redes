// La vista principal consulta solo el router; no monta los monitores anteriores.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'
import { consultarResumen } from '../src/api.js'

const ok = dato => ({ ok: true, json: async () => dato })
const base = () => ({ version_esquema: 1, datos: {
  autorizada: false, estado: 'requiere_autorizacion', gateway_candidato: '192.168.50.1',
  id_contexto: 'artificial', tablas: {}, series: [],
} })
let vista
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/') })

test('solo monta el panel del router y consulta su API incluso con la URL antigua de diagnóstico', async () => {
  vi.useFakeTimers()
  window.history.replaceState({}, '', '/?diagnostico=1')
  const consulta = vi.fn(async () => ok(base()))
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('h2').map(n => n.text())).toEqual(['Dispositivos y tráfico del router'])
  expect(consulta.mock.calls.map(([ruta]) => ruta)).toEqual(['/api/v1/router', '/api/v1/router'])
  expect(vista.text()).not.toContain('API accesible')
  expect(vista.text()).not.toContain('vecinos han respondido')
})

test('el fallo y la recuperación se muestran dentro del panel de dispositivos', async () => {
  vi.useFakeTimers()
  const consulta = vi.fn().mockRejectedValueOnce(new Error('Sin conexión')).mockResolvedValue(ok(base()))
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  expect(vista.text()).toContain('Sin conexión')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('Sin conexión')
  expect(vista.text()).toContain('Hace falta autorizar la lectura')
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
