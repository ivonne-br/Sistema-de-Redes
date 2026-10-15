// Comprueba distribución persistente, arrastre y controles de teclado con slots
// sintéticos: no consulta la red ni guarda datos de equipos o autorizaciones.
import { afterEach, expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Paneles from '../src/components/Paneles.vue'
let vista
const catalogo = [{ id: 'a', titulo: 'Internet' }, { id: 'b', titulo: 'Respuesta' }]
const crear = () => mount(Paneles, { props: { catalogo }, slots: { a: '<p>Medición A</p>', b: '<p>Medición B</p>' } })
afterEach(() => { vista?.unmount(); localStorage.clear(); vi.restoreAllMocks() })

test('mueve con botones, cambia ancho, oculta y restaura preferencias sin desmontar los datos', async () => {
  vista = crear()
  await vista.get('button').trigger('click')
  await vista.get('[aria-label="Mover Respuesta antes"]').trigger('click')
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['b', 'a'])
  await vista.get('[data-panel="b"] select').setValue('completo')
  await vista.findAll('input[type=checkbox]')[0].setValue(false)
  expect(vista.get('[data-panel="b"]').isVisible()).toBe(false)
  expect(vista.text()).toContain('Medición B')
  const guardado = JSON.parse(localStorage.getItem('red-paneles-v1'))
  expect(guardado).toEqual([{ id: 'b', visible: false, ancho: 'completo' }, { id: 'a', visible: true, ancho: 'medio' }])
  vista.unmount(); vista = crear()
  expect(vista.get('[data-panel="b"]').isVisible()).toBe(false)
  await vista.get('button').trigger('click')
  await vista.findAll('button').find(b => b.text() === 'Restablecer distribución').trigger('click')
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['a', 'b'])
  expect(vista.get('[data-panel="b"]').element.style.display).not.toBe('none')
})

test('arrastra un panel propio e ignora arrastres externos', async () => {
  vista = crear()
  await vista.get('button').trigger('click')
  await vista.get('[data-panel="a"]').trigger('drop')
  expect(vista.findAll('[data-panel]')[0].attributes('data-panel')).toBe('a')
  await vista.get('[aria-label="Mover Internet"]').trigger('dragstart', { dataTransfer: { setData: vi.fn() } })
  await vista.get('[data-panel="b"]').trigger('drop')
  expect(vista.findAll('[data-panel]')[0].attributes('data-panel')).toBe('b')
})

test('preferencias dañadas y almacenamiento bloqueado no impiden utilizar paneles', async () => {
  localStorage.setItem('red-paneles-v1', '[{"id":"a"},{"id":"a"}]')
  vista = crear()
  expect(vista.findAll('[data-panel]')).toHaveLength(2)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Bloqueado') })
  await vista.get('button').trigger('click')
  await vista.get('[aria-label="Mover Respuesta antes"]').trigger('click')
  expect(vista.findAll('[data-panel]')[0].attributes('data-panel')).toBe('b')
  expect(vista.text()).toContain('no permite guardarla')
})
