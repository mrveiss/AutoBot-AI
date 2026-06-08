// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeVectorization Composable
 *
 * Manages failed vectorization jobs — fetching, retrying, deleting, and
 * clearing all failed jobs. Extracted from FailedVectorizationsManager (#6041).
 *
 * All mutations are wrapped in useLoadingState so the component only needs
 * to bind the exposed refs instead of managing its own loading/error state.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeVectorization')

// ==================== Types ====================

export interface FailedVectorizationJob {
  job_id: string
  fact_id: string
  status: string
  started_at: string
  completed_at: string | null
  error: string | null
}

interface FailedJobsResponse {
  status: string
  failed_jobs: FailedVectorizationJob[]
  message?: string
  new_job_id?: string
  deleted_count?: number
}

// ==================== Bare imperative API ====================

/**
 * Fetch all failed vectorization jobs.
 * GET /api/knowledge_base/vectorize_jobs/failed
 */
export const fetchFailedVectorizationJobs = async (): Promise<FailedVectorizationJob[]> => {
  const data = await apiClient.get<FailedJobsResponse>(
    `${getApiBase()}/knowledge_base/vectorize_jobs/failed`
  )
  if (data.status !== 'success') {
    throw new Error('Failed to load failed jobs')
  }
  return data.failed_jobs
}

/**
 * Retry a single failed vectorization job.
 * POST /api/knowledge_base/vectorize_jobs/{jobId}/retry
 * Returns the new job ID.
 */
export const retryVectorizationJob = async (jobId: string): Promise<string> => {
  const data = await apiClient.post<FailedJobsResponse>(
    `${getApiBase()}/knowledge_base/vectorize_jobs/${jobId}/retry`
  )
  if (data.status !== 'success') {
    throw new Error(`Failed to retry job: ${data.message ?? 'Unknown error'}`)
  }
  logger.debug(`Job ${jobId} retry started as ${data.new_job_id}`)
  return data.new_job_id ?? jobId
}

/**
 * Delete a single failed vectorization job.
 * DELETE /api/knowledge_base/vectorize_jobs/{jobId}
 */
export const deleteVectorizationJob = async (jobId: string): Promise<void> => {
  const data = await apiClient.delete<FailedJobsResponse>(
    `${getApiBase()}/knowledge_base/vectorize_jobs/${jobId}`
  )
  if (data.status !== 'success') {
    throw new Error(data.message ?? 'Failed to delete job')
  }
}

/**
 * Clear all failed vectorization jobs.
 * DELETE /api/knowledge_base/vectorize_jobs/failed/clear
 * Returns the number of deleted jobs.
 */
export const clearAllFailedVectorizationJobs = async (): Promise<number> => {
  const data = await apiClient.delete<FailedJobsResponse>(
    `${getApiBase()}/knowledge_base/vectorize_jobs/failed/clear`
  )
  if (data.status !== 'success') {
    throw new Error(data.message ?? 'Failed to clear jobs')
  }
  logger.debug(`Cleared ${data.deleted_count} failed jobs`)
  return data.deleted_count ?? 0
}

// ==================== Reactive composable ====================

export interface UseKnowledgeVectorizationReturn {
  /** Current list of failed vectorization jobs. */
  failedJobs: Readonly<Ref<FailedVectorizationJob[]>>
  /** Set of job IDs currently being retried. */
  retryingJobs: Readonly<Ref<Set<string>>>
  /** True while any loading/mutation is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error from any managed action; cleared on the next call. */
  error: Readonly<Ref<string | null>>
  /** Fetch/refresh the full list of failed jobs. */
  refreshFailedJobs: () => Promise<void>
  /** Retry a single job by ID. */
  retryJob: (jobId: string) => Promise<void>
  /** Delete a single job by ID. */
  deleteJob: (jobId: string) => Promise<void>
  /** Clear all failed jobs. */
  clearAllFailed: () => Promise<void>
  // Imperative passthroughs
  fetchFailedVectorizationJobs: typeof fetchFailedVectorizationJobs
  retryVectorizationJob: typeof retryVectorizationJob
  deleteVectorizationJob: typeof deleteVectorizationJob
  clearAllFailedVectorizationJobs: typeof clearAllFailedVectorizationJobs
}

export function useKnowledgeVectorization(): UseKnowledgeVectorizationReturn {
  const failedJobs = ref<FailedVectorizationJob[]>([])
  const retryingJobs = ref<Set<string>>(new Set())
  const error = ref<string | null>(null)
  const { isLoading, wrap } = useLoadingState()

  const refreshFailedJobs = async (): Promise<void> => {
    error.value = null
    await wrap(async () => {
      const jobs = await fetchFailedVectorizationJobs()
      failedJobs.value = jobs
    }).catch((err: unknown) => {
      error.value = err instanceof Error ? err.message : String(err)
    })
  }

  const retryJob = async (jobId: string): Promise<void> => {
    retryingJobs.value = new Set([...retryingJobs.value, jobId])
    try {
      await retryVectorizationJob(jobId)
      failedJobs.value = failedJobs.value.filter(job => job.job_id !== jobId)
    } catch (err) {
      logger.error('Error retrying job:', err)
      throw err instanceof Error ? err : new Error(`Error retrying job: ${err}`)
    } finally {
      const next = new Set(retryingJobs.value)
      next.delete(jobId)
      retryingJobs.value = next
    }
  }

  const deleteJob = async (jobId: string): Promise<void> => {
    error.value = null
    await wrap(async () => {
      await deleteVectorizationJob(jobId)
      failedJobs.value = failedJobs.value.filter(job => job.job_id !== jobId)
    }).catch((err: unknown) => {
      error.value = err instanceof Error ? err.message : String(err)
    })
  }

  const clearAllFailed = async (): Promise<void> => {
    error.value = null
    await wrap(async () => {
      await clearAllFailedVectorizationJobs()
      failedJobs.value = []
    }).catch((err: unknown) => {
      error.value = err instanceof Error ? err.message : String(err)
    })
  }

  return {
    failedJobs: readonly(failedJobs) as Readonly<Ref<FailedVectorizationJob[]>>,
    retryingJobs: readonly(retryingJobs) as Readonly<Ref<Set<string>>>,
    isLoading: readonly(isLoading),
    error: readonly(error),
    refreshFailedJobs,
    retryJob,
    deleteJob,
    clearAllFailed,
    fetchFailedVectorizationJobs,
    retryVectorizationJob,
    deleteVectorizationJob,
    clearAllFailedVectorizationJobs,
  }
}
