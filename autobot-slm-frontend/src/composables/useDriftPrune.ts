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
import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

export type DriftPrunePreview = components['schemas']['DriftPrunePreview']
export type DriftPruneResponse = components['schemas']['DriftPruneResponse']

export function useDriftPrune() {
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
      error.value = e instanceof Error ? e.message : 'Drift prune request failed'
      return null
    } finally {
      busyComponent.value = null
    }
  }

  async function preview(component: string): Promise<DriftPrunePreview | null> {
    const data = await run(component, () =>
      slmApiClient.post<DriftPrunePreview>('/code-sync/drift/prune/preview', { component }),
    )
    if (data) {
      previews.value = { ...previews.value, [component]: data }
      delete results.value[component]
    }
    return data
  }

  async function confirm(component: string): Promise<DriftPruneResponse | null> {
    const shown = previews.value[component]
    if (!shown || shown.files.length === 0) return null
    const paths = shown.files.map((file) => file.path)
    const data = await run(component, () =>
      slmApiClient.post<DriftPruneResponse>('/code-sync/drift/prune', { component, paths }),
    )
    if (data) {
      results.value = { ...results.value, [component]: data }
      delete previews.value[component]
    }
    return data
  }

  function cancel(component: string): void {
    delete previews.value[component]
  }

  return { previews, results, busyComponent, error, preview, confirm, cancel }
}
