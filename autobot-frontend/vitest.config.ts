// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults, type UserConfig } from 'vitest/config'
import viteConfig from './vite.config'

// Issue #156 Fix: Define reporters outside to avoid type conflict (no as const - vitest expects mutable array)
// #16919: the dependency-floor banner only makes sense locally -- CI's `npm ci` always
// installs exactly what package.json declares, so it would never have anything to report.
const reporters = process.env.CI
  ? ['junit', 'default']
  : ['default', './src/test/dependency-floor-reporter.ts']

// Issue #156 Fix: Type assertion to resolve mergeConfig/defineConfig type conflict
// Vite 7 fix: resolve viteConfig if it is a function
const resolvedViteConfig = typeof viteConfig === 'function'
  ? viteConfig({ command: 'serve', mode: 'test' })
  : viteConfig

export default mergeConfig(
  resolvedViteConfig as UserConfig,
  defineConfig({
    test: {
      // Test environment setup
      environment: 'jsdom',
      environmentOptions: {
        jsdom: {
          url: 'http://localhost:3000',
        },
      },
      globals: true,
      setupFiles: ['src/test/vitest-setup.ts'],

      // File patterns
      include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
      exclude: [
        ...configDefaults.exclude,
        'e2e/**',
        'tests/**',
        'src/test/e2e/**',
        '**/*.e2e.test.ts',
        '**/*.playwright.spec.ts',
        '**/.worktrees/**',
      ],

      // Coverage configuration
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html', 'lcov'],
        reportsDirectory: 'coverage',
        exclude: [
          // Issue #156 Fix: Ensure configDefaults.coverage.exclude is defined before spreading
          ...(configDefaults.coverage?.exclude || []),
          'src/test/**',
          'src/**/*.d.ts',
          'src/**/*.config.ts',
          '**/*.spec.ts',
          '**/*.test.ts',
        ],
        // #17324: the valid key shape. These four numbers used to sit under a
        // `global` key, which is not a threshold key at all -- vitest treats an
        // unrecognised key under `thresholds` as a GLOB pattern for per-file
        // thresholds, so "global" matched no file and the gate enforced
        // nothing. Confirmed two ways: the shipped `interface Thresholds`
        // accepts only 100 / perFile / autoUpdate / statements / functions /
        // branches / lines, and CI passed this job on main at ~50% coverage
        // against a declared 70%.
        //
        // These are FLOORS, not targets. The target is still 70% on every
        // metric. The floors are what CI measured on main at f72de7ea1b
        // (statements 49.91, branches 34.98, functions 38.45, lines 51.01),
        // each pinned to the greatest integer at least 0.4 points below the
        // measurement so that run-to-run jitter -- observed at roughly +/-0.2
        // points across repeated runs of the same tree -- cannot red a PR that
        // changed nothing. Re-measure from a CI run, not a developer machine:
        // a local install below the declared vitest floor reports different
        // numbers and a different exit code.
        //
        // The pin only ever ratchets UP. A PR that raises coverage raises the
        // floor in the same PR -- the rule MAX_DUP_LINES and the reach floors
        // follow. Never lower a floor to clear a red: that is precisely how
        // those two accumulated their slack.
        thresholds: {
          statements: 49,
          branches: 34,
          functions: 38,
          lines: 50,
        },
      },

      // Test execution options
      root: fileURLToPath(new URL('./', import.meta.url)),
      testTimeout: 10000,
      hookTimeout: 10000,

      // Mock options — WARNING (#3070): mockReset wipes vi.mock() factory
      // implementations between tests.  Always re-apply mocks in beforeEach,
      // not in the factory.  Use regular functions for constructor mocks.
      clearMocks: true,
      mockReset: true,
      restoreMocks: true,

      // Reporter configuration
      // Issue #156 Fix: Use pre-defined reporters variable (plural 'reporters')
      reporters: reporters,
      outputFile: {
        junit: 'test-results/junit.xml',
      },
    },
  }) as UserConfig,
)
