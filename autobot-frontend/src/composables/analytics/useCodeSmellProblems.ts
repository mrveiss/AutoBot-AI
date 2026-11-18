// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Code smells for the panel and its export, from ONE load (#20493).
 *
 * The panel's cards and the exported report both read `smellsForPanel`, counted
 * by `summarizeSmells`.
 *
 * This is a second `/problems` request beside the Problems Report's because the
 * category filter is applied on the server (the report must keep showing every
 * finding), so the two lists are different slices of the store. The category
 * (production code, test files, or all) is sent to the backend as
 * `file_category` so the server returns only that slice.
 */

import { computed, ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { isCodeSmellType, type Problem } from './analyticsTypes'
import { buildSmellsExport } from './codeSmellSummary'

export const SMELL_CATEGORY_ALL = 'all'
export const SMELL_CATEGORY_DEFAULT = 'code'
export const SMELL_CATEGORIES = [SMELL_CATEGORY_DEFAULT, 'test', SMELL_CATEGORY_ALL] as const
export type SmellCategory = (typeof SMELL_CATEGORIES)[number]

export function useCodeSmellProblems(withSourceId: (url: string) => string) {
  const smellCategory = ref<SmellCategory>(SMELL_CATEGORY_DEFAULT)
  const smellProblems = ref<Problem[]>([])
  // The category the rows in `smellProblems` were loaded for; `smellCategory` is
  // the selection and runs ahead of it while a load is in flight.
  const loadedCategory = ref<SmellCategory>(SMELL_CATEGORY_DEFAULT)

  // One request per category (#21784): a callback belongs to the request that made it, so a response
  // that was superseded by a newer load (another category) is ignored instead of labelling its rows.
  interface SmellRequest { category: SmellCategory; seq: number }
  let latestSeq = 0
  let inFlight: { request: SmellRequest; done: Promise<void> } | null = null
  const isCurrent = (r: SmellRequest) => r.seq === latestSeq

  const endpoint = useFetchEndpoint<{ status?: string; problems?: Problem[] }, Problem[], SmellRequest>(
    {
      path: '/api/analytics/codebase/problems',
      scopeToSource: true,
      requireSource: true,
      label: 'Code smells endpoint',
      pickData: (raw) => (raw.status === 'no_data' ? [] : raw.problems ?? []),
      onSuccess: (d, _raw, r) => {
        if (!isCurrent(r)) return
        smellProblems.value = d
        loadedCategory.value = r.category
      },
      // A failed load must not leave the previous category's findings on screen.
      onError: (_message, _err, r) => {
        if (!isCurrent(r)) return
        smellProblems.value = []
        loadedCategory.value = r.category
      },
    },
    { withSourceId },
  )

  /**
   * Load the selected category. While a load of the SAME category is in flight its request is reused:
   * `useFetchEndpoint.load` cancels the previous request, so a refresh timer shorter than the response
   * time would otherwise cancel every request and the panel would never leave the previous category.
   */
  const loadSmellProblems = () => {
    const category = smellCategory.value
    if (inFlight && inFlight.request.category === category) return inFlight.done
    const request: SmellRequest = { category, seq: ++latestSeq }
    const done = endpoint
      .load(category === SMELL_CATEGORY_ALL ? undefined : { file_category: category }, request)
      .finally(() => {
        if (inFlight?.request === request) inFlight = null
      })
    inFlight = { request, done }
    return done
  }

  /** Drop the loaded rows (cache clear); they are the default category's again. */
  const resetSmells = () => {
    smellProblems.value = []
    loadedCategory.value = smellCategory.value
  }

  const selectSmellCategory = async (category: SmellCategory) => {
    smellCategory.value = category
    await loadSmellProblems()
  }

  const smellsForPanel = computed(() =>
    smellProblems.value
      .filter((p) => isCodeSmellType(p.type))
      .map((p) => ({
        severity: p.severity,
        description: p.description || p.message,
        file_path: p.file_path,
        line_number: p.line_number ?? p.line,
        suggestion: p.suggestion,
        smell_type: p.type,
      })),
  )

  /** The export's data: the cards' list and the cards' counts, nothing else. */
  /** True while the rows on hand belong to another category than the selected one (a load is in flight). */
  const smellsStale = computed(() => loadedCategory.value !== smellCategory.value)

  const smellsExport = computed(() => buildSmellsExport(smellsForPanel.value, loadedCategory.value))

  return {
    smellCategory,
    smellsForPanel,
    smellsExport,
    smellsStale,
    smellsError: endpoint.error,
    smellsLoading: endpoint.loading,
    loadSmellProblems,
    selectSmellCategory,
    resetSmells,
  }
}
