/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Vue Composable for Batch Processing API
 * Issue #584 - Batch Processing Manager
 */

import { ref, computed } from 'vue'
import { useApiWithState } from './useApi'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'
import type {
  BatchJob,
  BatchTemplate,
  BatchSchedule,
  BatchJobsListResponse,
  BatchTemplatesListResponse,
  BatchSchedulesListResponse,
  BatchHealthResponse,
  BatchJobsFilter,
  BatchJobLogsResponse,
  CreateBatchJobRequest,
  CreateBatchJobResponse,
  CreateBatchTemplateRequest,
  CreateBatchScheduleRequest,
  BatchJobStatus
} from '@/types/batch-processing'
import { isTerminalStatus } from '@/types/batch-processing'
import { getApiBase } from '@/config/ssot-config'
import { useProbeBackedHealth } from '@/composables/useProbeBackedHealth'

const logger = createLogger('useBatchProcessing')

/**
 * Composable for batch processing API calls
 */
export function useBatchProcessingApi() {
  const { api, withErrorHandling } = useApiWithState()

  return {
    /**
     * List all batch jobs with optional filtering
     */
    async listJobs(filter?: BatchJobsFilter): Promise<BatchJobsListResponse | null> {
      return withErrorHandling(
        async () => {
          const params = new URLSearchParams()
          if (filter?.status) params.append('status', filter.status)
          if (filter?.job_type) params.append('job_type', filter.job_type)
          if (filter?.limit) params.append('limit', filter.limit.toString())

          const queryString = params.toString()
          const url = `${getApiBase()}/batch-jobs${queryString ? `?${queryString}` : ''}`
          return await api.get<any>(url)
        },
        {
          errorMessage: 'Failed to load batch jobs',
          fallbackValue: {
            jobs: [],
            total_count: 0,
            pending_count: 0,
            running_count: 0,
            completed_count: 0,
            failed_count: 0
          }
        }
      )
    },

    /**
     * Get single batch job by ID
     */
    async getJob(jobId: string): Promise<BatchJob | null> {
      return withErrorHandling(
        async () => {
          return await api.get<any>(`${getApiBase()}/batch-jobs/${jobId}`)
        },
        {
          errorMessage: 'Failed to get batch job',
          fallbackValue: null
        }
      )
    },

    /**
     * Create a new batch job
     */
    async createJob(request: CreateBatchJobRequest): Promise<CreateBatchJobResponse | null> {
      return withErrorHandling(
        async () => {
          return await api.post<any>(`${getApiBase()}/batch-jobs`, request)
        },
        {
          errorMessage: 'Failed to create batch job'
        }
      )
    },

    /**
     * Delete a batch job
     */
    async deleteJob(jobId: string): Promise<{ status: string } | null> {
      return withErrorHandling(
        async () => {
          return await api.delete<any>(`${getApiBase()}/batch-jobs/${jobId}`)
        },
        {
          errorMessage: 'Failed to delete batch job'
        }
      )
    },

    /**
     * Cancel a running batch job
     */
    async cancelJob(jobId: string): Promise<{ status: string } | null> {
      return withErrorHandling(
        async () => {
          return await api.post<any>(`${getApiBase()}/batch-jobs/${jobId}/cancel`)
        },
        {
          errorMessage: 'Failed to cancel batch job'
        }
      )
    },

    /**
     * Get batch job logs
     */
    async getJobLogs(jobId: string): Promise<BatchJobLogsResponse | null> {
      return withErrorHandling(
        async () => {
          return await api.get<any>(`${getApiBase()}/batch-jobs/${jobId}/logs`)
        },
        {
          errorMessage: 'Failed to get batch job logs',
          fallbackValue: { job_id: jobId, logs: [] }
        }
      )
    },

    /**
     * List all batch templates
     */
    async listTemplates(): Promise<BatchTemplatesListResponse | null> {
      return withErrorHandling(
        async () => {
          return await api.get<any>(`${getApiBase()}/batch-templates`)
        },
        {
          errorMessage: 'Failed to load batch templates',
          fallbackValue: { templates: [], total_count: 0 }
        }
      )
    },

    /**
     * Create a new batch template
     */
    async createTemplate(request: CreateBatchTemplateRequest): Promise<BatchTemplate | null> {
      return withErrorHandling(
        async () => {
          return await api.post<any>(`${getApiBase()}/batch-templates`, request)
        },
        {
          errorMessage: 'Failed to create batch template'
        }
      )
    },

    /**
     * Delete a batch template
     */
    async deleteTemplate(templateId: string): Promise<{ status: string } | null> {
      return withErrorHandling(
        async () => {
          return await api.delete<any>(`${getApiBase()}/batch-templates/${templateId}`)
        },
        {
          errorMessage: 'Failed to delete batch template'
        }
      )
    },

    /**
     * List all batch schedules
     */
    async listSchedules(): Promise<BatchSchedulesListResponse | null> {
      return withErrorHandling(
        async () => {
          return await api.get<any>(`${getApiBase()}/batch-schedules`)
        },
        {
          errorMessage: 'Failed to load batch schedules',
          fallbackValue: { schedules: [], total_count: 0 }
        }
      )
    },

    /**
     * Create a new batch schedule
     */
    async createSchedule(request: CreateBatchScheduleRequest): Promise<BatchSchedule | null> {
      return withErrorHandling(
        async () => {
          return await api.post<any>(`${getApiBase()}/batch-schedules`, request)
        },
        {
          errorMessage: 'Failed to create batch schedule'
        }
      )
    },

    /**
     * Toggle schedule enabled state
     */
    async toggleSchedule(scheduleId: string, enabled: boolean): Promise<BatchSchedule | null> {
      return withErrorHandling(
        async () => {
          return await api.patch(`${getApiBase()}/batch-schedules/${scheduleId}`, { enabled })
        },
        {
          errorMessage: 'Failed to update batch schedule'
        }
      )
    },

    /**
     * Delete a batch schedule
     */
    async deleteSchedule(scheduleId: string): Promise<{ status: string } | null> {
      return withErrorHandling(
        async () => {
          return await api.delete<any>(`${getApiBase()}/batch-schedules/${scheduleId}`)
        },
        {
          errorMessage: 'Failed to delete batch schedule'
        }
      )
    },

    /**
     * Get batch service health status.
     *
     * Issue #6902: migrated off the legacy /api/batch-jobs/health (sunset
     * 2026-09-02) onto the canonical aggregator at /api/system/health. The
     * `batch_jobs` probe populates `data.redis_connected`; `active_jobs` and
     * `total_jobs` were never returned by the legacy backend response, so
     * the fallback values match the prior behaviour.
     */
    getHealth: useProbeBackedHealth<BatchHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy: (probe, data) => ({
        status: 'healthy',
        active_jobs: 0,
        total_jobs: 0,
        redis_connected: Boolean(data.redis_connected),
        message: probe.detail,
      }),
      buildUnavailable: (message) => ({
        status: 'unavailable',
        active_jobs: 0,
        total_jobs: 0,
        redis_connected: false,
        message,
      }),
      errorMessage: 'Failed to check batch service health',
    }),
  }
}

