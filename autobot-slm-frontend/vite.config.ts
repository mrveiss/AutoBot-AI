// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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

/**
 * Vite plugin that errors when VITE_API_URL is unset in a co-located build.
 *
 * NOTE: This guard only applies to `vite build` (built artifacts).
 * During `vite dev`, API routing is handled by the `server.proxy` config
 * below, so VITE_API_URL is never read — the dev server never bakes it into
 * the bundle.  No guard is needed (or useful) for the dev server.
 */
function coLocatedApiUrlGuard(): import('vite').Plugin {
  return {
    name: 'slm-co-located-api-url-guard',
    configResolved(config) {
      // Only check during builds — dev server uses proxy config, not baked VITE_API_URL.
      if (config.command !== 'build') return
      if (process.env.VITE_API_URL) return
      if (!isCoLocated()) return
      // Co-located build without VITE_API_URL — the baked-in base URL will be
      // empty string, so all API calls will silently route to the wrong backend
      // (port 8001 user backend instead of the SLM backend).
      // Throw to abort the build rather than silently writing a broken dist/.
      throw new Error(
        '[slm-frontend] VITE_API_URL is not set.\n' +
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
      // preserveSymlinks: true keeps module resolution relative to the symlink
      // path (node_modules/@autobot/vnc, @autobot/terminal) rather than the
      // real path (../../autobot-plugins/…). Without this, rolldown walks up
      // from the real plugin path and never finds pinia/vue in the frontend's
      // own node_modules. Required for file: workspace packages (MVA-893).
      preserveSymlinks: true,
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
