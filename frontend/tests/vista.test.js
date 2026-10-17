// Recibe HTTP simulado y acciones de pantalla; comprueba guía concisa, recuperación, cierre
// confirmado del iniciador y separación respecto de los permisos del router.
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
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState({}, '', '/'); localStorage.clear() })

test('integra fuentes públicas y router sin autorizar ni consultar ARP al abrir el resumen', async () => {
  vi.useFakeTimers()
  window.history.replaceState({}, '', '/?diagnostico=1')
  const consulta = vi.fn(async ruta => ok(fuentes(ruta)))
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('h2').map(n => n.text())).toEqual(['¿Puedo navegar?', '¿Hay acceso a Internet?', '¿Cuánto tarda en responder?', 'Dispositivos y tráfico del router'])
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
  expect(vista.text()).toContain('Abre «Iniciar Red.command»')
  consulta.mockImplementation(async ruta => ok(fuentes(ruta)))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('No se puede consultar la aplicación')
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


test('elegir vistas solo cambia la presentación y nunca autoriza el router', async () => {
  vi.useFakeTimers()
  const consulta = vi.fn(async ruta => ok(fuentes(ruta)))
  vi.stubGlobal('fetch', consulta)
  vista = mount(App, { attachTo: document.body })
  await flushPromises()
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.findAll('button').find(b => b.text() === 'Consultar equipos y uso').trigger('click')
  expect(vista.get('[data-panel=internet]').isVisible()).toBe(false)
  expect(vista.get('[data-panel=equipos]').isVisible()).toBe(true)
  await vista.get('nav').findAll('button').find(b => b.text() === '¿Puedo abrir páginas?').trigger('click')
  await flushPromises()
  expect(vista.get('[data-panel=internet]').isVisible()).toBe(true)
  expect(consulta).toHaveBeenCalledTimes(5)
  expect(consulta.mock.calls.every(([, opciones]) => !opciones.method)).toBe(true)
  expect(localStorage.getItem('red-paneles-v1')).not.toContain('192.168')
  await vista.findAll('button').find(b => b.text() === 'Revisar mi conexión').trigger('click')
  expect(vista.get('[data-panel=observaciones]').element.style.display).not.toBe('none')
  expect(consulta).toHaveBeenCalledTimes(5)
})

test('cierre requiere confirmación, permite cancelar y detiene las consultas después de aceptar', async () => {
  vi.useFakeTimers()
  const consulta = vi.fn(async (ruta, opciones) => {
    if (ruta === '/api/v1/estado') return ok({ version_esquema: 1, cierre_disponible: true, monitoreo: { estado: 'activo', id_ejecucion: 'sesion-prueba' } })
    if (ruta === '/api/v1/cierre') {
      expect(opciones.method).toBe('POST')
      expect(JSON.parse(opciones.body)).toEqual({ confirmado: true, id_ejecucion: 'sesion-prueba' })
      return { status: 202, json: async () => ({ version_esquema: 1, estado: 'cierre_solicitado' }) }
    }
    return ok(fuentes(ruta))
  })
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  const boton = texto => vista.findAll('button').find(b => b.text() === texto)
  await boton('Cerrar aplicación').trigger('click')
  expect(vista.get('[role=alertdialog]').text()).toContain('No se apagará Internet')
  await boton('Cancelar').trigger('click')
  expect(consulta.mock.calls.filter(([r]) => r === '/api/v1/cierre')).toHaveLength(0)
  await boton('Cerrar aplicación').trigger('click')
  await boton('Confirmar cierre').trigger('click')
  await flushPromises()
  expect(vista.text()).toContain('Cierre solicitado')
  expect(vista.text()).not.toContain('Estado de la aplicación')
  const total = consulta.mock.calls.length
  await vi.advanceTimersByTimeAsync(15000)
  expect(consulta).toHaveBeenCalledTimes(total)
  expect(consulta.mock.calls.filter(([r]) => r === '/api/v1/cierre')).toHaveLength(1)
})

test('un servicio abierto por separado no ofrece cierre y un cierre fallido no se reenvía solo', async () => {
  vi.useFakeTimers()
  let cierreDisponible = false
  const consulta = vi.fn(async ruta => {
    if (ruta === '/api/v1/estado') return ok({ version_esquema: 1, cierre_disponible: cierreDisponible, monitoreo: { estado: 'activo', id_ejecucion: 'sesion-prueba' } })
    if (ruta === '/api/v1/cierre') throw new Error('Sin respuesta')
    return ok(fuentes(ruta))
  })
  vi.stubGlobal('fetch', consulta)
  vista = mount(App)
  await flushPromises()
  const boton = texto => vista.findAll('button').find(b => b.text() === texto)
  expect(boton('Cerrar aplicación')).toBeUndefined()
  expect(vista.text()).toContain('Este servicio se abrió por separado')
  cierreDisponible = true
  await vi.advanceTimersByTimeAsync(5000)
  await boton('Cerrar aplicación').trigger('click')
  await boton('Confirmar cierre').trigger('click')
  await flushPromises()
  expect(vista.text()).toContain('No pudimos confirmar el cierre')
  await vi.advanceTimersByTimeAsync(15000)
  expect(consulta.mock.calls.filter(([r]) => r === '/api/v1/cierre')).toHaveLength(1)
})

test('un router que tarda no bloquea la guía ni la prueba web', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn((ruta, opciones) => {
    if (ruta === '/api/v1/router') return new Promise((_, reject) => {
      opciones.signal.addEventListener('abort', () => reject(new DOMException('Cancelada', 'AbortError')))
    })
    return Promise.resolve(ok(fuentes(ruta)))
  }))
  vista = mount(App)
  await flushPromises()
  expect(vista.get('[data-panel=observaciones]').text()).toContain('Esperando resultados')
  expect(vista.get('[data-panel=internet]').text()).toContain('Sí: esta computadora pudo comunicarse')
  await vi.advanceTimersByTimeAsync(8000)
  expect(vista.get('[data-panel=internet]').text()).toContain('Sí: esta computadora pudo comunicarse')
  expect(vista.get('[data-panel=equipos]').text()).toContain('Datos del router no disponibles')
})
