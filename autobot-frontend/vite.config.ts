/**
 * Vite Configuration for AutoBot Frontend - SIMPLIFIED to fix circular dependencies
 */

import { fileURLToPath, URL } from 'node:url'
import { copyFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import type { Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import pkg from './package.json'

/**
 * Copy VAD static assets (ONNX runtime WASM + Silero model + worklet bundle)
 * from node_modules into dist/ at build time (#1150).
 *
 * MicVAD (@ricky0123/vad-web) fetches these files at runtime via fetch()
 * from a configurable baseAssetPath. They must be served as static files.
 */
function vadAssetsPlugin(): Plugin {
  const assets: [string, string][] = [
    ['node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', 'vad.worklet.bundle.min.js'],
    ['node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx', 'silero_vad_legacy.onnx'],
    ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.mjs'],
    ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm', 'ort-wasm-simd-threaded.wasm'],
  ]
  return {
    name: 'vad-assets',
    writeBundle(options) {
      const outDir = options.dir || 'dist'
      for (const [src, dest] of assets) {
        try {
          copyFileSync(src, join(outDir, dest))
        } catch (e) {
          process.stderr.write(`[vad-assets] WARNING: Failed to copy ${src}: ${e}\n`)
        }
      }
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const config = {
    backend: { host: env.VITE_BACKEND_HOST || '127.0.0.1', port: env.VITE_BACKEND_PORT || '8001' },
    browser: { host: env.VITE_BROWSER_HOST || '127.0.0.1', port: env.VITE_BROWSER_PORT || '3000' },
    vnc: { host: env.VITE_DESKTOP_VNC_HOST || env.VITE_BACKEND_HOST || '127.0.0.1', port: env.VITE_DESKTOP_VNC_PORT || '6080' },
    protocol: env.VITE_HTTP_PROTOCOL || 'http'
  }

  return {
    define: {
      __FEATURE_VOICE__: JSON.stringify(env.VITE_FEATURE_VOICE !== 'false'),
      __FEATURE_VNC__: JSON.stringify(env.VITE_FEATURE_VNC !== 'false'),
      __FEATURE_BROWSER__: JSON.stringify(env.VITE_FEATURE_BROWSER !== 'false'),
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(pkg.version),
    },
    plugins: [vue(), vueDevTools(), vadAssetsPlugin()],
    optimizeDeps: {
      include: ['@xterm/xterm', '@xterm/addon-fit', '@xterm/addon-web-links', '@heroicons/vue/24/outline', '@heroicons/vue/24/solid'],
      rolldownOptions: { target: 'es2022' }
    },
    css: { devSourcemap: true, postcss: './postcss.config.js' },
    resolve: {
      // preserveSymlinks: true resolves modules relative to the symlink path
      // (node_modules/@autobot/terminal) not the real path (../../autobot-plugins/…).
      // Without this, rolldown walks up from the real plugin path and misses
      // pinia/vue in the frontend's node_modules. Required for file: workspace
      // packages (same fix applied to slm-frontend in #8482 / MVA-893).
      preserveSymlinks: true,
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
