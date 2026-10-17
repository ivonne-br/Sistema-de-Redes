// Entradas: API artificial. Comprueba identificación, autorización y privacidad de Router.vue sin red real.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Router from '../src/components/Router.vue'

let vista
afterEach(() => { localStorage.clear(); vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })
const ok = datos => ({ ok: true, json: async () => datos })
test('una lectura del backend no concede acceso a una vista sin clave', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ok({ version_esquema: 1, datos: {
    autorizada: false, estado: 'lectura_correcta', tablas: {}, series: [],
  } })))
  vista = mount(Router)
  await flushPromises()
  expect(vista.text()).toContain('Esta vista no tiene acceso autorizado')
  expect(vista.text()).toContain('máximo 30 minutos')
  expect(vista.text()).not.toContain('Último ciclo de lectura correcto')
  expect(vista.find('table').exists()).toBe(false)
})
test('envía credenciales solo al endpoint local y limpia el formulario', async () => {
  const consulta = vi.fn(async (_, opciones) => opciones.method === 'POST'
    ? ok({ clave: 'local' }) : ok({ version_esquema: 1, datos: {
      autorizada: false, id_contexto: 'A', gateway_candidato: '192.168.50.1', identificacion: { adaptador: 'sercomm', nombre: 'Panel de prueba' }, tablas: {}, series: [] } }))
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
    gateway_candidato: '192.168.50.1', identificacion: { adaptador: 'sercomm', nombre: 'Panel de prueba' }, tablas: {}, series: [] }
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
    antiguedad_s: [45, 40, 35, 5][i], fecha: new Date(inicio - [40000, 35000, 30000, 0][i]).toISOString(), bajada_mbps: valor, subida_mbps: valor }))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('svg line')).toHaveLength(3) // eje y un segmento por dirección
  await vista.findAll('.evolucion select')[2].setValue('tabla')
  expect(vista.text()).toContain('No disponible')
})

test('oculta el inventario al alcanzar el límite local aunque la API siga autorizada', async () => {
  await preparar()
  await vi.advanceTimersByTimeAsync(1800000)
  expect(vista.text()).not.toContain('Equipo de prueba')
  expect(vista.text()).toContain('Acceso caducado')
})

test('restaura una sesión HttpOnly al montar sin login y respeta su tiempo restante', async () => {
  vi.useFakeTimers()
  const consulta = vi.fn(async () => ok({ version_esquema: 1, datos: {
    estado: 'lectura_correcta', autorizada: true, restante_s: 2,
    tablas: { 'dhcp-json': { fecha: new Date().toISOString(), recuento: { total: 1 },
      equipos: [{ nombre: 'Equipo restaurado', ipv4: '192.0.2.2', mac: '02:00:00:00:00:01' }] } }, series: [],
  } }))
  vi.stubGlobal('fetch', consulta)
  vista = mount(Router)
  await flushPromises()
  expect(vista.text()).toContain('Equipo restaurado')
  expect(consulta).toHaveBeenCalledTimes(1)
  expect(consulta.mock.lastCall[1].credentials).toBe('same-origin')
  expect(consulta.mock.lastCall[1].headers).toEqual({})
  await vi.advanceTimersByTimeAsync(2000)
  expect(vista.text()).not.toContain('Equipo restaurado')
})

test('cerrar una sesión cookie no permite que una consulta tardía restaure la vista', async () => {
  vi.useFakeTimers()
  const consulta = vi.fn(async (_, opciones) => {
    if (opciones.method === 'DELETE') throw new Error('Respuesta perdida')
    return ok({ version_esquema: 1, datos: { estado: 'lectura_correcta', autorizada: true,
      restante_s: 600, tablas: {}, series: [] } })
  })
  vi.stubGlobal('fetch', consulta)
  vista = mount(Router)
  await flushPromises()
  await vista.get('button').trigger('click')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('Finalizar acceso de lectura')
  expect(vista.text()).toContain('no se confirmó la retirada')
})


test('filtra equipos sin guardar identidades ni hacer consultas nuevas', async () => {
  const { consulta } = await preparar()
  const n = consulta.mock.calls.length
  await vista.get('input[type=search]').setValue('no-coincide')
  expect(vista.text()).toContain('No hay coincidencias')
  expect(vista.text()).not.toContain('Equipo de prueba')
  await vista.get('input[type=search]').setValue('Equipo')
  expect(vista.text()).toContain('Equipo de prueba')
  expect(consulta).toHaveBeenCalledTimes(n)
  expect(JSON.stringify(localStorage)).not.toContain('Equipo')
})


