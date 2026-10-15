// Series sintéticas: periodos, huecos, cero real, accesibilidad y preferencias sin datos.
import { afterEach, expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Evolucion from '../src/components/Evolucion.vue'
let vista
const puntos = [100, 90, 80, 70, 20].map((edad, i) => ({ edad, fecha: '2026-10-15T12:00:00Z', valor: [1, 0, null, 3, 4][i] }))
const crear = () => mount(Evolucion, { props: { titulo: 'Prueba', unidad: 'ms', preferencia: 'prueba', hueco: 20,
  series: [{ id: 'privado', nombre: 'Destino privado', puntos }] } })
afterEach(() => { vista?.unmount(); localStorage.clear(); vi.restoreAllMocks() })
test('no une huecos, conserva cero y presenta puntos aislados', () => {
  vista = crear()
  expect(vista.findAll('svg line')).toHaveLength(2) // eje y único intervalo válido
  expect(vista.findAll('circle')).toHaveLength(4)
  expect(vista.text()).toContain('no significan cero')
})
test('filtra periodo y serie y ofrece tabla y valores sin tratar null como cero', async () => {
  vista = crear()
  await vista.findAll('select')[2].setValue('tabla')
  expect(vista.text()).toContain('No disponible')
  expect(vista.text()).toContain('0 ms')
  await vista.findAll('select')[0].setValue('60')
  expect(vista.findAll('tbody tr')).toHaveLength(1)
  await vista.findAll('select')[2].setValue('valores')
  expect(vista.get('dd').text()).toBe('4 ms')
  await vista.findAll('select')[1].setValue('privado')
  await vista.setProps({ series: [{ id: 'otra', nombre: 'Otra red', puntos: [] }] })
  expect(vista.findAll('select')[1].element.value).toBe('')
  expect(vista.text()).toContain('No hay valores disponibles')
})
test('guarda solo periodo y vista y tolera almacenamiento bloqueado', async () => {
  vista = crear()
  await vista.findAll('select')[2].setValue('tabla')
  expect(JSON.parse(localStorage.getItem('red-grafica-prueba-v1'))).toEqual({ periodo: 300, vista: 'tabla' })
  vista.unmount(); vista = crear()
  expect(vista.find('table').exists()).toBe(true)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado') })
  await vista.findAll('select')[0].setValue('60')
  expect(vista.text()).toContain('no permite guardarlos')
})
test('excluye edades fuera de ventana y valores inválidos sin recuperar un valor anterior como último', async () => {
  vista = crear()
  await vista.setProps({ series: [{ id: 'a', nombre: 'A', puntos: [
    { edad: -1, valor: 9 }, { edad: 300, valor: 10 }, { edad: 20, valor: 4 }, { edad: 10, valor: null },
  ] }] })
  await vista.findAll('select')[2].setValue('valores')
  expect(vista.get('dd').text()).toBe('No disponible')
  await vista.findAll('select')[2].setValue('tabla')
  expect(vista.findAll('tbody tr')).toHaveLength(2)
})
