import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  css: {
    devSourcemap: true,
    postcss: './postcss.config.js',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      'vue': 'vue/dist/vue.esm-bundler.js'
    },
  },
  server: {
    port: 5173,
    strictPort: true, // Fail if port 5173 is busy instead of trying alternates
    host: true,
    allowedHosts: ['localhost', '127.0.0.1', 'host.docker.internal'],
    headers: {
      'X-Content-Type-Options': 'nosniff'
      // Removed Content-Security-Policy to avoid unneeded headers
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || `${process.env.VITE_HTTP_PROTOCOL || 'http'}://${process.env.VITE_BACKEND_HOST || '127.0.0.1'}:${process.env.VITE_BACKEND_PORT || '8001'}`,
        changeOrigin: true,
        secure: false
      },
      '/vnc-proxy': {
        target: process.env.VITE_PLAYWRIGHT_VNC_URL || `${process.env.VITE_HTTP_PROTOCOL || 'http'}://${process.env.VITE_PLAYWRIGHT_HOST || '127.0.0.1'}:${process.env.VITE_PLAYWRIGHT_VNC_PORT || '6080'}`,
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
    chunkSizeWarningLimit: 1000, // Increase limit since we have good chunking strategy
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Split Vue and related dependencies into their own chunk
          if (id.includes('vue') || id.includes('vue-router') || id.includes('@vue')) {
            return 'vue';
          }
          // Split large component groups
          if (id.includes('/src/components/Terminal') || id.includes('/src/components/Workflow')) {
            return 'terminal-workflow';
          }
          if (id.includes('/src/components/Chat') || id.includes('/src/components/Knowledge')) {
            return 'chat-knowledge';
          }
          if (id.includes('/src/components/Settings') || id.includes('/src/components/Dashboard')) {
            return 'settings-dashboard';
          }
          // Split utilities and services into their own chunk
          if (id.includes('/src/utils/') || id.includes('/src/services/')) {
            return 'utils';
          }
          // Split node_modules by library type
          if (id.includes('node_modules')) {
            // Large UI libraries
            if (id.includes('monaco-editor') || id.includes('codemirror')) {
              return 'editor';
            }
            // Charts and visualization
            if (id.includes('chart') || id.includes('d3')) {
              return 'charts';
            }
            // HTTP and networking
            if (id.includes('axios') || id.includes('socket')) {
              return 'network';
            }
            // Everything else
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
