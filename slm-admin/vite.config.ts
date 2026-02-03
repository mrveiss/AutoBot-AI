// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      // SLM Backend API - local backend at port 8000
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true
      },
      // External proxies via nginx (Grafana, Prometheus, etc.)
      '/grafana': {
        target: 'http://127.0.0.1:80',
        changeOrigin: true
      },
      '/prometheus': {
        target: 'http://127.0.0.1:80',
        changeOrigin: true
      },
      // Main AutoBot backend for admin functionality (Issue #729)
      // Proxies to main backend at 172.16.168.20:8001
      '/autobot-api': {
        target: 'http://172.16.168.20:8001',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/autobot-api/, '/api')
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
})
