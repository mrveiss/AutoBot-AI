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
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const PACKAGE = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8')) as {
  name: string
  exports: Record<string, string>
}

/** Bare packages the kit imports that must come from the consuming app's copy. */
export const KIT_SHARED_DEPS = ['vue', '@vueuse/core', 'dompurify', 'reka-ui']

const escapeRegex = (text: string) => text.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')

export interface KitAlias {
  find: RegExp
  replacement: string
}

/**
 * One exact-match alias per `exports` entry of the kit's package.json (the single
 * source of truth). Exact match matters: a string alias on '@autobot/ui' would also
 * rewrite '@autobot/ui/adapter' to '<index.ts>/adapter' and break every build.
 */
export function kitAliases(): KitAlias[] {
  return Object.entries(PACKAGE.exports).map(([subpath, target]) => {
    const specifier = subpath === '.' ? PACKAGE.name : `${PACKAGE.name}/${subpath.slice(2)}`
    return {
      find: new RegExp(`^${escapeRegex(specifier)}$`),
      replacement: fileURLToPath(new URL(target, new URL('./', import.meta.url))),
    }
  })
}

export function autobotUiResolve() {
  return {
    alias: kitAliases(),
    dedupe: KIT_SHARED_DEPS,
  }
}
