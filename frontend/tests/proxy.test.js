// Entradas HTTP artificiales verifican que el proxy rechace orígenes ajenos antes de adaptar Host/Origin hacia Python.
import { expect, test, vi } from 'vitest'
import configuracion from '../vite.config.js'

const proxy = configuracion.server.proxy['/api']
test('solo adapta el origen de una petición local validada', () => {
  const req = { headers: { host: '127.0.0.1:5173', origin: 'http://127.0.0.1:5173' } }
  const res = { writeHead: vi.fn(), end: vi.fn() }
  expect(proxy.bypass(req, res)).toBeUndefined()
  expect(req.headers.origin).toBe(proxy.target)
  expect(proxy.changeOrigin).toBe(true)
  expect(res.end).not.toHaveBeenCalled()
  expect(configuracion.server.host).toBe('127.0.0.1')
  expect(configuracion.server.cors).toBe(false)
})
test.each([
  { host: 'externo.test' },
  { host: '127.0.0.1:5173', origin: 'https://externo.test' },
  { host: '127.0.0.1:5173', origin: 'null' },
  { host: '127.0.0.1:5173', 'sec-fetch-site': 'cross-site' },
])('rechaza cabeceras ajenas sin reescribirlas: %j', headers => {
  const originales = { ...headers }
  const res = { writeHead: vi.fn(), end: vi.fn() }
  expect(proxy.bypass({ headers }, res)).toBe(false)
  expect(headers).toEqual(originales)
  expect(res.writeHead).toHaveBeenCalledWith(403, expect.any(Object))
})
