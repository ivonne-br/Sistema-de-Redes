// Comprueba distribución persistente, arrastre y controles de teclado con slots
// sintéticos: no consulta la red ni guarda datos de equipos o autorizaciones.
import { afterEach, expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Paneles from '../src/components/Paneles.vue'
let vista
const catalogo = [{ id: 'a', titulo: 'Internet' }, { id: 'b', titulo: 'Respuesta' }]
const crear = () => mount(Paneles, { props: { catalogo }, slots: { a: '<p>Medición A</p>', b: '<p>Medición B</p>' } })
afterEach(() => { vista?.unmount(); localStorage.clear(); vi.restoreAllMocks() })

test('añadir un panel conserva el orden, tamaño y ocultación anteriores', () => {
  localStorage.setItem('red-paneles-v1', JSON.stringify([{ id: 'b', visible: false, ancho: 'completo' }]))
  vista = crear()
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['b', 'a'])
  expect(vista.get('[data-panel="b"]').element.style.display).toBe('none')
  expect(vista.get('[data-panel="b"]').classes()).toContain('completo')
})

test('mueve con botones, cambia ancho, oculta y restaura preferencias sin desmontar los datos', async () => {
  vista = crear()
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.get('[aria-label="Mover Respuesta antes"]').trigger('click')
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['b', 'a'])
  await vista.get('[data-panel="b"] select').setValue('completo')
  await vista.findAll('input[type=checkbox]')[0].setValue(false)
  expect(vista.get('[data-panel="b"]').isVisible()).toBe(false)
  expect(vista.text()).toContain('Medición B')
  const guardado = JSON.parse(localStorage.getItem('red-paneles-v1'))
  expect(guardado).toEqual([{ id: 'b', visible: false, ancho: 'completo', alto: 'automatico' }, { id: 'a', visible: true, ancho: 'medio', alto: 'automatico' }])
  vista.unmount(); vista = crear()
  expect(vista.get('[data-panel="b"]').isVisible()).toBe(false)
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.findAll('button').find(b => b.text() === 'Restablecer distribución').trigger('click')
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['a', 'b'])
  expect(vista.get('[data-panel="b"]').element.style.display).not.toBe('none')
})

test('arrastra un panel propio e ignora arrastres externos', async () => {
  vista = crear()
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
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
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.get('[aria-label="Mover Respuesta antes"]').trigger('click')
  expect(vista.findAll('[data-panel]')[0].attributes('data-panel')).toBe('b')
  expect(vista.text()).toContain('no permite guardarla')
})


test('conserva preferencias antiguas al añadir paneles y descarta campos ajenos', async () => {
  localStorage.setItem('red-paneles-v1', JSON.stringify([
    { id: 'b', visible: false, ancho: 'completo', campoAjeno: 'no-conservar' },
    { id: 'retirado', visible: true, ancho: 'medio' },
  ]))
  vista = crear()
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['b', 'a'])
  expect(vista.get('[data-panel=b]').isVisible()).toBe(false)
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.get('[data-panel=a] select').setValue('completo')
  const guardado = JSON.parse(localStorage.getItem('red-paneles-v1'))
  expect(guardado[0]).toEqual({ id: 'b', visible: false, ancho: 'completo', alto: 'automatico' })
  expect(JSON.stringify(guardado)).not.toContain('campoAjeno')
  expect(JSON.stringify(guardado)).not.toContain('retirado')
})

test('vistas preparadas y accesos conservan componentes, orden y tamaños', async () => {
  vista = mount(Paneles, { props: { catalogo, vistas: [{ id: 'solo', titulo: 'Solo Internet', paneles: ['a'] }] },
    slots: { a: '<input value="dato-temporal" />', b: '<p>Medición B</p>' }, attachTo: document.body })
  const entrada = vista.get('[data-panel=a] input').element
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.get('[aria-label="Mover Respuesta antes"]').trigger('click')
  await vista.findAll('button').find(b => b.text() === 'Solo Internet').trigger('click')
  expect(vista.get('[data-panel=b]').isVisible()).toBe(false)
  expect(vista.get('[data-panel=a] input').element).toBe(entrada)
  await vista.get('nav').findAll('button')[1].trigger('click')
  expect(vista.get('[data-panel=b]').isVisible()).toBe(true)
  expect(document.activeElement.id).toBe('panel-b')
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['b', 'a'])
})

test('altura accesible se guarda, vuelve al recargar y se restablece', async () => {
  vista = crear()
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.get('[data-panel=a]').findAll('select')[1].setValue('compacto')
  expect(vista.get('#panel-a').classes()).toContain('alto-compacto')
  expect(vista.get('#panel-a').attributes('tabindex')).toBe('0')
  vista.unmount(); vista = crear()
  expect(vista.get('#panel-a').classes()).toContain('alto-compacto')
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.findAll('button').find(b => b.text() === 'Restablecer distribución').trigger('click')
  expect(vista.get('#panel-a').classes()).toContain('alto-automatico')
})

test('la guía esencial ignora ocultación y altura guardadas sin borrar preferencias', async () => {
  const previo = [{ id: 'b', visible: true, ancho: 'medio', alto: 'automatico' },
    { id: 'a', visible: false, ancho: 'medio', alto: 'compacto' }]
  localStorage.setItem('red-paneles-v1', JSON.stringify(previo))
  vista = mount(Paneles, { props: { catalogo: [{ ...catalogo[0], esencial: true }, catalogo[1]],
    vistas: [{ id: 'b', titulo: 'Solo apoyo', paneles: ['b'] }] },
    slots: { a: '<p>Guía esencial</p>', b: '<p>Apoyo</p>' } })
  expect(vista.findAll('[data-panel]').map(p => p.attributes('data-panel'))).toEqual(['a', 'b'])
  expect(vista.get('[data-panel=a]').isVisible()).toBe(true)
  expect(vista.get('#panel-a').classes()).not.toContain('alto-compacto')
  expect(JSON.parse(localStorage.getItem('red-paneles-v1'))).toEqual(previo)
  await vista.get('[aria-controls=opciones-paneles]').trigger('click')
  await vista.findAll('button').find(b => b.text() === 'Solo apoyo').trigger('click')
  expect(vista.get('[data-panel=a]').isVisible()).toBe(true)
  expect(JSON.parse(localStorage.getItem('red-paneles-v1'))[1]).toEqual(previo[1])
})
