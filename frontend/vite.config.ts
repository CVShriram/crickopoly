import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Production serves the built SPA from FastAPI on the same origin. In local
// development, forward API and WebSocket traffic to the backend so the same
// relative paths work in both environments.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
