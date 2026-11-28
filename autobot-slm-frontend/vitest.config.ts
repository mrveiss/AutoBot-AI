// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults, type UserConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { autobotUiResolve } from '../libs/autobot-ui/vite-resolve'

export default mergeConfig(
  defineConfig({
    plugins: [vue()],
    resolve: {
      // Match vite.config.ts: keep resolution relative to the symlink path so
      // `file:` workspace packages (@autobot/ui, @autobot/terminal, @autobot/vnc)
      // find their vue/pinia peers in this app's own node_modules rather than
      // walking up from the real ../libs / ../autobot-plugins path (MVA-893).
      preserveSymlinks: true,
      dedupe: autobotUiResolve().dedupe,
      alias: [
        ...autobotUiResolve().alias,
        { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
        // Mirror vite.config.ts (#13079): without this, any test that mounts a
        // component importing from '@shared' fails to resolve at transform time.
        { find: '@shared', replacement: fileURLToPath(new URL('../autobot_shared', import.meta.url)) },
      ],
    },
  }),
  defineConfig({
    test: {
      // #18254: console output goes straight to the worker's stdout. With interception on, each
      // console call is an `onUserConsoleLog` RPC to the main process, and a log made just before a
      // file's environment is torn down fails the run with "Closing rpc while onUserConsoleLog was
      // pending" although every test passed. Off, there is no RPC to race; the cost is the per-test
      // "stdout | file > test" headers. The Vitest UI needs interception for its console-log
      // previews, so `--ui` runs keep it; the race is a headless-run failure.
      disableConsoleIntercept: !process.argv.includes('--ui'),
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
