// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useStaleResults (#17982)
 *
 * A cached dependencies / duplicates / import-tree result older than the source's last sync
 * is SERVED, flagged `stale: true` by its cached route (owner decision on #17982): it is
 * shown, never hidden, and the page says it predates the last sync. This holds the three
 * flags; `StaleResultNotice` reads them by injection.
 *
 * A flag is set only from a cached body and cleared when the same result is loaded by a full
 * scan, so it never outlives the data it describes.
 */

import { getCurrentInstance, inject, provide, reactive, watch, type InjectionKey } from 'vue'

export type StaleResultKind = 'duplicates' | 'dependencies' | 'importTree'

export interface StaleResultsHandle {
  flags: Record<StaleResultKind, boolean>
  /** Set the flag from a cached-route body: stale only when the route said `stale: true`. */
  markFromCached: (kind: StaleResultKind, body: unknown) => void
  clear: (kind: StaleResultKind) => void
}

export const STALE_RESULTS_KEY: InjectionKey<StaleResultsHandle> = Symbol('codebase-stale-results')

/**
 * Create the page's stale flags and offer them to the components below the caller.
 * `currentSource` names the selected source; a different source starts with no flag set.
 */
export function useStaleResults(currentSource: () => string): StaleResultsHandle {
  const flags = reactive<Record<StaleResultKind, boolean>>({ duplicates: false, dependencies: false, importTree: false })
  const handle: StaleResultsHandle = {
    flags,
    markFromCached: (kind, body) => {
      flags[kind] = !!body && typeof body === 'object' && (body as { stale?: unknown }).stale === true
    },
    clear: (kind) => {
      flags[kind] = false
    },
  }
  watch(currentSource, () => {
    flags.duplicates = flags.dependencies = flags.importTree = false
  })
  if (getCurrentInstance()) provide(STALE_RESULTS_KEY, handle)
  return handle
}

/** The stale flags a parent provided, or `null` when the component is mounted without any. */
export function injectStaleResults(): StaleResultsHandle | null {
  return inject(STALE_RESULTS_KEY, null)
}
