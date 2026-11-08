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
import { CODE_SMELL_TYPES, type Problem } from './analyticsTypes'
import { buildSmellsExport } from './codeSmellSummary'

export const SMELL_CATEGORY_ALL = 'all'
export const SMELL_CATEGORY_DEFAULT = 'code'
export const SMELL_CATEGORIES = [SMELL_CATEGORY_DEFAULT, 'test', SMELL_CATEGORY_ALL] as const
export type SmellCategory = (typeof SMELL_CATEGORIES)[number]

export function useCodeSmellProblems(withSourceId: (url: string) => string) {
  const smellCategory = ref<SmellCategory>(SMELL_CATEGORY_DEFAULT)
  const smellProblems = ref<Problem[]>([])

  const endpoint = useFetchEndpoint<{ status?: string; problems?: Problem[] }, Problem[]>(
    {
      path: '/api/analytics/codebase/problems',
      scopeToSource: true,
      label: 'Code smells endpoint',
      pickData: (raw) => (raw.status === 'no_data' ? [] : raw.problems ?? []),
      onSuccess: (d) => { smellProblems.value = d },
      // A failed load must not leave the previous category's findings on screen.
      onError: () => { smellProblems.value = [] },
    },
    { withSourceId },
  )

  const loadSmellProblems = () =>
    endpoint.load(
      smellCategory.value === SMELL_CATEGORY_ALL ? undefined : { file_category: smellCategory.value },
    )

  const selectSmellCategory = async (category: SmellCategory) => {
    smellCategory.value = category
    await loadSmellProblems()
  }

  const smellsForPanel = computed(() =>
    smellProblems.value
      .filter((p) => p.type && CODE_SMELL_TYPES.has(p.type))
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
  const smellsExport = computed(() => buildSmellsExport(smellsForPanel.value, smellCategory.value))

  return {
    smellCategory,
    smellsForPanel,
    smellsExport,
    smellsError: endpoint.error,
    smellsLoading: endpoint.loading,
    loadSmellProblems,
    selectSmellCategory,
  }
}
