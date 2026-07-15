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
 * Resolve VITE_API_URL from every source Vite would consult, in priority order:
 *   1. inline / shell env  (process.env.VITE_API_URL — how `build:slm` passes it)
 *   2. .env* files         (loadEnv result)
 *
 * loadEnv() ONLY reads .env* files — it does NOT include inline `VAR=x vite build`
 * env vars. Relying on Vite's implicit `import.meta.env.VITE_*` replacement for an
 * inline var is fragile: the value must be resolved explicitly here and baked via
 * `define` so the built bundle is deterministic regardless of how the var arrives.
 */
function resolveApiUrl(fileEnv: Record<string, string>): string {
  const inline = process.env.VITE_API_URL
  if (inline !== undefined && inline !== '') return inline
  return fileEnv.VITE_API_URL || ''
}

/**
 * Vite plugin that errors when VITE_API_URL is unset in a co-located build.
 *
 * NOTE: This guard only applies to `vite build` (built artifacts).
 * During `vite dev`, API routing is handled by the `server.proxy` config
 * below, so VITE_API_URL is never read — the dev server never bakes it into
 * the bundle.  No guard is needed (or useful) for the dev server.
 */
function coLocatedApiUrlGuard(apiUrl: string): import('vite').Plugin {
  return {
    name: 'slm-co-located-api-url-guard',
    configResolved(config) {
      // Only check during builds — dev server uses proxy config, not baked VITE_API_URL.
      if (config.command !== 'build') return
      if (apiUrl) return
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

  // Resolve the API base once, from inline env or .env files, and bake it
  // explicitly via `define`. This is immune to Vite version changes and to
  // shell/npm quirks in how `VAR=x vite build` propagates the inline var —
  // the bundle always contains the value resolved here.
  const apiUrl = resolveApiUrl(env)

  return {
    base: '/slm/',
    plugins: [vue(), coLocatedApiUrlGuard(apiUrl)],
    // Statically replace import.meta.env.VITE_API_URL in the source. Without
    // this, baking relied on Vite implicitly exposing an inline process.env
    // var — fragile across versions and invocation styles. See resolveApiUrl().
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl),
    },
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
