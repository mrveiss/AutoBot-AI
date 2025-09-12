import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// Import centralized defaults - use localhost for WSL development
const DEFAULT_CONFIG = {
  backend: { host: 'localhost', port: '8001' },
  browser: { host: 'localhost', port: '6080' }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  optimizeDeps: {
    include: [
      '@xterm/xterm',
      '@xterm/addon-fit',
      '@xterm/addon-web-links',
      '@heroicons/vue/24/outline',
      '@heroicons/vue/24/solid'
    ],
    esbuildOptions: {
      target: 'es2022'
    }
  },
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
      // Prevent caching of API configurations and critical assets
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
      'X-Content-Type-Options': 'nosniff',
      // Force browsers to revalidate cached resources
      'Last-Modified': new Date().toUTCString(),
      // Prevent proxy caching
      'Surrogate-Control': 'no-store',
      // Additional cache-busting headers
      'X-Cache-Bust': Date.now().toString(),
      'X-AutoBot-Build': process.env.npm_package_version || 'dev'
    },
    proxy: {
      '/api': {
        target: `http://${process.env.VITE_BACKEND_HOST || DEFAULT_CONFIG.backend.host}:${process.env.VITE_BACKEND_PORT || DEFAULT_CONFIG.backend.port}`,
        changeOrigin: true,
        secure: false,
        timeout: 30000,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.error('Proxy error:', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            // Add cache-busting headers to proxied requests
            proxyReq.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
            proxyReq.setHeader('X-Cache-Bust', Date.now().toString());
            
            // Only log proxy requests in debug mode to reduce noise
            if (process.env.NODE_ENV === 'development' && process.env.DEBUG_PROXY === 'true') {
              console.debug('Proxying request:', req.method, req.url, 'to', options.target);
            }
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // Force no-cache on API responses
            proxyRes.headers['cache-control'] = 'no-cache, no-store, must-revalidate';
            proxyRes.headers['pragma'] = 'no-cache';
            proxyRes.headers['expires'] = '0';
          });
        }
      },
      '/ws': {
        target: `http://${process.env.VITE_BACKEND_HOST || DEFAULT_CONFIG.backend.host}:${process.env.VITE_BACKEND_PORT || DEFAULT_CONFIG.backend.port}`,
        ws: true,
        changeOrigin: true,
        timeout: 30000,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.error('WebSocket proxy error:', err);
          });
          proxy.on('proxyReqWs', (proxyReq, req, socket) => {
            console.log('WebSocket proxy request:', req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            console.log('WebSocket proxy response:', proxyRes.statusCode);
          });
        }
      },
      '/vnc-proxy': {
        target: process.env.VITE_PLAYWRIGHT_VNC_URL || `${process.env.VITE_HTTP_PROTOCOL || 'http'}://${process.env.VITE_PLAYWRIGHT_HOST || DEFAULT_CONFIG.browser.host}:${process.env.VITE_PLAYWRIGHT_VNC_PORT || DEFAULT_CONFIG.browser.port}`,
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
        // Add cache-busting hash to asset filenames with longer hash for better cache invalidation
        assetFileNames: 'assets/[name]-[hash:16][extname]',
        chunkFileNames: 'js/[name]-[hash:16].js',
        entryFileNames: 'js/[name]-[hash:16].js',
      },
    },
  }
})