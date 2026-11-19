import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Optional: comma separated hostnames (e.g. an ngrok tunnel) allowed in dev.
  const allowedHosts = (env.VITE_DEV_ALLOWED_HOSTS ?? '')
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean)

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      allowedHosts,
      proxy: {
        '/api': {
          target: env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000',
          changeOrigin: true,
          // /api/health -> /health
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
