/**
 * useManPages Composable
 *
 * Man-page integration, population, summary fetch, and AutoBot-docs
 * population (grouped here because it shares the same backend ingestion
 * pattern with man pages).
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
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

export function useManPages() {
  /**
   * Fetch man pages summary.
   * Returns null on error so consumers can treat missing summary as non-fatal.
   */
  const fetchManPagesSummary = async (): Promise<ManPagesSummary | null> => {
    try {
      return await apiClient.get<ManPagesSummary>(`${getApiBase()}/knowledge_base/man_pages/summary`)
    } catch {
      return null
    }
  }

  /**
   * Integrate man pages for a specific machine.
   */
  const integrateManPages = (machineId: string): Promise<IntegrationResponse> =>
    apiClient.post<IntegrationResponse>(
      `${getApiBase()}/knowledge_base/man_pages/integrate`,
      { machine_id: machineId }
    )

  /**
   * Populate man pages for a specific machine.
   * POST /api/knowledge_base/populate_man_pages
   */
  const populateManPages = (machineId: string): Promise<ManPagesPopulateResponse> =>
    apiClient.post<ManPagesPopulateResponse>(
      `${getApiBase()}/knowledge_base/populate_man_pages`,
      { machine_id: machineId }
    )

  /**
   * Populate AutoBot documentation.
   * POST /api/knowledge_base/populate_autobot_docs
   */
  const populateAutoBotDocs = (): Promise<AutoBotDocsResponse> =>
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
  const searchManPages = (query: string) =>
    apiClient.post(`${getApiBase()}/knowledge_base/search`, {
      query,
      category: 'man_pages',
    })

  return {
    fetchManPagesSummary,
    integrateManPages,
    populateManPages,
    populateAutoBotDocs,
    searchManPages,
  }
}