test('presenta cantidades parciales por conexión y las retira al perder acceso', async () => {
  const { datos, consulta } = await preparar()
  datos.resumen_trafico = [{ fuente: 'wan-prueba', familia_ip: 'IPv4', interfaz: 'prueba',
    recibidos_mb: 2, enviados_mb: 1, total_mb: 3, segundos_medidos: 5, intervalos_validos: 1,
    intervalos_excluidos: 1, antiguedad_s: 30, ultima_fecha: new Date().toISOString() }]
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('3 MB')
  expect(vista.text()).toContain('5 segundos medidos')
  expect(vista.text()).toContain('La última lectura es antigua')
  datos.resumen_trafico[0].total_mb = null
  datos.resumen_trafico[0].intervalos_validos = 0
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Todavía no hay dos lecturas comparables')
  consulta.mockRejectedValueOnce(new Error('Sin servicio'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('¿Cuántos datos pasaron')
})


test('un periodo común actualiza cantidades y gráficas sin repetir consultas', async () => {
  const { datos, consulta } = await preparar()
  const resumen = total => [{ fuente: 'wan', familia_ip: 'IPv4', interfaz: 'prueba', total_mb: total,
    recibidos_mb: total, enviados_mb: 0, segundos_medidos: 5, segundos_sin_medicion: 55,
    intervalos_validos: 1, intervalos_excluidos: 0, antiguedad_s: 0, ultima_fecha: new Date().toISOString() }]
  datos.trafico_por_periodo = { '60': resumen(1), '300': resumen(2), '600': resumen(3) }
  datos.series = [{ familia_ip: 'IPv4', interfaz: 'prueba', fecha: new Date().toISOString(),
    antiguedad_s: 10, bajada_mbps: 1, subida_mbps: 0 }]
  await vi.advanceTimersByTimeAsync(5000)
  const n = consulta.mock.calls.length
  expect(vista.text()).toContain('3 MB')
  await vista.get('[data-periodo-trafico]').setValue('60')
  expect(vista.text()).toContain('1 MB')
  expect(vista.text()).not.toContain('3 MB')
  expect(vista.findAll('.evolucion select')[0].element.value).toBe('60')
  expect(vista.text()).toContain('55 segundos del periodo sin medición')
  await vista.findAll('.evolucion select')[0].setValue('300')
  expect(vista.get('[data-periodo-trafico]').element.value).toBe('300')
  expect(vista.text()).toContain('2 MB')
  expect(consulta).toHaveBeenCalledTimes(n)
  expect(localStorage.getItem('red-trafico-periodo-v1')).toBe('300')
  datos.trafico_por_periodo['300'] = []
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('No hay cantidades disponibles')
  expect(vista.text()).not.toContain('2 MB')
})


test('el diagnóstico autorizado desaparece si falla la consulta o se retira el acceso', async () => {
  const { datos, consulta } = await preparar()
  datos.diagnostico = { estado: 'insuficiente', comparaciones: [], mensaje: 'Esperando periodos compatibles.',
    siguiente_paso: 'Se actualiza automáticamente.', consumo_individual: 'No disponible por dispositivo.' }
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Esperando periodos compatibles')
  consulta.mockRejectedValueOnce(new Error('falló'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).not.toContain('Esperando periodos compatibles')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Esperando periodos compatibles')
  await vista.findAll('button').find(b => b.text() === 'Finalizar acceso de lectura').trigger('click')
  await flushPromises()
  expect(vista.text()).not.toContain('Esperando periodos compatibles')
})

test('un router desconocido conserva la consulta general sin habilitar credenciales', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ok({ version_esquema: 1, datos: {
    autorizada: false, estado: 'requiere_autorizacion', tablas: {}, series: [],
    gateway_candidato: '192.168.50.1', identificacion: { adaptador: null, nombre: 'Sin identificar' },
  } })))
  vista = mount(Router); await flushPromises()
  expect(vista.text()).toContain('Conectar mi router')
  expect(vista.text()).toContain('comprobaciones generales')
  expect(vista.get('fieldset').attributes('disabled')).toBeDefined()
})
