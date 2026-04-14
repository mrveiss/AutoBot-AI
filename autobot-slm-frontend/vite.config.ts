// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

/** Best-effort check: are we co-located with the user frontend? */
function isCoLocated(): boolean {
  try {
    return existsSync(resolve(__dirname, '../autobot-frontend/package.json'))
  } catch {
    return false
  }
}

/** Vite plugin that warns (or errors) when VITE_API_URL is unset in a co-located build. */
function coLocatedApiUrlGuard(): import('vite').Plugin {
  return {
    name: 'slm-co-located-api-url-guard',
    configResolved(config) {
      if (config.command !== 'build') return
      if (process.env.VITE_API_URL) return
      if (!isCoLocated()) return
      // Co-located build without VITE_API_URL — all API calls will silently
      // route to the wrong backend (port 8001 user backend instead of SLM).
      config.logger.warn(
        '\n[slm-frontend] WARNING: VITE_API_URL is not set.\n' +
        '  In co-located mode every API call will default to "" (empty string)\n' +
        '  and route to the user backend (port 8001) instead of the SLM backend.\n' +
        '  Fix: run  VITE_API_URL=/slm npm run build  or use  npm run build:slm\n'
      )
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const slmTarget = env.VITE_SLM_PROXY_TARGET || 'https://localhost'
  const autobotTarget = env.VITE_AUTOBOT_PROXY_TARGET || 'http://localhost:8001'

  return {
    base: '/slm/',
    plugins: [vue(), coLocatedApiUrlGuard()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@shared': fileURLToPath(new URL('../autobot_shared', import.meta.url))
      }
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
          ws: true
        },
        // Grafana/Prometheus via SLM server nginx proxy
        '/grafana': {
          target: slmTarget,
          changeOrigin: true,
          secure: false
        },
        '/prometheus': {
          target: slmTarget,
          changeOrigin: true,
          secure: false
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
        }
      }
    },
    build: {
      outDir: 'dist',
      sourcemap: true
    }
  }
})
