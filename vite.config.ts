import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true,
    watch: {
      // Tauri watches native sources; Vite must not traverse Rust builds or local tooling.
      ignored: ['**/src-tauri/**', '**/.tools/**', '**/.cache/**'],
    },
  },
})
