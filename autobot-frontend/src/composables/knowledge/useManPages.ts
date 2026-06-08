// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useManPages Composable
 *
 * Man-page integration, population, summary fetch, and AutoBot-docs
 * population (grouped here because it shares the same backend ingestion
 * pattern with man pages).
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Reactive refs layer (#5149): the composable now owns loading/error state
 * for `refresh` (summary fetch). The bare imperative functions remain
 * exported at module scope for the `useKnowledgeBase` BC shim.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '../useLoadingState'
import type {
  IntegrationResponse,
  ManPagesPopulateResponse,
  AutoBotDocsResponse,
} from '@/types/knowledgeBase'

export interface ManPagesSummary {
  status?: string
  message?: string
  successful?: number
  processed?: number
  current_man_page_files?: number
  total_available_tools?: number
  integration_date?: string
  available_commands?: string[]
}

// ==================== Bare imperative API ====================

/**
 * Fetch man pages summary.
 * Returns null on error so consumers can treat missing summary as non-fatal.
 */
export const fetchManPagesSummary = async (): Promise<ManPagesSummary | null> => {
  try {
    return await apiClient.get<ManPagesSummary>(`${getApiBase()}/knowledge_base/man_pages/summary`)
  } catch {
    return null
  }
}

/**
 * Integrate man pages for a specific machine.
 */
export const integrateManPages = (machineId: string): Promise<IntegrationResponse> =>
  apiClient.post<IntegrationResponse>(
    `${getApiBase()}/knowledge_base/man_pages/integrate`,
    { machine_id: machineId }
  )

/**
 * Populate man pages for a specific machine.
 * POST /api/knowledge_base/populate_man_pages
 */
export const populateManPages = (machineId: string): Promise<ManPagesPopulateResponse> =>
  apiClient.post<ManPagesPopulateResponse>(
    `${getApiBase()}/knowledge_base/populate_man_pages`,
    { machine_id: machineId }
  )

/**
 * Populate AutoBot documentation.
 * POST /api/knowledge_base/populate_autobot_docs
 */
export const populateAutoBotDocs = (): Promise<AutoBotDocsResponse> =>
  apiClient.post<AutoBotDocsResponse>(
    `${getApiBase()}/knowledge_base/populate_autobot_docs`,
    {}
  )

/**
 * Search man pages (placeholder — current backend search returns man
 * pages through the unified /search endpoint; callers should invoke
 * useKnowledgeFacts().searchKnowledge with a man-page filter instead).
 * Kept as a thin wrapper here for API discoverability.
 */
export const searchManPages = (query: string) =>
  apiClient.post(`${getApiBase()}/knowledge_base/search`, {
    query,
    category: 'man_pages',
  })

// ==================== Reactive composable ====================

export interface UseManPagesReturn {
  /** Latest man-pages summary. */
  summary: Readonly<Ref<ManPagesSummary | null>>
  /** True while any refresh is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error; cleared on next call. */
  error: Readonly<Ref<Error | null>>
  /** Fetch summary, update `summary`. */
  refresh: () => Promise<ManPagesSummary | null>
  // Imperative passthroughs — BC with pre-#5149 callers
  fetchManPagesSummary: typeof fetchManPagesSummary
  integrateManPages: typeof integrateManPages
  populateManPages: typeof populateManPages
  populateAutoBotDocs: typeof populateAutoBotDocs
  searchManPages: typeof searchManPages
}

export function useManPages(): UseManPagesReturn {
  const summary = ref<ManPagesSummary | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const error = ref<Error | null>(null)

  const refresh = async (): Promise<ManPagesSummary | null> => {
    error.value = null
    return wrap(async () => {
      const data = await fetchManPagesSummary()
      summary.value = data
      return data
    })
  }

  return {
    summary: readonly(summary) as Readonly<Ref<ManPagesSummary | null>>,
    isLoading: readonly(isLoading),
    error: readonly(error),
    refresh,
    fetchManPagesSummary,
    integrateManPages,
    populateManPages,
    populateAutoBotDocs,
    searchManPages,
  }
}
