// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useModelPicker — shared multi-model picker wiring (#10755, dedupe #10718).
 *
 * Both MultiModelChat and BenchmarkView build a checkbox picker from the live
 * /api/models list and seed the selection once that list loads. This composable
 * centralises that identical wiring:
 *   - fetch the model list on mount (fire-and-forget; empty until it resolves,
 *     so the picker never renders fake/hardcoded models),
 *   - expose `availableModels` = union of live names + any current selection
 *     (a persisted choice stays selectable even if its provider is briefly down),
 *   - seed `selectedModels` from the live list exactly once, and only while the
 *     caller has no choice yet (default guard: selection is empty). Because
 *     callers back `selectedModels` with a persisted (localStorage) ref via
 *     useMultiModelCompare, this guard also respects a persisted choice.
 *
 * The `models` ref is re-exported for callers that need per-model metadata
 * (e.g. MultiModelChat's context-window labels); BenchmarkView ignores it.
 */

import { computed, watch, onMounted, type ComputedRef, type Ref } from 'vue'
import { useAvailableModels, type AvailableModel } from './useAvailableModels'

export interface UseModelPickerOptions {
  /**
   * Seed the selection only when this returns true. Defaults to "selection is
   * empty", which — with a persisted selection ref — also means "no persisted
   * choice yet".
   */
  shouldSeed?: () => boolean
}

export interface UseModelPickerReturn {
  /** Full model metadata list (name, provider, context_window, …). */
  models: Ref<AvailableModel[]>
  /** Names of models currently reported available. */
  availableModelNames: ComputedRef<string[]>
  /** Picker list: live available names ∪ current selection. */
  availableModels: ComputedRef<string[]>
  /** Re-fetch the live model list. */
  fetchModels: () => Promise<void>
}

export function useModelPicker(
  selectedModels: Ref<string[]>,
  options: UseModelPickerOptions = {},
): UseModelPickerReturn {
  const { models, availableModelNames, fetchModels } = useAvailableModels()

  const shouldSeed = options.shouldSeed ?? (() => selectedModels.value.length === 0)

  // Picker list: live available models plus any previously-stored selections
  // (so a persisted choice stays selectable even if a provider is briefly down).
  // Before the fetch resolves this is empty — the picker renders no fake models.
  const availableModels = computed<string[]>(() =>
    Array.from(new Set<string>([...availableModelNames.value, ...selectedModels.value])),
  )

  // Seed the selection from the live list once it loads, but only when the user
  // has no choice yet. The watcher handles the async fetch timing.
  watch(availableModelNames, (names) => {
    if (shouldSeed() && names.length > 0) {
      selectedModels.value = [...names]
    }
  })

  onMounted(() => {
    fetchModels().catch(() => {})
  })

  return { models, availableModelNames, availableModels, fetchModels }
}
