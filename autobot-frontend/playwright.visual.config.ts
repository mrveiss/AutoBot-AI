// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Playwright config for visual regression tests.
 *
 * Separated from playwright.config.ts (which targets the live frontend
 * at :5173) because visual tests target Storybook at :6006 and have
 * different timing / parallelism needs.
 *
 * Usage:
 *   npm run test:visual                          # diff against baselines
 *   npm run test:visual -- --update-snapshots    # regenerate baselines
 *
 * Issue #5077.
 */
import { defineConfig, devices } from '@playwright/test';

const STORYBOOK_PORT = 6006;
const STORYBOOK_URL = `http://localhost:${STORYBOOK_PORT}`;

export default defineConfig({
  testDir: './tests/visual',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? 'github' : [['html', { open: 'never' }]],

  // The single test in storybook-stories.spec.ts loops through every
  // discovered story (one iframe load + screenshot per story). With 1154 stories
  // at ~3-5s each = ~3462-5770s, we budget 150 minutes per project for headroom.
  timeout: 9_000_000,

  // Snapshot baselines live next to the tests, organized per project (light/dark)
  // and OS to avoid cross-platform rendering noise and theme conflicts.
  // Engineers regenerate locally on the OS they develop on; CI runs Linux baselines.
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{testFilePath}/{arg}-{platform}{ext}',

  expect: {
    // Per-screenshot expect timeout. Default 5s is too tight for the
    // first paint of complex stories on a cold CI runner.
    timeout: 30_000,
    // Pixel-diff tolerance — small enough to catch real layout drift,
    // large enough to ignore subpixel font rendering jitter across
    // machines.
    toHaveScreenshot: {
      maxDiffPixels: 100,
      threshold: 0.2,
      animations: 'disabled',
    },
  },

  use: {
    baseURL: STORYBOOK_URL,
    trace: 'on-first-retry',
    // Disable animations globally so transitions don't cause flaky diffs.
    contextOptions: {
      reducedMotion: 'reduce',
    },
  },

  // Auto-start Storybook for the test run if it's not already running.
  // Engineers may want to start it manually (faster iteration) — set
  // SKIP_STORYBOOK_START=1 to bypass.
  webServer: process.env.SKIP_STORYBOOK_START
    ? undefined
    : {
        command: 'npm run storybook -- --ci --quiet',
        port: STORYBOOK_PORT,
        reuseExistingServer: true,
        timeout: 120_000,
      },

  projects: [
    {
      name: 'chromium-light',
      use: { ...devices['Desktop Chrome'], colorScheme: 'light' },
    },
    {
      name: 'chromium-dark',
      use: { ...devices['Desktop Chrome'], colorScheme: 'dark' },
    },
  ],
});
