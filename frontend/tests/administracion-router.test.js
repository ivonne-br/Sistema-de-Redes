// Entradas: API y reloj simulados. Verifica consentimiento, secretos y confirmación
// en AdministracionRouter sin conectar con la red ni guardar ajustes privados.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AdministracionRouter from '../src/components/AdministracionRouter.vue'
let vista
const respuesta = datos => ({ ok: true, json: async () => ({ version_esquema: 1, datos }) })
const config = { wifi: [{ banda: '2.4', nombre: 'Red de prueba', activa: true }], bloqueo: { activo: '1', lista: [{ macfilter_name: 'Consola', macfilter_mac: '02:00:00:00:00:04' }] }, avisos: [] }
const boton = texto => vista.findAll('button').find(b => b.text() === texto)
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear() })
async function preparar() {
  vi.useFakeTimers()
  const fetch = vi.fn(async url => {
    if (url.endsWith('/autorizar')) return respuesta({ autorizada: true, restante_s: 300 })
    if (url.endsWith('/consultar')) return respuesta(config)
    if (url.endsWith('/preparar')) return respuesta({ id: 'plan-artificial', resumen: 'Cambiar contraseña de Red de prueba', efecto: 'Puede desconectar los equipos.', restante_s: 60 })
    return respuesta({ id: 'plan-artificial', estado: 'incierto', resumen: 'Cambio solicitado' })
  })
  vi.stubGlobal('fetch', fetch)
  vista = mount(AdministracionRouter, { props: { contexto: 'red-A', clave: 'clave-local', estado: { autorizada: false } } })
  expect(fetch).not.toHaveBeenCalled()
  expect(boton('Autorizar administración').attributes('disabled')).toBeDefined()
  await vista.get('input[type=checkbox]').setValue(true)
  await vista.get('form').trigger('submit'); await flushPromises()
  return fetch
}
test('la lectura no concede escritura; preparar no confirma y limpia contraseña', async () => {
  const fetch = await preparar()
  await vista.findAll('select')[0].setValue('password')
  await vista.get('input[type=password]').setValue('ClaveNuevaArtificial')
  await vista.get('form').trigger('submit'); await flushPromises()
  expect(vista.text()).not.toContain('ClaveNuevaArtificial')
  expect(localStorage.length).toBe(0)
  expect(fetch.mock.calls.filter(([u]) => u.endsWith('/confirmar'))).toHaveLength(0)
  expect(boton('Aplicar cambio confirmado').attributes('disabled')).toBeDefined()
  await vista.get('input[type=checkbox]').setValue(true)
  await boton('Aplicar cambio confirmado').trigger('click'); await flushPromises()
  const envio = fetch.mock.calls.find(([u]) => u.endsWith('/confirmar'))[1]
  expect(JSON.parse(envio.body)).toEqual({ id: 'plan-artificial', confirmado: true })
  expect(envio.headers['X-Red-Accion']).toBe('administrar-router')
  expect(vista.text()).toContain('podría haberse aplicado')
  expect(vista.text()).not.toContain('El router informa la configuración solicitada')
  expect(boton('Aplicar cambio confirmado')).toBeUndefined()
})
test('caducidad y cambio de red eliminan el plan y los secretos', async () => {
  await preparar()
  await vista.findAll('select')[0].setValue('nombre')
  await vista.get('input[maxlength="32"]').setValue('Nombre nuevo')
  await vista.get('form').trigger('submit'); await flushPromises()
  await vista.get('input[type=checkbox]').setValue(true)
  await vi.advanceTimersByTimeAsync(61000)
  expect(boton('Aplicar cambio confirmado').attributes('disabled')).toBeDefined()
  await vista.setProps({ contexto: 'red-B' })
  expect(boton('Aplicar cambio confirmado')).toBeUndefined()
  expect(boton('Autorizar administración')).toBeDefined()
})
test('permite elegir una regla aunque no exista inventario de conectados', async () => {
  const fetch = await preparar()
  await vista.findAll('select')[0].setValue('desbloquear')
  await vista.findAll('select')[1].setValue('02:00:00:00:00:04')
  await vista.get('form').trigger('submit'); await flushPromises()
  expect(JSON.parse(fetch.mock.calls.find(([u]) => u.endsWith('/preparar'))[1].body))
    .toEqual({ operacion: 'desbloquear', mac: '02:00:00:00:00:04' })
})
