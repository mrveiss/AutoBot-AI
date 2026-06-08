// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCytoscapeLibrary
 *
 * Encapsulates lazy-loading of `cytoscape` + `cytoscape-fcose` for chart
 * components. Before this composable, `FunctionCallGraph.vue` and
 * `ImportTreeChart.vue` each carried their own copy of:
 *
 *   - state refs (`cytoscapeLoading`, `cytoscapeError`, `cytoscapeModule`,
 *     `fcoseModule`)
 *   - `loadCytoscapeLibrary()` dynamic import + fcose register
 *   - `initAfterLoad()` retry helper that combines load + chart init
 *   - `retryCytoscape()` wrapper for the error UI's Retry button
 *
 * The refactor in #5173 / PR #5190 extracted a local helper per file to
 * fix a retry-reinit bug but stopped short of sharing code between the
 * two files. This composable finishes the job.
 *
 * Chart files now:
 *   - own their chart-specific `cy` / `clusterCy` refs and
 *     `initCytoscape()` / `updateCytoscapeElements()` functions
 *   - receive a single `onReady` callback that does view-mode-aware init
 *   - use `ensureReady()` from every caller that previously awaited
 *     `loadCytoscapeLibrary()` + ran the init-or-skip logic
 *   - wire the template Retry button to `retry()`
 *
 * Issue #5206.
 */

import { ref, shallowRef, type Ref, type ShallowRef } from 'vue'
import type cytoscape from 'cytoscape'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCytoscapeLibrary')

export interface UseCytoscapeLibraryReturn {
  /** True while the dynamic import is in flight. */
  loading: Ref<boolean>
  /** Non-empty when the last import failed; cleared on every fresh attempt. */
  error: Ref<string>
  /** Loaded cytoscape default export, or null before/after failure. */
  cytoscapeModule: ShallowRef<typeof cytoscape | null>
  /** Loaded cytoscape-fcose default export, or null before/after failure. */
  fcoseModule: ShallowRef<unknown>
  /**
   * Await the library load AND run the chart-specific init callback.
   * If the load fails, the callback is skipped and `error.value` is set.
   * If the library is already loaded, the import is skipped but the
   * callback still runs — this is the caller's hook to (re)attach the
   * cytoscape instance to a (possibly new) container.
   */
  ensureReady: () => Promise<void>
  /** Re-run `ensureReady()`. Template-facing handler for the Retry button. */
  retry: () => void
}

/**
 * @param onReady chart-specific init callback fired after a successful
 *   library load. Typically does view-mode-aware `initCytoscape()` /
 *   `updateCytoscapeElements()` etc. Runs in the same task as the caller
 *   of `ensureReady()` so awaiting `ensureReady()` awaits the callback too.
 */
export function useCytoscapeLibrary(
  onReady: () => void | Promise<void>,
): UseCytoscapeLibraryReturn {
  const loading = ref(false)
  const error = ref('')
  const cytoscapeModule = shallowRef<typeof cytoscape | null>(null)
  const fcoseModule = shallowRef<unknown>(null)

  async function load(): Promise<void> {
    if (cytoscapeModule.value) return // already loaded
    try {
      loading.value = true
      error.value = ''
      const [cyMod, fcoseMod] = await Promise.all([
        import('cytoscape'),
        // @ts-expect-error - cytoscape-fcose ships no type declarations
        import('cytoscape-fcose'),
      ])
      cytoscapeModule.value = cyMod.default
      fcoseModule.value = (fcoseMod as { default: unknown }).default
      if (cytoscapeModule.value && fcoseModule.value) {
        cytoscapeModule.value.use(fcoseModule.value as never)
      }
    } catch (err) {
      error.value = `Failed to load visualization library: ${
        err instanceof Error ? err.message : 'Unknown error'
      }`
      logger.error('Cytoscape lazy-load error:', err)
    } finally {
      loading.value = false
    }
  }

  async function ensureReady(): Promise<void> {
    await load()
    if (error.value) return
    await onReady()
  }

  function retry(): void {
    // Fire-and-forget — the UI reflects progress via `loading`/`error`.
    ensureReady()
  }

  return { loading, error, cytoscapeModule, fcoseModule, ensureReady, retry }
}
