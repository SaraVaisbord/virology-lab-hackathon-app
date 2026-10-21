import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend runs locally without the /api prefix (API_PREFIX is set only on AWS), so the dev server strips it.
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
