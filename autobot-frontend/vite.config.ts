/**
 * Vite Configuration for AutoBot Frontend - SIMPLIFIED to fix circular dependencies
 */

import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const config = {
    backend: { host: env.VITE_BACKEND_HOST || '172.16.168.20', port: env.VITE_BACKEND_PORT || '8001' },
    browser: { host: env.VITE_BROWSER_HOST || '172.16.168.25', port: env.VITE_BROWSER_PORT || '3000' },
    vnc: { host: env.VITE_DESKTOP_VNC_HOST || env.VITE_BACKEND_HOST || '172.16.168.20', port: env.VITE_DESKTOP_VNC_PORT || '6080' },
    protocol: env.VITE_HTTP_PROTOCOL || 'http'
  }

  return {
    plugins: [vue(), vueDevTools()],
    optimizeDeps: {
      include: ['@xterm/xterm', '@xterm/addon-fit', '@xterm/addon-web-links', '@heroicons/vue/24/outline', '@heroicons/vue/24/solid'],
      esbuildOptions: { target: 'es2022' }
    },
    css: { devSourcemap: true, postcss: './postcss.config.js' },
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)), 'vue': 'vue/dist/vue.esm-bundler.js' }
    },
    server: {
      port: 5173,
      strictPort: true,
      host: true,
      allowedHosts: ['localhost', '127.0.0.1', 'host.docker.internal'],
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      },
      proxy: {
        '/api/terminal/ws': { target: `${config.protocol}://${config.backend.host}:${config.backend.port}`, changeOrigin: true, secure: false, ws: true, timeout: 300000 },
        '/api/ws': { target: `${config.protocol}://${config.backend.host}:${config.backend.port}`, changeOrigin: true, secure: false, ws: true, timeout: 300000 },
        '/api': { target: `${config.protocol}://${config.backend.host}:${config.backend.port}`, changeOrigin: true, secure: false, timeout: 300000 },
        '/ws': { target: `${config.protocol}://${config.backend.host}:${config.backend.port}`, ws: true, changeOrigin: true, timeout: 300000 }
      }
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      cssMinify: 'esbuild',
      chunkSizeWarningLimit: 3000,
      rollupOptions: {
        output: {
          manualChunks: undefined  // DISABLED - let Vite handle chunking automatically to avoid circular deps
        }
      }
    }
  }
})
