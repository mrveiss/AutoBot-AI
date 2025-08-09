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
    transformer: 'postcss',
    lightningcss: {
      // Disable lightningcss minification that's causing issues with Tailwind
      minify: false,
    },
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
