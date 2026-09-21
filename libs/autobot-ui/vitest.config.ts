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
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.{test,spec}.ts'],
    },
  }) as UserConfig,
)
