// Simula la API DNS/HTTPS y su recuperación; comprueba resultados y recuentos independientes, caducidad del historial y sustitución de contexto sin red pública.
import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ServiciosWeb from '../src/components/ServiciosWeb.vue'
import { consultarWeb } from '../src/api.js'
const base = () => ({ version_esquema: 1, datos: { estado: 'en_espera', id_contexto: 'A',
  intervalo_s: 60, limite_s: 8, vigencia_s: 120, codigo_https_esperado: 204,
  resultados: [
    { tipo: 'dns', destino: 'www.gstatic.com', estado: 'correcto', direcciones: ['192.0.2.1'], duracion_ms: 0, antiguedad_s: 2, vigencia: 'vigente' },
    { tipo: 'https', destino: 'https://www.gstatic.com/generate_204', estado: 'correcto', direcciones: [], codigo_http: 204, duracion_ms: 10, antiguedad_s: 1, vigencia: 'vigente' },
  ] } })
const ok = dato => ({ ok: true, json: async () => structuredClone(dato) })
let vista
afterEach(() => { vista?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })

test('el resumen no presenta éxito antiguo, fallo ni monitor detenido como acceso actual', async () => {
  vi.useFakeTimers()
  const dato = base()
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(ServiciosWeb)
  await flushPromises()
  expect(vista.get('.resultado-principal').text()).toContain('Sí: esta computadora pudo comunicarse')
  dato.datos.resultados[1].vigencia = 'desactualizado'
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.resultado-principal').text()).toContain('antigua')
  dato.datos.resultados[1].vigencia = 'vigente'
  dato.datos.resultados[1].estado = 'tiempo_agotado'
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.resultado-principal').text()).toContain('No confirma una caída')
  dato.datos.resultados[1].estado = 'correcto'
  dato.datos.estado = 'detenido'
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.resultado-principal').text()).not.toContain('Sí: esta computadora pudo comunicarse')
})

test('muestra DNS y HTTPS separados, cero no es ausencia y fallo no es éxito antiguo', async () => {
  vi.useFakeTimers()
  const dato = base()
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(ServiciosWeb)
  expect(vista.text()).toContain('Cargando comprobaciones')
  await flushPromises()
  expect(vista.text()).toContain('0 ms')
  expect(vista.text()).toContain('Código HTTP recibido: 204')
  dato.datos.resultados[0] = { ...dato.datos.resultados[0], estado: 'tiempo_agotado', duracion_ms: null, direcciones: [] }
  await vi.advanceTimersByTimeAsync(5000)
  const filas = vista.findAll('article')
  expect(filas[0].text()).toContain('Tiempo de espera agotado')
  expect(filas[0].text()).toContain('Duración de la operación: No disponible')
  expect(filas[0].text()).not.toContain('192.0.2.1')
  expect(filas[1].text()).toContain('Comprobación correcta')
})

test('HTTP inaccesible congela y recuperación sustituye; contexto perdido elimina datos', async () => {
  vi.useFakeTimers()
  const pedir = vi.fn().mockResolvedValue(ok(base()))
  vi.stubGlobal('fetch', pedir)
  vista = mount(ServiciosWeb)
  await flushPromises()
  pedir.mockRejectedValueOnce(new Error('API inaccesible'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('congelados')
  expect(vista.text()).not.toContain('Dato dentro de vigencia')
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.text()).toContain('Consulta DNS/HTTPS recuperada')
  pedir.mockResolvedValue(ok({ version_esquema: 1, datos: { estado: 'sin_contexto', resultados: [] } }))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.findAll('article')).toHaveLength(0)
})

test('certificado, HTTP inesperado y datos antiguos se muestran explícitos', async () => {
  const dato = base()
  dato.datos.resultados[0].estado = 'error_resolucion'
  dato.datos.resultados[1].estado = 'certificado_invalido'
  dato.datos.resultados[1].vigencia = 'desactualizado'
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(ServiciosWeb)
  await flushPromises()
  expect(vista.text()).toContain('No se pudo resolver el nombre')
  expect(vista.text()).toContain('Certificado TLS no válido')
  expect(vista.text()).toContain('Dato antiguo')
})

test('el componente web consulta únicamente su API independiente', async () => {
  vi.stubGlobal('fetch', vi.fn(async url => url.endsWith('/web') ? ok(base()) : { ok: false, status: 500 }))
  vista = mount(ServiciosWeb)
  await flushPromises()
  expect(vista.text()).toContain('Código HTTP recibido: 204')
})

