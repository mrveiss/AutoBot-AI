// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // Dev proxy targets — overridable via env vars (#3049)
  const slmTarget = env.VITE_SLM_PROXY_TARGET || 'https://172.16.168.19'
  const autobotTarget = env.VITE_AUTOBOT_PROXY_TARGET || 'http://172.16.168.20:8001'

  return {
    base: '/slm/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@shared': fileURLToPath(new URL('../autobot-shared', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        // SLM Backend API - backend runs on SLM server (.19)
        '/api': {
          target: slmTarget,
          changeOrigin: true,
          secure: false,
          ws: true,
        },
        // Grafana/Prometheus via SLM server nginx proxy
        '/grafana': {
          target: slmTarget,
          changeOrigin: true,
          secure: false,
        },
        '/prometheus': {
          target: slmTarget,
          changeOrigin: true,
          secure: false,
        },
        // Main AutoBot backend for admin functionality (Issue #729)
        // Issue #1779: inject X-Internal-API-Key for service auth
        '/autobot-api': {
          target: autobotTarget,
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/autobot-api/, '/api'),
          headers: {
            'X-Internal-API-Key': process.env.AUTOBOT_INTERNAL_API_KEY || '',
          },
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  }
})
