// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Shared vite/vitest `resolve` fragment for apps that consume `@autobot/ui` (#17959).
 *
 * Both apps declare `"@autobot/ui": "file:../libs/autobot-ui"` and resolve with
 * `preserveSymlinks: true`, so the specifier normally goes through
 * `node_modules/@autobot/ui`. In a git worktree `node_modules` is a symlink to the
 * MAIN checkout's install (#16912), so that link points at the main checkout's kit
 * and app tests silently exercise a kit older than the one being edited.
 *
 * Pinning the specifier to the in-tree kit fixes that. In CI (`npm ci`) the package
 * link points at these same files, so the resolved code is identical.
 *
 * The kit directory has no `node_modules`, so its own bare imports would not
 * resolve from there. `dedupe` makes vite resolve them from the app root instead,
 * which also guarantees the kit shares the app's single `vue` instance.
 */
import { fileURLToPath } from 'node:url'

const KIT_ENTRY = fileURLToPath(new URL('./index.ts', import.meta.url))

/** Bare packages the kit imports that must come from the consuming app's copy. */
export const KIT_SHARED_DEPS = ['vue', '@vueuse/core']

export function autobotUiResolve() {
  return {
    alias: { '@autobot/ui': KIT_ENTRY },
    dedupe: KIT_SHARED_DEPS,
  }
}
