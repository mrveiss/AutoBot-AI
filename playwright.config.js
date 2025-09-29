/**
 * Playwright Configuration for AutoBot Testing
 *
 * Global configuration to ensure consistent browser behavior
 * across all Playwright tests and scripts.
 */

module.exports = {
  // Global test settings
  testDir: './tests',
  timeout: 60000, // 60 seconds per test
  expect: {
    timeout: 10000 // 10 seconds for assertions
  },

  // Global browser settings
  use: {
    // Browser viewport
    viewport: { width: 1920, height: 1080 },

    // Browser context options
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',

    // Timeouts
    navigationTimeout: 30000,
    actionTimeout: 10000,

    // Browser launch options
    launchOptions: {
      args: [
        '--window-size=1920,1080',
        '--force-device-scale-factor=1',
        '--disable-web-security',
        '--disable-features=TranslateUI',
        '--disable-ipc-flooding-protection',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding'
      ]
    }
  },

  // Browser projects
  projects: [
    {
      name: 'chromium',
      use: {
        ...require('@playwright/test').devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 }
      }
    },
    {
      name: 'firefox',
      use: {
        ...require('@playwright/test').devices['Desktop Firefox'],
        viewport: { width: 1920, height: 1080 }
      }
    },
    {
      name: 'webkit',
      use: {
        ...require('@playwright/test').devices['Desktop Safari'],
        viewport: { width: 1920, height: 1080 }
      }
    }
  ],

  // Output directories
  outputDir: 'tests/results/playwright-output',

  // Reporting
  reporter: [
    ['html', { outputFolder: 'tests/results/playwright-report' }],
    ['json', { outputFile: 'tests/results/playwright-results.json' }]
  ],

  // Global setup
  globalSetup: require.resolve('./tests/setup/global-setup.js'),

  // Web server (for testing local development)
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
    cwd: './autobot-vue'
  }
};