/**
 * Composable with reactive state management for batch processing
 */
export function useBatchProcessingState() {
  const batchApi = useBatchProcessingApi()

  // Reactive state for jobs
  const jobs = ref<BatchJob[]>([])
  const totalCount = ref(0)
  const pendingCount = ref(0)
  const runningCount = ref(0)
  const completedCount = ref(0)
  const failedCount = ref(0)
  const { isLoading: loading, wrap } = useLoadingState()
  const errors = ref<string[]>([])
  const error = computed<string | null>(() =>
    errors.value.length > 0 ? errors.value.join('; ') : null,
  )
  const selectedJob = ref<BatchJob | null>(null)
  const jobLogs = ref<BatchJobLogsResponse | null>(null)
  const healthStatus = ref<BatchHealthResponse | null>(null)

  // Filter state
  const filter = ref<BatchJobsFilter>({
    status: undefined,
    job_type: undefined,
    limit: 50
  })

  // Templates state
  const templates = ref<BatchTemplate[]>([])
  const { isLoading: templatesLoading, wrap: wrapTemplates } = useLoadingState()

  // Schedules state
  const schedules = ref<BatchSchedule[]>([])
  const { isLoading: schedulesLoading, wrap: wrapSchedules } = useLoadingState()

  // Polling state
  const isPolling = ref(false)
  const pollingIntervalMs = ref(5000)

  // Computed properties
  const activeJobs = computed(() =>
    jobs.value.filter((job) => job.status === 'running' || job.status === 'pending')
  )

  const completedJobs = computed(() =>
    jobs.value.filter((job) => job.status === 'completed')
  )

  const failedJobs = computed(() =>
    jobs.value.filter((job) => job.status === 'failed')
  )

  const hasActiveJobs = computed(() => activeJobs.value.length > 0)

  const isServiceHealthy = computed(
    () => healthStatus.value?.status === 'healthy'
  )

  /**
   * Load batch jobs list
   */
  async function loadJobs() {
    errors.value = []
    await wrap(async () => {
      try {
        const result = await batchApi.listJobs(filter.value)
        if (result) {
          jobs.value = result.jobs
          totalCount.value = result.total_count
          pendingCount.value = result.pending_count
          runningCount.value = result.running_count
          completedCount.value = result.completed_count
          failedCount.value = result.failed_count
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Unknown error'
        errors.value = [...errors.value, msg]
        logger.error('Failed to load batch jobs:', e)
      }
    })
  }

  /**
   * Refresh single job
   */
  async function refreshJob(jobId: string) {
    const result = await batchApi.getJob(jobId)
    if (result) {
      updateJobInList(result)
      if (selectedJob.value?.job_id === jobId) {
        selectedJob.value = result
      }
    }
    return result
  }

  /**
   * Update job in the jobs list
   */
  function updateJobInList(updatedJob: BatchJob) {
    const index = jobs.value.findIndex((job) => job.job_id === updatedJob.job_id)
    if (index !== -1) {
      jobs.value[index] = updatedJob
    }
  }

  /**
   * Create a new batch job
   */
  async function createJob(request: CreateBatchJobRequest) {
    const result = await batchApi.createJob(request)
    if (result) {
      await loadJobs()
    }
    return result
  }

  /**
   * Cancel a batch job
   */
  async function cancelJob(jobId: string) {
    const result = await batchApi.cancelJob(jobId)
    if (result) {
      await refreshJob(jobId)
    }
    return result
  }

  /**
   * Delete a batch job
   */
  async function deleteJob(jobId: string) {
    const result = await batchApi.deleteJob(jobId)
    if (result) {
      if (selectedJob.value?.job_id === jobId) {
        selectedJob.value = null
      }
      await loadJobs()
    }
    return result
  }

  /**
   * Load job logs
   */
  async function loadJobLogs(jobId: string) {
    jobLogs.value = await batchApi.getJobLogs(jobId)
    return jobLogs.value
  }

  /**
   * Check service health
   */
  async function checkHealth() {
    healthStatus.value = await batchApi.getHealth()
    return healthStatus.value
  }

  /**
   * Set filter and reload
   */
  async function setFilter(newFilter: Partial<BatchJobsFilter>) {
    filter.value = { ...filter.value, ...newFilter }
    await loadJobs()
  }

  /**
   * Clear filter and reload
   */
  async function clearFilter() {
    filter.value = {
      status: undefined,
      job_type: undefined,
      limit: 50
    }
    await loadJobs()
  }

  /**
   * Select a job for detail view
   */
  function selectJob(job: BatchJob | null) {
    selectedJob.value = job
    if (job) {
      loadJobLogs(job.job_id)
    } else {
      jobLogs.value = null
    }
  }

  /**
   * Load templates
   */
  async function loadTemplates() {
    await wrapTemplates(async () => {
      const result = await batchApi.listTemplates()
      if (result) {
        templates.value = result.templates
      }
    })
  }

  /**
   * Create a new template
   */
  async function createTemplate(request: CreateBatchTemplateRequest) {
    const result = await batchApi.createTemplate(request)
    if (result) {
      await loadTemplates()
    }
    return result
  }

  /**
   * Delete a template
   */
  async function deleteTemplate(templateId: string) {
    const result = await batchApi.deleteTemplate(templateId)
    if (result) {
      await loadTemplates()
    }
    return result
  }

  /**
   * Load schedules
   */
  async function loadSchedules() {
    await wrapSchedules(async () => {
      const result = await batchApi.listSchedules()
      if (result) {
        schedules.value = result.schedules
      }
    })
  }

  /**
   * Create a new schedule
   */
  async function createSchedule(request: CreateBatchScheduleRequest) {
    const result = await batchApi.createSchedule(request)
    if (result) {
      await loadSchedules()
    }
    return result
  }

  /**
   * Toggle schedule enabled state
   */
  async function toggleSchedule(scheduleId: string, enabled: boolean) {
    const result = await batchApi.toggleSchedule(scheduleId, enabled)
    if (result) {
      await loadSchedules()
    }
    return result
  }

  /**
   * Delete a schedule
   */
  async function deleteSchedule(scheduleId: string) {
    const result = await batchApi.deleteSchedule(scheduleId)
    if (result) {
      await loadSchedules()
    }
    return result
  }

  let _stopBatchPoller: (() => void) | null = null

  /**
   * Start polling for updates
   */
  function startPolling(intervalMs = 5000) {
    if (_stopBatchPoller) _stopBatchPoller()

    pollingIntervalMs.value = intervalMs
    isPolling.value = true
    logger.debug(`Started polling every ${intervalMs}ms`)

    const poller = usePollingJob<void>(
      async () => {
        if (hasActiveJobs.value) {
          logger.debug('Polling for batch job updates...')
          await loadJobs()
          if (selectedJob.value && !isTerminalStatus(selectedJob.value.status)) {
            await refreshJob(selectedJob.value.job_id)
          }
        }
      },
      { intervalMs }
    )
    _stopBatchPoller = poller.stop
    poller.start('')
  }

  /**
   * Stop polling
   */
  function stopPolling() {
    if (_stopBatchPoller) _stopBatchPoller()
    _stopBatchPoller = null
    isPolling.value = false
    logger.debug('Stopped polling')
  }

  /**
   * Get jobs grouped by status
   */
  function getJobsByStatus(status: BatchJobStatus): BatchJob[] {
    return jobs.value.filter((job) => job.status === status)
  }

  // usePollingJob handles cleanup via its own onScopeDispose hook.

  return {
    // State
    jobs,
    totalCount,
    pendingCount,
    runningCount,
    completedCount,
    failedCount,
    loading,
    error,
    selectedJob,
    jobLogs,
    healthStatus,
    filter,
    templates,
    templatesLoading,
    schedules,
    schedulesLoading,
    isPolling,
    pollingIntervalMs,

    // Computed
    activeJobs,
    completedJobs,
    failedJobs,
    hasActiveJobs,
    isServiceHealthy,

    // Job methods
    loadJobs,
    refreshJob,
    createJob,
    cancelJob,
    deleteJob,
    loadJobLogs,
    checkHealth,
    setFilter,
    clearFilter,
    selectJob,
    getJobsByStatus,

    // Template methods
    loadTemplates,
    createTemplate,
    deleteTemplate,

    // Schedule methods
    loadSchedules,
    createSchedule,
    toggleSchedule,
    deleteSchedule,

    // Polling methods
    startPolling,
    stopPolling
  }
}
