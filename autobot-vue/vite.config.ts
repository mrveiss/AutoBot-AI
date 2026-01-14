/**
 * Vite Configuration for AutoBot Frontend
 *
 * Issue: #603 - SSOT Phase 3: Frontend Migration
 * Related: #599 - SSOT Configuration System Epic
 *
 * All network configuration comes from environment variables.
 * No hardcoded values - uses .env file or VITE_* environment variables.
 *
 * SINGLE FRONTEND SERVER ARCHITECTURE
 * Service Distribution (6-VM Architecture):
 * - Main Machine (WSL): Backend API + VNC Desktop
 * - VM1 Frontend: Web interface (SINGLE FRONTEND SERVER)
 * - VM2 NPU Worker: Hardware AI acceleration
 * - VM3 Redis: Data layer
 * - VM4 AI Stack: AI processing
 * - VM5 Browser: Web automation (Playwright)
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')

  // Get configuration from environment variables with sensible defaults
  // These defaults match the SSOT configuration in ssot-config.ts
  const config = {
    backend: {
      host: env.VITE_BACKEND_HOST || '172.16.168.20',
      port: env.VITE_BACKEND_PORT || '8001'
    },
    browser: {
      host: env.VITE_BROWSER_HOST || '172.16.168.25',
      port: env.VITE_BROWSER_PORT || '3000'
    },
    vnc: {
      host: env.VITE_DESKTOP_VNC_HOST || env.VITE_BACKEND_HOST || '172.16.168.20',
      port: env.VITE_DESKTOP_VNC_PORT || '6080'
    },
    protocol: env.VITE_HTTP_PROTOCOL || 'http'
  }

  return {
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
        'X-AutoBot-Build': env.npm_package_version || 'dev'
      },
      proxy: {
        // WebSocket endpoints under /api need ws: true
        // SSH Terminal WebSocket (Issue #715)
        '/api/terminal/ws': {
          target: `${config.protocol}://${config.backend.host}:${config.backend.port}`,
          changeOrigin: true,
          secure: false,
          ws: true,  // Enable WebSocket support for terminal connections
          timeout: 300000, // 5 minutes for long-running terminal sessions
        },
        // General WebSocket proxy under /api/ws
        '/api/ws': {
          target: `${config.protocol}://${config.backend.host}:${config.backend.port}`,
          changeOrigin: true,
          secure: false,
          ws: true,  // Enable WebSocket support
          timeout: 300000,
        },
        '/api': {
          target: `${config.protocol}://${config.backend.host}:${config.backend.port}`,
          changeOrigin: true,
          secure: false,
          timeout: 300000, // 5 minutes for long-running analytics operations
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              // Add cache-busting headers to proxied requests
              proxyReq.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
              proxyReq.setHeader('X-Cache-Bust', Date.now().toString());
            });
            proxy.on('proxyRes', (proxyRes) => {
              // Force no-cache on API responses
              proxyRes.headers['cache-control'] = 'no-cache, no-store, must-revalidate';
              proxyRes.headers['pragma'] = 'no-cache';
              proxyRes.headers['expires'] = '0';
            });
          }
        },
        '/ws': {
          target: `${config.protocol}://${config.backend.host}:${config.backend.port}`,
          ws: true,
          changeOrigin: true,
          timeout: 300000, // 5 minutes for long-running WebSocket operations
        },
        '/vnc-proxy': {
          target: env.VITE_PLAYWRIGHT_VNC_URL || `${config.protocol}://${config.browser.host}:${config.browser.port}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/vnc-proxy/, '')
        },
        // Desktop VNC (noVNC) access - WSL Desktop
        '/tools/novnc': {
          target: `${config.protocol}://${config.vnc.host}:${config.vnc.port}`,
          changeOrigin: true,
          ws: true,  // Enable WebSocket support for noVNC
          rewrite: (path) => path.replace(/^\/tools\/novnc/, ''),
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
            if (!assetInfo.name) {
              return `assets/[name]-[hash:12][extname]`;
            }
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
  }
})
