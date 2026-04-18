/**
 * useKnowledgeJobs Composable
 *
 * Vectorization API calls + background job polling. These are the
 * low-level endpoints; `useKnowledgeVectorization` layers state + dedup
 * caching on top of them.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 */

import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'
import { getApiBase } from '@/config/ssot-config'
import type {
  VectorizationStatusResponse,
  VectorizationResponse,
} from '@/types/knowledgeBase'

export function useKnowledgeJobs() {
  /**
   * Get vectorization status.
   * Issue #552: Fixed path — backend uses /api/knowledge_base/vectorize_facts/status.
   */
  const getVectorizationStatus = (): Promise<VectorizationStatusResponse> =>
    apiClient.get<VectorizationStatusResponse>(
      `${getApiBase()}/knowledge_base/vectorize_facts/status`
    )

  /**
   * Generate vector embeddings for all existing facts using batched processing.
   * @param batchSize - Number of facts to process per batch (default: 50)
   * @param batchDelay - Delay in seconds between batches (default: 0.5)
   * @param skipExisting - Skip facts that already have vectors (default: true)
   */
  const vectorizeFacts = (
    batchSize: number = 50,
    batchDelay: number = 0.5,
    skipExisting: boolean = true
  ): Promise<VectorizationResponse> => {
    // Knowledge-specific timeout (300s for vectorization operations)
    const knowledgeTimeout = appConfig.getTimeout('knowledge')

    return apiClient.post<VectorizationResponse>(
      `${getApiBase()}/knowledge_base/vectorize_facts`,
      {
        batch_size: batchSize,
        batch_delay: batchDelay,
        skip_existing: skipExisting,
      },
      { timeout: knowledgeTimeout }
    )
  }

  /**
   * Poll status of a background job (e.g., knowledge refresh, reindexing).
   * GET /api/knowledge_base/job_status/{task_id}
   *
   * Returns current status: PENDING, PROGRESS, SUCCESS, or FAILURE.
   */
  const pollJobStatus = (taskId: string): Promise<unknown> =>
    apiClient.get(`${getApiBase()}/knowledge_base/job_status/${taskId}`)

  return {
    getVectorizationStatus,
    vectorizeFacts,
    pollJobStatus,
  }
}
