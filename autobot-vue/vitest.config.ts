import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      // Test environment setup
      environment: 'jsdom',
      globals: true,
      setupFiles: ['src/test/vitest-setup.ts'],

      // File patterns
      include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
      exclude: [...configDefaults.exclude, 'e2e/**', 'tests/**'],

      // Coverage configuration
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html', 'lcov'],
        reportsDirectory: 'coverage',
        exclude: [
          ...configDefaults.coverage.exclude,
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
      reporter: process.env.CI ? ['junit', 'default'] : ['default'],
      outputFile: {
        junit: 'test-results/junit.xml',
      },
    },
  }),
)
