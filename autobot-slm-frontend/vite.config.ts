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
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../autobot-shared', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // SLM Backend API - backend runs on SLM server (.19)
      '/api': {
        target: 'https://172.16.168.19',
        changeOrigin: true,
        secure: false,
        ws: true
      },
      // Grafana/Prometheus via SLM server nginx proxy
      '/grafana': {
        target: 'https://172.16.168.19',
        changeOrigin: true,
        secure: false
      },
      '/prometheus': {
        target: 'https://172.16.168.19',
        changeOrigin: true,
        secure: false
      },
      // Main AutoBot backend for admin functionality (Issue #729)
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
