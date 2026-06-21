// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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
  // discovered story (one iframe load + screenshot per story). With ~1175
  // stories at ~3-5s each (~60-100 min worst case across both projects) we
  // budget 30 min per test. Per-story navigation is bounded in the spec
  // (#10038) so one stuck story fails fast and is named rather than burning
  // the whole budget — the old 150 min budget let a single hung iframe run
  // for hours (#10038).
  timeout: 30 * 60 * 1000,

  // Hard ceiling on the entire run (all projects). Backstop below the 45-min
  // job timeout so a pathological hang fails inside Playwright (naming the
  // offending story) before the runner kills the job opaquely.
  globalTimeout: 40 * 60 * 1000,

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
    // Bound per-story navigation/actions so a single story whose iframe never
    // settles fails in seconds (caught + named by the spec's soft-collect
    // loop) instead of hanging on the whole-test budget (#10038).
    navigationTimeout: 30_000,
    actionTimeout: 30_000,
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
