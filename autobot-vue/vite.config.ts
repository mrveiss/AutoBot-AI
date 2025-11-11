import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// Import centralized defaults - SINGLE FRONTEND SERVER ARCHITECTURE
// Frontend runs on 172.16.168.21:5173 and connects to backend on 172.16.168.20:8001
// Service Distribution:
// - Browser (Playwright): 172.16.168.25:3000
// - Terminal VNC: 172.16.168.20:6080
// - Desktop VNC: 172.16.168.20:6080
const DEFAULT_CONFIG = {
  backend: { host: '172.16.168.20', port: '8001' },
  browser: { host: '172.16.168.25', port: '3000' },  // Browser automation service
  vnc: { host: '172.16.168.20', port: '6080' }       // Desktop/Terminal VNC
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
      },
      // Desktop VNC (noVNC) access - WSL Desktop
      '/tools/novnc': {
        target: `http://${process.env.VITE_VNC_HOST || DEFAULT_CONFIG.vnc.host}:${process.env.VITE_VNC_PORT || DEFAULT_CONFIG.vnc.port}`,
        changeOrigin: true,
        ws: true,  // Enable WebSocket support for noVNC
        rewrite: (path) => path.replace(/^\/tools\/novnc/, ''),
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.error('noVNC proxy error:', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('noVNC proxy request:', req.url);
          });
        }
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: '.',
    emptyOutDir: true,
    cssMinify: 'esbuild', // Use esbuild instead of lightningcss
    chunkSizeWarningLimit: 2000, // Increase limit to accommodate larger chunks
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Vue core (keep together)
          if (id.includes('node_modules/vue/') ||
              id.includes('node_modules/@vue/') ||
              id.includes('node_modules/vue-router/')) {
            return 'vue-core';
          }

          // Async components (separate from static imports to avoid conflicts)
          if (id.includes('/src/components/async/')) {
            return 'async-components';
          }

          // Large UI component groups
          if (id.includes('/src/components/Terminal') ||
              id.includes('/src/components/XTerminal') ||
              id.includes('/src/components/Workflow')) {
            return 'terminal-workflow';
          }

          if (id.includes('/src/components/Chat') ||
              id.includes('/src/components/Knowledge') ||
              id.includes('/src/components/chat/') ||
              id.includes('/src/components/knowledge/')) {
            return 'chat-knowledge';
          }

          if (id.includes('/src/components/Settings') ||
              id.includes('/src/components/settings/') ||
              id.includes('/src/components/Dashboard') ||
              id.includes('/src/components/monitoring/')) {
            return 'settings-dashboard';
          }

          // File management components
          if (id.includes('/src/components/FileBrowser') ||
              id.includes('/src/components/FileUpload')) {
            return 'file-management';
          }

          // Utilities and services
          if (id.includes('/src/utils/') || id.includes('/src/services/')) {
            return 'utils-services';
          }

          // View components
          if (id.includes('/src/views/')) {
            return 'views';
          }

          // Stores
          if (id.includes('/src/stores/')) {
            return 'stores';
          }

          // Node modules - split by size and functionality
          if (id.includes('node_modules')) {
            // Large libraries
            if (id.includes('monaco-editor') || id.includes('codemirror')) {
              return 'editor-libs';
            }

            // Charts and visualization
            if (id.includes('chart') || id.includes('d3') || id.includes('echarts')) {
              return 'chart-libs';
            }

            // Terminal libraries
            if (id.includes('@xterm/')) {
              return 'terminal-libs';
            }

            // HTTP and networking
            if (id.includes('axios') || id.includes('socket') || id.includes('fetch')) {
              return 'network-libs';
            }

            // UI libraries
            if (id.includes('tailwind') || id.includes('@headless') || id.includes('@heroicons')) {
              return 'ui-libs';
            }

            // Everything else
            return 'vendor';
          }
        },

        // Improved cache-busting strategy
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name.split('.');
          const ext = info[info.length - 1];
          if (/png|jpe?g|svg|gif|tiff|bmp|ico/i.test(ext)) {
            return `assets/images/[name]-[hash:12][extname]`;
          }
          if (/woff2?|eot|ttf|otf/i.test(ext)) {
            return `assets/fonts/[name]-[hash:12][extname]`;
          }
          return `assets/[name]-[hash:12][extname]`;
        },
        chunkFileNames: 'js/[name]-[hash:12].js',
        entryFileNames: 'js/[name]-[hash:12].js',
      },
    },
  }
})