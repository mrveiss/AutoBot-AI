import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
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
          ...configDefaults.coverage.exclude,
          'src/test/**',
          'src/**/*.d.ts',
          'src/**/*.config.ts',
        ],
      },

      // Sequential execution for integration tests
      pool: 'forks',
      poolOptions: {
        forks: {
          singleFork: true,
        },
      },

      // Mock options
      clearMocks: true,
      mockReset: true,
      restoreMocks: true,

      // Reporter configuration
      reporter: process.env.CI ? ['junit', 'default'] : ['default'],
      outputFile: {
        junit: 'test-results/integration-junit.xml',
      },
    },
  }),
)
