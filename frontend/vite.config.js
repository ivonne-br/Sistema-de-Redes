// Recibe API_PUERTO y sirve Vue en loopback; valida peticiones antes de enviarlas a Python.
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const puerto = Number(process.env.API_PUERTO ?? 8000)
if (!Number.isInteger(puerto) || puerto < 1 || puerto > 65535) throw new Error('API_PUERTO debe ser un puerto entre 1 y 65535.')
const destino = `http://127.0.0.1:${puerto}`

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true, cors: false,
    proxy: {
      '/api': {
        target: destino, changeOrigin: true,
        bypass(req, res) {
          const host = req.headers.host
          const origen = req.headers.origin
          if (!['127.0.0.1:5173', 'localhost:5173'].includes(host)
              || (origen !== undefined && origen !== `http://${host}`)
              || req.headers['sec-fetch-site'] === 'cross-site') {
            res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' })
            res.end('Origen local no permitido.')
            return false
          }
          // Solo después de validar el origen local, se adapta al origen del backend.
          if (origen !== undefined) req.headers.origin = destino
        },
      },
    },
  },
  test: { environment: 'jsdom', clearMocks: true },
})
