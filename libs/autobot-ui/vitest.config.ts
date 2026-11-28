// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Vitest config for the @autobot/ui kit (#14786). Minimal on purpose — no
// coverage thresholds and no CI wiring yet, those are later ACs on the parent
// issue. Merges onto the kit's own vite.config.ts (same pattern the two
// consuming apps use in their own vitest.config.ts) so the Vue plugin used
// for `npm run build` is also used to compile .vue SFCs under test.
import { mergeConfig, defineConfig, type UserConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig as UserConfig,
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
      include: ['src/**/*.{test,spec}.ts'],
    },
  }) as UserConfig,
)
