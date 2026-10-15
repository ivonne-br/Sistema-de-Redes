// Respuestas artificiales: autorización, privacidad y discontinuidades sin red real.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Router from '../src/components/Router.vue'

let vista
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })
const ok = datos => ({ ok: true, json: async () => datos })
test('envía credenciales solo al endpoint local y limpia el formulario', async () => {
  const consulta = vi.fn(async (_, opciones) => opciones.method === 'POST'
    ? ok({ clave: 'local' }) : ok({ version_esquema: 1, datos: {
      autorizada: false, id_contexto: 'A', gateway_candidato: '192.168.50.1', tablas: {}, series: [] } }))
  vi.stubGlobal('fetch', consulta)
  vista = mount(Router)
  await flushPromises()
  await vista.get('input[maxlength="128"]').setValue('usuario artificial')
  await vista.get('input[maxlength="1024"]').setValue('contraseña artificial')
  await vista.findAll('input[type=checkbox]')[1].setValue(true)
  await vista.get('form').trigger('submit')
  await flushPromises()
  const [url, opciones] = consulta.mock.calls.find(([, o]) => o.method === 'POST')
  expect(url).toBe('/api/v1/router/sesion')
  expect(JSON.parse(opciones.body)).toEqual({ usuario: 'usuario artificial', password: 'contraseña artificial', confirmado: true, id_contexto: 'A' })
  expect(vista.get('fieldset').attributes('disabled')).toBeDefined()
  expect(vista.get('input[maxlength="1024"]').element.value).toBe('')
  expect(vista.text()).not.toContain('contraseña artificial')
})

async function preparar() {
  vi.useFakeTimers()
  const datos = { estado: 'requiere_autorizacion', autorizada: false, id_contexto: 'A',
    gateway_candidato: '192.168.50.1', tablas: {}, series: [] }
  const consulta = vi.fn(async (_, opciones) => opciones.method === 'POST'
    ? ok({ clave: 'clave-local-artificial' }) : ok({ version_esquema: 1, datos: structuredClone(datos) }))
  vi.stubGlobal('fetch', consulta)
  vista = mount(Router)
  await flushPromises()
  await vista.get('input[type=checkbox]').setValue(true)
  await vista.findAll('input[type=password]')[0].setValue('session_id=artificial')
  await vista.findAll('input[type=password]')[1].setValue('csrf-artificial')
  await vista.findAll('input[type=checkbox]')[1].setValue(true)
  await vista.get('form').trigger('submit')
  await flushPromises()
  datos.autorizada = true
  datos.tablas['dhcp-json'] = { fecha: new Date().toISOString(), vigencia: 'vigente',
    recuento: { total: 1, activo: 1, inactivo: 0, estado_desconocido: 0 },
    equipos: [{ nombre: 'Equipo de prueba', ipv4: '192.168.50.2', mac: '02:00:00:00:00:01', estado_original: 'Activo' }] }
  await vi.advanceTimersByTimeAsync(5000)
  return { datos, consulta }
}

test('autoriza por contexto, consulta con clave local y oculta datos ante error y revocación', async () => {
  const { consulta } = await preparar()
  expect(vista.text()).toContain('Equipo de prueba')
  const post = consulta.mock.calls.find(([, o]) => o.method === 'POST')[1]
  expect(JSON.parse(post.body).id_contexto).toBe('A')
  expect(consulta.mock.lastCall[1].headers).toEqual({ 'X-Router-Authorization': 'clave-local-artificial' })
  consulta.mockRejectedValueOnce(new Error('Sin conexión'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('Equipo de prueba')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Equipo de prueba')
  await vista.get('button').trigger('click')
  expect(vista.text()).not.toContain('Equipo de prueba')
  expect(consulta.mock.lastCall[1].method).toBe('DELETE')
})

test('cambio de red retira la vista privada y permite autorizar el nuevo contexto', async () => {
  const { datos } = await preparar()
  datos.autorizada = false
  datos.id_contexto = 'B'
  datos.tablas = {}
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('Equipo de prueba')
  expect(vista.find('form').exists()).toBe(true)
})

test('no une tasas nulas ni intervalos largos en la gráfica', async () => {
  const { datos } = await preparar()
  const inicio = Date.now()
  datos.series = [null, 2, 3, 4].map((valor, i) => ({ familia_ip: 'IPv4', interfaz: 'prueba',
    fecha: new Date(inicio - [40000, 35000, 30000, 0][i]).toISOString(), bajada_mbps: valor, subida_mbps: valor }))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('svg line')).toHaveLength(3) // eje y un segmento por dirección
  expect(vista.text()).toContain('Sin intervalo válido')
})

test('oculta el inventario al alcanzar el límite local aunque la API siga autorizada', async () => {
  await preparar()
  await vi.advanceTimersByTimeAsync(900000)
  expect(vista.text()).not.toContain('Equipo de prueba')
  expect(vista.text()).toContain('Acceso caducado')
})
