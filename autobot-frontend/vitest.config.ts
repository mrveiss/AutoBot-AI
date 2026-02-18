import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults, type UserConfig } from 'vitest/config'
import viteConfig from './vite.config'

// Issue #156 Fix: Define reporters outside to avoid type conflict (no as const - vitest expects mutable array)
const reporters = process.env.CI ? ['junit', 'default'] : ['default']

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
        '**/*.playwright.spec.ts'
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
        thresholds: {
          global: {
            branches: 70,
            functions: 70,
            lines: 70,
            statements: 70,
          },
        },
      },

      // Test execution options
      root: fileURLToPath(new URL('./', import.meta.url)),
      testTimeout: 10000,
      hookTimeout: 10000,

      // Mock options
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
