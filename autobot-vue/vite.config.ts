import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    vueDevTools(),
  ],
  css: {
    devSourcemap: true,
    postcss: './postcss.config.js',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    port: 5173,
    headers: {
      'X-Content-Type-Options': 'nosniff'
      // Removed Content-Security-Policy to avoid unneeded headers
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false
      },
      '/vnc-proxy': {
        target: 'http://localhost:6080',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/vnc-proxy/, '')
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: '.',
    emptyOutDir: true,
    cssMinify: 'esbuild', // Use esbuild instead of lightningcss
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Split Vue and related dependencies into their own chunk
          if (id.includes('vue') || id.includes('vue-router')) {
            return 'vue';
          }
          // Split utilities into their own chunk
          if (id.includes('/src/utils/')) {
            return 'utils';
          }
          // Split node_modules into vendor chunk
          if (id.includes('node_modules')) {
            return 'vendor';
          }
        },
        // Add cache-busting hash to asset filenames
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'js/[name]-[hash].js',
        entryFileNames: 'js/[name]-[hash].js',
      },
    },
  }
})
