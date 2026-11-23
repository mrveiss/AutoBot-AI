// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useDriftPrune - #22082: remove exactly the drift-confirmed
 * `removed_from_source` files of one component.
 *
 * Two steps, mirroring the backend (autobot-slm-backend/api/drift_prune.py):
 *   1. `preview(component)` lists what would be removed.
 *   2. `confirm(component)` sends back that exact list; the server re-checks
 *      each path against git and refuses any that is no longer eligible.
 *
 * Kept out of useCodeSync.ts, which is already far past the size the file
 * guard tolerates growing.
 */

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

export type DriftPrunePreview = components['schemas']['DriftPrunePreview']
export type DriftPruneResponse = components['schemas']['DriftPruneResponse']

/**
 * Most paths one confirm may send. Mirrors `_MAX_PATHS` (the `max_length` of
 * `DriftPruneRequest.paths`) in autobot-slm-backend/api/drift_prune.py; the API
 * schema does not expose the number, so a larger list is cut into batches here
 * instead of coming back 422.
 */
export const DRIFT_PRUNE_MAX_PATHS = 5000

export function useDriftPrune() {
  const { t } = useI18n()
  const previews = ref<Record<string, DriftPrunePreview>>({})
  const results = ref<Record<string, DriftPruneResponse>>({})
  const busyComponent = ref<string | null>(null)
  const error = ref<string | null>(null)

  async function run<T>(component: string, call: () => Promise<T>): Promise<T | null> {
    busyComponent.value = component
    error.value = null
    try {
      return await call()
    } catch (e) {
      error.value = e instanceof Error ? e.message : t('fullTreeDriftPanel.prune.requestFailed')
      return null
    } finally {
      busyComponent.value = null
    }
  }

  async function fetchPreview(component: string): Promise<DriftPrunePreview | null> {
    const data = await run(component, () =>
      slmApiClient.call('post', '/api/code-sync/drift/prune/preview', { body: { component } }),
    )
    if (data) previews.value = { ...previews.value, [component]: data }
    return data
  }

  async function preview(component: string): Promise<DriftPrunePreview | null> {
    const data = await fetchPreview(component)
    if (data) delete results.value[component]
    return data
  }

  /** The files one confirm covers: the first batch of the previewed list, and the full total. */
  function batch(component: string): { files: DriftPrunePreview['files']; total: number } {
    const all = previews.value[component]?.files ?? []
    return { files: all.slice(0, DRIFT_PRUNE_MAX_PATHS), total: all.length }
  }

  /** "batch of N of total M" while the preview is cut into batches, else null. */
  function batchNote(component: string): string | null {
    const { files, total } = batch(component)
    return total > files.length ? t('fullTreeDriftPanel.prune.batch', { count: files.length, total }) : null
  }

  async function confirm(component: string): Promise<DriftPruneResponse | null> {
    const paths = batch(component).files.map((file) => file.path)
    if (paths.length === 0) return null
    const data = await run(component, () =>
      slmApiClient.call('post', '/api/code-sync/drift/prune', { body: { component, paths } }),
    )
    if (!data) return null
    results.value = { ...results.value, [component]: data }
    delete previews.value[component]
    // Re-preview only when something was removed: the next batch (or what was left in place)
    // is then shown for its own confirm. A fully refused batch would just repeat the same list.
    if (data.removed.length === 0) return data
    const next = await fetchPreview(component)
    if (next && next.files.length === 0) delete previews.value[component]
    return data
  }

  function cancel(component: string): void {
    delete previews.value[component]
  }

  return { previews, results, busyComponent, error, preview, confirm, cancel, batch, batchNote }
}
