import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev server proxies every backend route so the page and the API share one
// origin (same as the fused single-service mode, where FastAPI serves dist/).
const backendPort = process.env.DODO_DEV_BACKEND_PORT || '8888'
const backend = `http://127.0.0.1:${backendPort}`
const backendRoutes = [
  '/health', '/file', '/document', '/skill', '/session', '/agent',
  '/doc-asset', '/generated', '/console', '/docs', '/openapi.json', '/favicon.ico',
]

export default defineConfig({
  plugins: [vue()],
  // Watched rebuilds (hot-deploy mode) must not empty dist: the rmtree races
  // with transient Windows locks (Defender/open handles) and dies with EPERM.
  // Stale hashed assets are harmless; a normal `npm run build` cleans them.
  build: process.argv.includes('--watch') ? { emptyOutDir: false } : {},
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: Object.fromEntries(backendRoutes.map(route => [route, { target: backend, changeOrigin: false }])),
  },
})
