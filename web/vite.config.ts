/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev proxy: /api -> the FastAPI backend (post_api), so the browser never needs CORS.
const API_PORT = process.env.POST_API_PORT ?? '8000'

// T27 item 3: "reload shows the old UI, almost like it's cached" -- vite dev already sends
// `Cache-Control: no-cache` (revalidate-before-reuse) on served files, but that still lets the
// browser reuse a cached response on a 304, and a stale service worker or aggressive
// intermediary can make a reload look stuck on old code. Force `no-store` on every dev
// response so a reload is always a real network fetch of current code.
function noStoreInDev() {
  return {
    name: 'post3-no-store-dev',
    configureServer(server: import('vite').ViteDevServer) {
      server.middlewares.use((_req, res, next) => {
        res.setHeader('Cache-Control', 'no-store')
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), noStoreInDev()],
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    exclude: ['node_modules', 'dist', 'e2e/**'],
  },
})
