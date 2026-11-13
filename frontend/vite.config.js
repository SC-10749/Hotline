import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { backendStatus } from './backend-status.js'

// Dev server proxies every backend route so the page and the API share one
// origin (same as the fused single-service mode, where FastAPI serves dist/).
const backendPort = process.env.HOTLINE_JAVA_PORT || '8080'
const backend = `http://127.0.0.1:${backendPort}`
const backendRoutes = [
  '/api', '/health', '/file', '/document', '/skill', '/session', '/agent',
  '/execution', '/evaluation', '/release', '/harness', '/code-map', '/doc-asset', '/generated', '/console', '/docs', '/openapi.json', '/favicon.ico',
]

export default defineConfig({
  plugins: [vue(), backendStatus(backend)],
  build: {
    ...(process.argv.includes('--watch') ? { emptyOutDir: false } : {}),
  },
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: Object.fromEntries(backendRoutes.map(route => [route, { target: backend, changeOrigin: false }])),
  },
})
