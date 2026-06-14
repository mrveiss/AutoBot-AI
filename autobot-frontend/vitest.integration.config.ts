// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { mergeConfig, defineConfig, configDefaults, type UserConfig } from 'vitest/config'
import viteConfig from './vite.config'

// #9693: vite.config exports a function (Vite 7) — mergeConfig cannot merge a
// callback, so resolve it first (same pattern as vitest.config.ts).
const resolvedViteConfig = typeof viteConfig === 'function'
  ? viteConfig({ command: 'serve', mode: 'test' })
  : viteConfig

export default mergeConfig(
  resolvedViteConfig as UserConfig,
  defineConfig({
    test: {
      // Integration test environment
      environment: 'jsdom',
      globals: true,
      setupFiles: ['src/test/setup.ts', 'src/test/integration-setup.ts'],

      // Integration test file patterns
      include: ['src/**/*.integration.{test,spec}.{js,ts,jsx,tsx}'],
      exclude: [...configDefaults.exclude],

      // Integration tests may need longer timeouts
      testTimeout: 30000,
      hookTimeout: 30000,

      // Coverage for integration tests
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html'],
        reportsDirectory: 'coverage/integration',
        exclude: [
          ...(configDefaults.coverage?.exclude || []),
          'src/test/**',
          'src/**/*.d.ts',
          'src/**/*.config.ts',
        ],
      },

      // Sequential execution for integration tests
      // (Vitest 4 removed poolOptions.forks.singleFork — maxWorkers: 1 is
      // the top-level equivalent.)
      pool: 'forks',
      maxWorkers: 1,

      // Mock options
      clearMocks: true,
      mockReset: true,
      restoreMocks: true,

      // Reporter configuration
      reporters: process.env.CI ? ['junit', 'default'] : ['default'],
      outputFile: {
        junit: 'test-results/integration-junit.xml',
      },
    },
  }) as UserConfig,
)