test('no solapa peticiones y cancela al desmontar', async () => {
  vi.useFakeTimers()
  let signal
  const pedir = vi.fn((_, opciones) => { signal = opciones.signal; return new Promise(() => {}) })
  vi.stubGlobal('fetch', pedir)
  vista = mount(ServiciosWeb)
  await vi.advanceTimersByTimeAsync(6000)
  expect(pedir).toHaveBeenCalledTimes(1)
  vista.unmount()
  expect(signal.aborted).toBe(true)
})

test('valida el contrato antes de renderizar', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: false, status: 404 })
    .mockResolvedValueOnce(ok({ version_esquema: 1, datos: { estado: 'activo', resultados: [{}] } })))
  await expect(consultarWeb()).rejects.toThrow('HTTP 404')
  await expect(consultarWeb()).rejects.toThrow('formato no compatible')
})

test('historial muestra fallo y recuperación, se congela y caduca sin duplicar filas', async () => {
  vi.useFakeTimers()
  const dato = base()
  dato.datos.capacidad_series = 100
  dato.datos.retencion_s = 600
  dato.datos.historial = [
    { id_serie: 'fallo', resultados: [{ ...dato.datos.resultados[0], estado: 'tiempo_agotado', duracion_ms: null }] },
    { id_serie: 'recuperacion', resultados: [dato.datos.resultados[0]] },
  ]
  const pedir = vi.fn(async () => ok(dato))
  vi.stubGlobal('fetch', pedir)
  vista = mount(ServiciosWeb)
  await flushPromises()
  const filas = () => vista.findAll('.historial-web tbody tr')
  expect(filas()).toHaveLength(2)
  expect(filas()[0].text()).toContain('Comprobación correcta')
  expect(filas()[1].text()).toContain('Tiempo de espera agotado')
  expect(filas()[1].text()).toContain('No disponible')
  expect(filas()[0].text()).toContain('No aplica')
  expect(vista.get('.historial-web [role="region"]').attributes('tabindex')).toBe('0')
  await vi.advanceTimersByTimeAsync(5000)
  expect(filas()).toHaveLength(2)
  pedir.mockRejectedValueOnce(new Error('API inaccesible'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.historial-web').text()).toContain('Historial conservado sin actualizar')
  expect(filas()).toHaveLength(2)
  dato.datos.historial = []
  dato.datos.resultados = []
  dato.datos.id_contexto = 'B'
  await vi.advanceTimersByTimeAsync(5000)
  expect(filas()).toHaveLength(0)
})

test('recuentos separados por estado no implican recuperación permanente y se sustituyen', async () => {
  vi.useFakeTimers()
  const dato = base()
  dato.datos.resumen_ventana = [{ tipo: 'dns', destino: 'www.gstatic.com', intentos: 3,
    correctos: 1, no_correctos: 2, por_estado: { tiempo_agotado: 1, error_resolucion: 1, correcto: 1 },
    correcto_posterior: true }]
  const pedir = vi.fn(async () => ok(dato))
  vi.stubGlobal('fetch', pedir)
  vista = mount(ServiciosWeb)
  await flushPromises()
  expect(vista.get('.resumen-web').text()).toContain('1 correctas de 3 comprobaciones')
  expect(vista.get('.resumen-web').text()).toContain('Tiempo de espera agotado: 1')
  expect(vista.get('.resumen-web').text()).toContain('No demuestra una recuperación permanente')
  pedir.mockRejectedValueOnce(new Error('API inaccesible'))
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.get('.resumen-web').text()).toContain('Resumen conservado sin actualizar')
  dato.datos.resumen_ventana = []
  await vi.advanceTimersByTimeAsync(5000)
  expect(vista.find('.resumen-web').exists()).toBe(false)
})

test('un error al ejecutar la prueba no se presenta como fallo del sitio', async () => {
  const dato = base()
  dato.datos.resultados[1].estado = 'error_medicion'
  vi.stubGlobal('fetch', vi.fn(async () => ok(dato)))
  vista = mount(ServiciosWeb)
  await flushPromises()
  expect(vista.get('.resultado-principal').text()).toContain('La aplicación no pudo realizar la prueba')
  expect(vista.get('.resultado-principal').text()).not.toContain('No pudimos comunicarnos')
})
