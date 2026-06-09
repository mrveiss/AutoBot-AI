// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Vue Composable for Batch Processing API
 * Issue #584 - Batch Processing Manager
 */

import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
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
import { useProbeBackedHealth, probeStatusToLegacy } from '@/composables/useProbeBackedHealth'
import { PROBE_NAMES } from '@/types/probe-names'

const logger = createLogger('useBatchProcessing')

export function useBatchProcessingApi() {
  const api = useApiClient()

  return {
    async listJobs(filter?: BatchJobsFilter): Promise<BatchJobsListResponse | null> {
      try {
        const params = new URLSearchParams()
        if (filter?.status) params.append('status', filter.status)
        if (filter?.job_type) params.append('job_type', filter.job_type)
        if (filter?.limit) params.append('limit', filter.limit.toString())
        const queryString = params.toString()
        const url = `${getApiBase()}/batch-jobs${queryString ? `?${queryString}` : ''}`
        return await api.get<any>(url)
      } catch (error: unknown) {
        logger.error('Failed to load batch jobs', error)
        showSubtleErrorNotification('Error', 'Failed to load batch jobs', 'error')
        return { jobs: [], total_count: 0, pending_count: 0, running_count: 0, completed_count: 0, failed_count: 0 }
      }
    },

    async getJob(jobId: string): Promise<BatchJob | null> {
      try {
        return await api.get<any>(`${getApiBase()}/batch-jobs/${jobId}`)
      } catch (error: unknown) {
        logger.error('Failed to get batch job', error)
        showSubtleErrorNotification('Error', 'Failed to get batch job', 'error')
        return null
      }
    },

    async createJob(request: CreateBatchJobRequest): Promise<CreateBatchJobResponse | null> {
      try {
        return await api.post<any>(`${getApiBase()}/batch-jobs`, request)
      } catch (error: unknown) {
        logger.error('Failed to create batch job', error)
        showSubtleErrorNotification('Error', 'Failed to create batch job', 'error')
        return null
      }
    },

    async deleteJob(jobId: string): Promise<{ status: string } | null> {
      try {
        return await api.delete<any>(`${getApiBase()}/batch-jobs/${jobId}`)
      } catch (error: unknown) {
        logger.error('Failed to delete batch job', error)
        showSubtleErrorNotification('Error', 'Failed to delete batch job', 'error')
        return null
      }
    },

    async cancelJob(jobId: string): Promise<{ status: string } | null> {
      try {
        return await api.post<any>(`${getApiBase()}/batch-jobs/${jobId}/cancel`)
      } catch (error: unknown) {
        logger.error('Failed to cancel batch job', error)
        showSubtleErrorNotification('Error', 'Failed to cancel batch job', 'error')
        return null
      }
    },

    async getJobLogs(jobId: string): Promise<BatchJobLogsResponse | null> {
      try {
        return await api.get<any>(`${getApiBase()}/batch-jobs/${jobId}/logs`)
      } catch (error: unknown) {
        logger.error('Failed to get batch job logs', error)
        showSubtleErrorNotification('Error', 'Failed to get batch job logs', 'error')
        return { job_id: jobId, logs: [] }
      }
    },

    async listTemplates(): Promise<BatchTemplatesListResponse | null> {
      try {
        return await api.get<any>(`${getApiBase()}/batch-templates`)
      } catch (error: unknown) {
        logger.error('Failed to load batch templates', error)
        showSubtleErrorNotification('Error', 'Failed to load batch templates', 'error')
        return { templates: [], total_count: 0 }
      }
    },

    async createTemplate(request: CreateBatchTemplateRequest): Promise<BatchTemplate | null> {
      try {
        return await api.post<any>(`${getApiBase()}/batch-templates`, request)
      } catch (error: unknown) {
        logger.error('Failed to create batch template', error)
        showSubtleErrorNotification('Error', 'Failed to create batch template', 'error')
        return null
      }
    },

    async deleteTemplate(templateId: string): Promise<{ status: string } | null> {
      try {
        return await api.delete<any>(`${getApiBase()}/batch-templates/${templateId}`)
      } catch (error: unknown) {
        logger.error('Failed to delete batch template', error)
        showSubtleErrorNotification('Error', 'Failed to delete batch template', 'error')
        return null
      }
    },

    async listSchedules(): Promise<BatchSchedulesListResponse | null> {
      try {
        return await api.get<any>(`${getApiBase()}/batch-schedules`)
      } catch (error: unknown) {
        logger.error('Failed to load batch schedules', error)
        showSubtleErrorNotification('Error', 'Failed to load batch schedules', 'error')
        return { schedules: [], total_count: 0 }
      }
    },

    async createSchedule(request: CreateBatchScheduleRequest): Promise<BatchSchedule | null> {
      try {
        return await api.post<any>(`${getApiBase()}/batch-schedules`, request)
      } catch (error: unknown) {
        logger.error('Failed to create batch schedule', error)
        showSubtleErrorNotification('Error', 'Failed to create batch schedule', 'error')
        return null
      }
    },

    async toggleSchedule(scheduleId: string, enabled: boolean): Promise<BatchSchedule | null> {
      try {
        return await api.patch(`${getApiBase()}/batch-schedules/${scheduleId}`, { enabled })
      } catch (error: unknown) {
        logger.error('Failed to update batch schedule', error)
        showSubtleErrorNotification('Error', 'Failed to update batch schedule', 'error')
        return null
      }
    },

    async deleteSchedule(scheduleId: string): Promise<{ status: string } | null> {
      try {
        return await api.delete<any>(`${getApiBase()}/batch-schedules/${scheduleId}`)
      } catch (error: unknown) {
        logger.error('Failed to delete batch schedule', error)
        showSubtleErrorNotification('Error', 'Failed to delete batch schedule', 'error')
        return null
      }
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
      probeName: PROBE_NAMES.BATCH_JOBS,
      buildHealthy: (probe, data) => ({
        status: probeStatusToLegacy(probe.status),
        active_jobs: 0,
        total_jobs: 0,
        redis_connected: Boolean(data.redis_connected),
        message: probe.detail,
      }),
      buildUnavailable: (message) => ({
        status: 'unavailable' as const,
        active_jobs: 0,
        total_jobs: 0,
        redis_connected: false,
        message,
      }),
      errorMessage: 'Failed to check batch service health',
    }),
  }
}

