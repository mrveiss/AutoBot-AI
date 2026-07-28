// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults, type UserConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default mergeConfig(
  defineConfig({
    plugins: [vue()],
    resolve: {
      // Match vite.config.ts: keep resolution relative to the symlink path so
      // `file:` workspace packages (@autobot/ui, @autobot/terminal, @autobot/vnc)
      // find their vue/pinia peers in this app's own node_modules rather than
      // walking up from the real ../libs / ../autobot-plugins path (MVA-893).
      preserveSymlinks: true,
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
  }),
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
      exclude: [...configDefaults.exclude],
      root: fileURLToPath(new URL('./', import.meta.url)),
      testTimeout: 10000,
      clearMocks: true,
      mockReset: true,
      restoreMocks: true,
    },
  }) as UserConfig,
)
