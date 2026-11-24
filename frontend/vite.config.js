import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'

const workspaceRoot = fileURLToPath(new URL('../', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, workspaceRoot, '')
  const googleClientId = process.env.VITE_GOOGLE_CLIENT_ID
    || process.env.GOOGLE_CLIENT_ID
    || env.VITE_GOOGLE_CLIENT_ID
    || env.GOOGLE_CLIENT_ID
    || ''

  return {
    envDir: workspaceRoot,
    define: {
      'import.meta.env.VITE_GOOGLE_CLIENT_ID': JSON.stringify(googleClientId)
    },
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      allowedHosts: [
        'localhost',
        '.trycloudflare.com',
        'mobility-prospect-estates-pork.trycloudflare.com'
      ]
    }
  }
})