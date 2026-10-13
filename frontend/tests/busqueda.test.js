// Sondas simuladas entran como props; verifica texto accesible, antigüedad y reemplazo sin peticiones reales.
import { expect, test } from 'vitest'
import { mount } from '@vue/test-utils'
import BusquedaLocal from '../src/components/BusquedaLocal.vue'

test('separa silencio, error, respuesta y dato antiguo; no afirma desconexión', async () => {
  const vista = mount(BusquedaLocal, { props: { asociaciones: [{ ipv4: '192.168.0.85' }], busqueda: {
    estado: 'en_espera', consultados: 252, destinos_total: 252, intervalo_s: 60,
    resultados: [
      { ipv4: '192.168.0.85', estado: 'sin_respuesta', antiguedad_s: 2 },
      { ipv4: '192.168.0.120', estado: 'respuesta_valida', respondio_alguna_vez: true, antiguedad_s: 181, vigencia: 'desactualizado' },
      { ipv4: '192.168.0.94', estado: 'error_recoleccion', respondio_alguna_vez: true, antiguedad_s: null },
      { ipv4: '192.168.0.200', estado: 'sin_respuesta' },
    ],
  } } })
  expect(vista.findAll('tbody tr')).toHaveLength(3)
  expect(vista.text()).toContain('Sin respuesta a ICMP')
  expect(vista.text()).toContain('Error de comprobación')
  expect(vista.text()).toContain('Comprobación antigua')
  expect(vista.text()).toContain('no confirma desconexión')
  expect(vista.get('[role="region"]').attributes('tabindex')).toBe('0')
  await vista.setProps({ asociaciones: [], busqueda: { estado: 'esperando_contexto', resultados: [] } })
  expect(vista.findAll('tbody tr')).toHaveLength(0)
  vista.unmount()
})

test('API anterior y subred omitida tienen explicaciones visibles', async () => {
  const vista = mount(BusquedaLocal)
  expect(vista.text()).toContain('Reinicia Python')
  await vista.setProps({ busqueda: { estado: 'omitida', detalle: 'La subred supera 256 direcciones.', resultados: [] } })
  expect(vista.text()).toContain('Búsqueda omitida')
  expect(vista.text()).toContain('La subred supera 256')
  vista.unmount()
})

test('la tabla principal exige respuesta reciente; silencio, caducidad y fallo HTTP la retiran', async () => {
  const fila = { ipv4: '192.168.0.120', estado: 'respuesta_valida', respondio_alguna_vez: true, vigencia: 'vigente', antiguedad_s: 2 }
  const busqueda = { estado: 'en_espera', vigencia_s: 180, resultados: [fila] }
  const vista = mount(BusquedaLocal, { props: { busqueda } })
  expect(vista.findAll('.recientes tbody tr')).toHaveLength(1)
  expect(vista.get('details').attributes('open')).toBeUndefined()
  await vista.setProps({ busqueda: { ...busqueda, resultados: [{ ...fila, estado: 'sin_respuesta' }] } })
  expect(vista.findAll('.recientes tbody tr')).toHaveLength(0)
  expect(vista.findAll('details tbody tr')).toHaveLength(1)
  await vista.setProps({ busqueda: { ...busqueda, resultados: [{ ...fila, vigencia: 'desactualizado', antiguedad_s: 181 }] } })
  expect(vista.findAll('.recientes tbody tr')).toHaveLength(0)
  await vista.setProps({ busqueda, actualizada: false })
  expect(vista.findAll('.recientes tbody tr')).toHaveLength(0)
  expect(vista.text()).toContain('No hay datos actuales')
  await vista.setProps({ actualizada: true })
  expect(vista.findAll('.recientes tbody tr')).toHaveLength(1)
  vista.unmount()
})
