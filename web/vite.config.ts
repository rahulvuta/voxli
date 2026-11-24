import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { defineConfig } from 'vite'

// HTTPS on the LAN so phone browsers allow the microphone; /ws and /api proxied to the Python backend.
export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: true,
    port: 5173,
    proxy: { '/ws': { target: 'ws://127.0.0.1:8000', ws: true }, '/api': 'http://127.0.0.1:8000' },
  },
})
