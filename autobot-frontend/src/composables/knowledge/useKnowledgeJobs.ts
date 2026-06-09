// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeJobs Composable
 *
 * Vectorization API calls + background job polling. These are the
 * low-level endpoints; `useKnowledgeVectorization` layers state + dedup
 * caching on top of them, and `usePollingJob` (#5191) provides generic
 * managed interval polling on top of `pollJobStatus`.
 *
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Reactive refs layer (#5195, follow-up to #5149): the composable now owns
 * loading/error state via `ref`s and exposes managed `refreshStatus` and
 * `runVectorization` actions. The bare imperative functions remain exported at
 * module scope so non-reactive consumers (and the `useKnowledgeBase` BC shim)
 * keep working unchanged. `pollJobStatus` is a one-shot snapshot and is kept
 * imperative — for managed polling, use `usePollingJob(pollJobStatus, ...)`.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'
import { getApiBase } from '@/config/ssot-config'
import type {
  VectorizationStatusResponse,
  VectorizationResponse,
} from '@/types/knowledgeBase'

// ==================== Bare imperative API ====================

/**
 * Get vectorization status.
 * Issue #552: Fixed path — backend uses /api/knowledge_base/vectorize_facts/status.
 */
export const getVectorizationStatus = (): Promise<VectorizationStatusResponse> =>
  apiClient.get<VectorizationStatusResponse>(
    `${getApiBase()}/knowledge_base/vectorize_facts/status`
  )

/**
 * Generate vector embeddings for all existing facts using batched processing.
 * @param batchSize - Number of facts to process per batch (default: 50)
 * @param batchDelay - Delay in seconds between batches (default: 0.5)
 * @param skipExisting - Skip facts that already have vectors (default: true)
 */
export const vectorizeFacts = (
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
 *
 * One-shot snapshot. For managed interval polling, use `usePollingJob`
 * (#5191) with this fetcher.
 */
export const pollJobStatus = (taskId: string): Promise<unknown> =>
  apiClient.get(`${getApiBase()}/knowledge_base/job_status/${taskId}`)

// ==================== Reactive composable ====================

export interface UseKnowledgeJobsReturn {
  /** Latest vectorization status snapshot, or null if never fetched. */
  vectorizationStatus: Readonly<Ref<VectorizationStatusResponse | null>>
  /** Latest vectorization run result, or null if never run. */
  vectorizationResult: Readonly<Ref<VectorizationResponse | null>>
  /** True while refreshStatus is in-flight. */
  isLoadingStatus: Readonly<Ref<boolean>>
  /** True while runVectorization is in-flight. */
  isVectorizing: Readonly<Ref<boolean>>
  /** Last error raised by a managed action; cleared on the next call. */
  error: Readonly<Ref<Error | null>>
  /** Fetch vectorization status, update `vectorizationStatus` + state refs. */
  refreshStatus: () => Promise<VectorizationStatusResponse>
  /** Run vectorization, update `vectorizationResult` + state refs. */
  runVectorization: (
    batchSize?: number,
    batchDelay?: number,
    skipExisting?: boolean
  ) => Promise<VectorizationResponse>
  // Imperative passthroughs — BC with pre-#5195 callers
  getVectorizationStatus: typeof getVectorizationStatus
  vectorizeFacts: typeof vectorizeFacts
  pollJobStatus: typeof pollJobStatus
}

export function useKnowledgeJobs(): UseKnowledgeJobsReturn {
  const vectorizationStatus = ref<VectorizationStatusResponse | null>(null)
  const vectorizationResult = ref<VectorizationResponse | null>(null)
  const isLoadingStatus = ref(false)
  const isVectorizing = ref(false)
  const error = ref<Error | null>(null)

  const refreshStatus = async (): Promise<VectorizationStatusResponse> => {
    isLoadingStatus.value = true
    error.value = null
    try {
      const data = await getVectorizationStatus()
      vectorizationStatus.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      throw err
    } finally {
      isLoadingStatus.value = false
    }
  }

  const runVectorization = async (
    batchSize: number = 50,
    batchDelay: number = 0.5,
    skipExisting: boolean = true
  ): Promise<VectorizationResponse> => {
    isVectorizing.value = true
    error.value = null
    try {
      const data = await vectorizeFacts(batchSize, batchDelay, skipExisting)
      vectorizationResult.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      throw err
    } finally {
      isVectorizing.value = false
    }
  }

  return {
    vectorizationStatus: readonly(vectorizationStatus) as Readonly<
      Ref<VectorizationStatusResponse | null>
    >,
    vectorizationResult: readonly(vectorizationResult) as Readonly<
      Ref<VectorizationResponse | null>
    >,
    isLoadingStatus: readonly(isLoadingStatus),
    isVectorizing: readonly(isVectorizing),
    error: readonly(error),
    refreshStatus,
    runVectorization,
    getVectorizationStatus,
    vectorizeFacts,
    pollJobStatus,
  }
}
