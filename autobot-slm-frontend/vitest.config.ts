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
