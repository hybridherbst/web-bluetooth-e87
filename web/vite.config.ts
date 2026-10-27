import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: mode === 'desktop' ? [svelte()] : [svelte(), basicSsl()],
  base: mode === 'desktop' ? './' : process.env.BASE_PATH,
  build: mode === 'desktop' ? {
    outDir: 'dist-desktop',
    rollupOptions: { input: fileURLToPath(new URL('./desktop.html', import.meta.url)) },
  } : undefined,
}))