export function useBatchProcessingState() {
  const batchApi = useBatchProcessingApi()

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

  const filter = ref<BatchJobsFilter>({ status: undefined, job_type: undefined, limit: 50 })

  const templates = ref<BatchTemplate[]>([])
  const { isLoading: templatesLoading, wrap: wrapTemplates } = useLoadingState()

  const schedules = ref<BatchSchedule[]>([])
  const { isLoading: schedulesLoading, wrap: wrapSchedules } = useLoadingState()

  const isPolling = ref(false)
  const pollingIntervalMs = ref(5000)

  const activeJobs = computed(() =>
    jobs.value.filter((job) => job.status === 'running' || job.status === 'pending')
  )
  const completedJobs = computed(() => jobs.value.filter((job) => job.status === 'completed'))
  const failedJobs = computed(() => jobs.value.filter((job) => job.status === 'failed'))
  const hasActiveJobs = computed(() => activeJobs.value.length > 0)
  const isServiceHealthy = computed(() => healthStatus.value?.status === 'healthy')

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

  function updateJobInList(updatedJob: BatchJob) {
    const index = jobs.value.findIndex((job) => job.job_id === updatedJob.job_id)
    if (index !== -1) {
      jobs.value[index] = updatedJob
    }
  }

  async function createJob(request: CreateBatchJobRequest) {
    const result = await batchApi.createJob(request)
    if (result) await loadJobs()
    return result
  }

  async function cancelJob(jobId: string) {
    const result = await batchApi.cancelJob(jobId)
    if (result) await refreshJob(jobId)
    return result
  }

  async function deleteJob(jobId: string) {
    const result = await batchApi.deleteJob(jobId)
    if (result) {
      if (selectedJob.value?.job_id === jobId) selectedJob.value = null
      await loadJobs()
    }
    return result
  }

  async function loadJobLogs(jobId: string) {
    jobLogs.value = await batchApi.getJobLogs(jobId)
    return jobLogs.value
  }

  async function checkHealth() {
    healthStatus.value = await batchApi.getHealth()
    return healthStatus.value
  }

  async function setFilter(newFilter: Partial<BatchJobsFilter>) {
    filter.value = { ...filter.value, ...newFilter }
    await loadJobs()
  }

  async function clearFilter() {
    filter.value = { status: undefined, job_type: undefined, limit: 50 }
    await loadJobs()
  }

  function selectJob(job: BatchJob | null) {
    selectedJob.value = job
    if (job) {
      loadJobLogs(job.job_id)
    } else {
      jobLogs.value = null
    }
  }

  async function loadTemplates() {
    await wrapTemplates(async () => {
      const result = await batchApi.listTemplates()
      if (result) templates.value = result.templates
    })
  }

  async function createTemplate(request: CreateBatchTemplateRequest) {
    const result = await batchApi.createTemplate(request)
    if (result) await loadTemplates()
    return result
  }

  async function deleteTemplate(templateId: string) {
    const result = await batchApi.deleteTemplate(templateId)
    if (result) await loadTemplates()
    return result
  }

  async function loadSchedules() {
    await wrapSchedules(async () => {
      const result = await batchApi.listSchedules()
      if (result) schedules.value = result.schedules
    })
  }

  async function createSchedule(request: CreateBatchScheduleRequest) {
    const result = await batchApi.createSchedule(request)
    if (result) await loadSchedules()
    return result
  }

  async function toggleSchedule(scheduleId: string, enabled: boolean) {
    const result = await batchApi.toggleSchedule(scheduleId, enabled)
    if (result) await loadSchedules()
    return result
  }

  async function deleteSchedule(scheduleId: string) {
    const result = await batchApi.deleteSchedule(scheduleId)
    if (result) await loadSchedules()
    return result
  }

  let _stopBatchPoller: (() => void) | null = null

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

  function stopPolling() {
    if (_stopBatchPoller) _stopBatchPoller()
    _stopBatchPoller = null
    isPolling.value = false
    logger.debug('Stopped polling')
  }

  function getJobsByStatus(status: BatchJobStatus): BatchJob[] {
    return jobs.value.filter((job) => job.status === status)
  }

  // usePollingJob handles cleanup via its own onScopeDispose hook.

  return {
    jobs, totalCount, pendingCount, runningCount, completedCount, failedCount,
    loading, error, selectedJob, jobLogs, healthStatus, filter,
    templates, templatesLoading, schedules, schedulesLoading, isPolling, pollingIntervalMs,
    activeJobs, completedJobs, failedJobs, hasActiveJobs, isServiceHealthy,
    loadJobs, refreshJob, createJob, cancelJob, deleteJob, loadJobLogs, checkHealth,
    setFilter, clearFilter, selectJob, getJobsByStatus,
    loadTemplates, createTemplate, deleteTemplate,
    loadSchedules, createSchedule, toggleSchedule, deleteSchedule,
    startPolling, stopPolling
  }
}
