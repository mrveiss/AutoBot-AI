// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Vue Composable for Batch Processing API
 * Issue #584 - Batch Processing Manager
 *
 * #21649: every call goes through the typed `apiClient.call` against the generated
 * contract, resolves to exactly what the backend sends, and THROWS on failure (an
 * `HttpError`). Nothing is replaced by an empty fallback, so a failed load can never
 * read as "no jobs". The state layer records each area's failure as its own error
 * (the raw error, so the screen words it with `httpErrorText` and its own i18n key)
 * and keeps loading, error and empty apart in `jobsView`.
 */

import { ref, computed, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'
import type {
  BatchJob,
  BatchTemplate,
  BatchSchedule,
  BatchLogEntry,
  BatchJobsListResponse,
  BatchHealthResponse,
  BatchJobsFilter,
  CreateBatchJobRequest,
  CreateBatchTemplateRequest,
  CreateBatchScheduleRequest,
  BatchJobStatus,
} from '@/types/batch-processing'
import { isTerminalStatus } from '@/types/batch-processing'
import { getApiBase } from '@/config/ssot-config'
import { useProbeBackedHealth, probeStatusToLegacy } from '@/composables/useProbeBackedHealth'
import { PROBE_NAMES } from '@/types/probe-names'

const logger = createLogger('useBatchProcessing')

/** What the jobs list is showing: kept apart so an outage never reads as an empty list. */
export type BatchJobsView = 'loading' | 'error' | 'empty' | 'ready'

const getHealth = useProbeBackedHealth<BatchHealthResponse>({
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
})

function listJobs(filter?: BatchJobsFilter): Promise<BatchJobsListResponse> {
  const query = { status: filter?.status, job_type: filter?.job_type, limit: filter?.limit }
  return apiClient.call('get', '/api/batch-jobs', { query })
}

async function cancelJob(jobId: string): Promise<{ status: string }> {
  // POST /{id}/cancel is not served -- the backend's only cancel is DELETE, which also
  // deletes the job. Per the #18751 ruling the request stays exactly as it was, pending a
  // per-row decision (#18730 / #18751); since #21649 a failure rejects instead of returning null.
  const api = useApiClient()
  return await api.post<{ status: string }>(`${getApiBase()}/batch-jobs/${jobId}/cancel`)
}

/** Job calls: the list, one job, its logs, and the job actions. */
const jobCalls = {
  listJobs,
  getJob: (jobId: string): Promise<BatchJob> =>
    apiClient.call('get', '/api/batch-jobs/{job_id}', { path: { job_id: jobId } }),
  createJob: (request: CreateBatchJobRequest): Promise<BatchJob> =>
    apiClient.call('post', '/api/batch-jobs', { body: request }),
  deleteJob: (jobId: string) => apiClient.call('delete', '/api/batch-jobs/{job_id}', { path: { job_id: jobId } }),
  runJob: (jobId: string): Promise<BatchJob> =>
    apiClient.call('post', '/api/batch-jobs/{job_id}/run', { path: { job_id: jobId } }),
  cancelJob,
  getJobLogs: (jobId: string): Promise<BatchLogEntry[]> =>
    apiClient.call('get', '/api/batch-jobs/{job_id}/logs', { path: { job_id: jobId } }),
}

/** Template calls: name and type travel as query on create, the parameters as the body. */
const templateCalls = {
  listTemplates: (): Promise<BatchTemplate[]> => apiClient.call('get', '/api/batch-jobs/templates/'),
  createTemplate: ({ name, job_type, parameters }: CreateBatchTemplateRequest): Promise<BatchTemplate> =>
    apiClient.call('post', '/api/batch-jobs/templates/', { query: { name, job_type }, body: parameters ?? {} }),
  deleteTemplate: (templateId: string) =>
    apiClient.call('delete', '/api/batch-jobs/templates/{template_id}', { path: { template_id: templateId } }),
}

/** Schedule calls: every create field travels as query. */
const scheduleCalls = {
  listSchedules: (): Promise<BatchSchedule[]> => apiClient.call('get', '/api/batch-jobs/schedules/'),
  createSchedule: (request: CreateBatchScheduleRequest): Promise<BatchSchedule> =>
    apiClient.call('post', '/api/batch-jobs/schedules/', { query: request }),
  // #12326 / #12380: PATCH /api/batch-jobs/schedules/{id} toggles a schedule.
  toggleSchedule: (scheduleId: string, enabled: boolean): Promise<BatchSchedule> =>
    apiClient.call('patch', '/api/batch-jobs/schedules/{schedule_id}', {
      path: { schedule_id: scheduleId },
      body: { enabled },
    }),
  deleteSchedule: (scheduleId: string) =>
    apiClient.call('delete', '/api/batch-jobs/schedules/{schedule_id}', { path: { schedule_id: scheduleId } }),
}

/** The raw batch-jobs calls. Each resolves to the backend's reply and throws on a non-2xx. */
export function useBatchProcessingApi() {
  return { ...jobCalls, ...templateCalls, ...scheduleCalls, getHealth }
}

type BatchApi = ReturnType<typeof useBatchProcessingApi>

/** What the list shows, and the per-status counts read from `status_counts`. */
function useJobsView(
  jobs: Ref<BatchJob[]>,
  statusCounts: Ref<Record<string, number>>,
  loaded: Ref<boolean>,
  error: Ref<unknown>,
) {
  const countOf = (status: BatchJobStatus) => computed(() => statusCounts.value[status] ?? 0)
  return {
    jobsView: computed<BatchJobsView>(() => {
      if (error.value) return 'error'
      if (!loaded.value) return 'loading'
      return jobs.value.length ? 'ready' : 'empty'
    }),
    pendingCount: countOf('pending'),
    runningCount: countOf('running'),
    completedCount: countOf('completed'),
    failedCount: countOf('failed'),
  }
}

/** The jobs list: rows, per-status counts, and its own loading and error. */
function useJobsList(batchApi: BatchApi) {
  const jobs = ref<BatchJob[]>([])
  const totalCount = ref(0)
  const statusCounts = ref<Record<string, number>>({})
  const loaded = ref(false)
  const error = ref<unknown>(null)
  const { isLoading: loading, wrap } = useLoadingState()
  const filter = ref<BatchJobsFilter>({ status: undefined, job_type: undefined, limit: 50 })

  async function loadJobs(): Promise<void> {
    await wrap(async () => {
      try {
        const result = await batchApi.listJobs(filter.value)
        jobs.value = result.jobs
        totalCount.value = result.total_count
        statusCounts.value = result.status_counts
        error.value = null
        loaded.value = true
      } catch (e) {
        error.value = e
        logger.error('Failed to load batch jobs:', e)
      }
    })
  }

  return {
    jobs, totalCount, statusCounts, loaded, error, loading, filter, loadJobs,
    ...useJobsView(jobs, statusCounts, loaded, error),
  }
}

/** A list that loads all at once, with its own loading and error. */
function useLoadedList<T>(load: () => Promise<T[]>, what: string) {
  const items = ref<T[]>([]) as { value: T[] }
  const error = ref<unknown>(null)
  const { isLoading: loading, wrap } = useLoadingState()

  async function reload(): Promise<void> {
    await wrap(async () => {
      try {
        items.value = await load()
        error.value = null
      } catch (e) {
        error.value = e
        logger.error(`Failed to load batch ${what}:`, e)
      }
    })
  }

  return { items, error, loading, reload }
}

/** Polling that refreshes the list (and the selected job) only while a job is still active. */
function useJobsPolling(tick: () => Promise<void>) {
  const isPolling = ref(false)
  const pollingIntervalMs = ref(5000)
  let stopPoller: (() => void) | null = null

  function startPolling(intervalMs = 5000) {
    if (stopPoller) stopPoller()
    pollingIntervalMs.value = intervalMs
    isPolling.value = true
    logger.debug(`Started polling every ${intervalMs}ms`)
    const poller = usePollingJob<void>(tick, { intervalMs })
    stopPoller = poller.stop
    poller.start('')
  }

  function stopPolling() {
    if (stopPoller) stopPoller()
    stopPoller = null
    isPolling.value = false
    logger.debug('Stopped polling')
  }

  return { isPolling, pollingIntervalMs, startPolling, stopPolling }
}

/** The selected job and its logs; a logs failure is its own error, not the list's. */
function useJobDetail(batchApi: BatchApi) {
  const selectedJob = ref<BatchJob | null>(null)
  const jobLogs = ref<BatchLogEntry[] | null>(null)
  const logsError = ref<unknown>(null)

  async function loadJobLogs(jobId: string): Promise<BatchLogEntry[] | null> {
    try {
      jobLogs.value = await batchApi.getJobLogs(jobId)
      logsError.value = null
    } catch (e) {
      jobLogs.value = null
      logsError.value = e
      logger.error('Failed to load batch job logs:', e)
    }
    return jobLogs.value
  }

  function selectJob(job: BatchJob | null) {
    selectedJob.value = job
    jobLogs.value = null
    logsError.value = null
    if (job) void loadJobLogs(job.job_id)
  }

  return { selectedJob, jobLogs, logsError, loadJobLogs, selectJob }
}

type JobsList = ReturnType<typeof useJobsList>
type JobDetail = ReturnType<typeof useJobDetail>

/** The list split by status, and the service health those groups sit beside. */
function useJobGroups(list: JobsList, batchApi: BatchApi) {
  const healthStatus = ref<BatchHealthResponse | null>(null)
  const activeJobs = computed(() => list.jobs.value.filter((j) => j.status === 'running' || j.status === 'pending'))

  return {
    healthStatus,
    activeJobs,
    completedJobs: computed(() => list.jobs.value.filter((j) => j.status === 'completed')),
    failedJobs: computed(() => list.jobs.value.filter((j) => j.status === 'failed')),
    hasActiveJobs: computed(() => activeJobs.value.length > 0),
    isServiceHealthy: computed(() => healthStatus.value?.status === 'healthy'),
    getJobsByStatus: (status: BatchJobStatus): BatchJob[] => list.jobs.value.filter((j) => j.status === status),
    async checkHealth() {
      healthStatus.value = await batchApi.getHealth()
      return healthStatus.value
    },
  }
}

/** Filter changes; each reloads the list with the new filter. */
function useFilterActions(list: JobsList) {
  return {
    async setFilter(newFilter: Partial<BatchJobsFilter>) {
      list.filter.value = { ...list.filter.value, ...newFilter }
      await list.loadJobs()
    },
    async clearFilter() {
      list.filter.value = { status: undefined, job_type: undefined, limit: 50 }
      await list.loadJobs()
    },
  }
}

/** Re-read one job into the list and, if it is the selected one, into the detail. */
function useRefreshJob(batchApi: BatchApi, list: JobsList, detail: JobDetail) {
  return async function refreshJob(jobId: string): Promise<BatchJob> {
    const job = await batchApi.getJob(jobId)
    const index = list.jobs.value.findIndex((j) => j.job_id === job.job_id)
    if (index !== -1) list.jobs.value[index] = job
    if (detail.selectedJob.value?.job_id === jobId) detail.selectedJob.value = job
    return job
  }
}

/** Templates and schedules, each under the names the screen state has always exposed. */
function useTemplatesAndSchedules(batchApi: BatchApi) {
  const templates = useLoadedList(batchApi.listTemplates, 'templates')
  const schedules = useLoadedList(batchApi.listSchedules, 'schedules')
  return {
    templates: templates.items, templatesLoading: templates.loading, templatesError: templates.error,
    loadTemplates: templates.reload,
    schedules: schedules.items, schedulesLoading: schedules.loading, schedulesError: schedules.error,
    loadSchedules: schedules.reload,
  }
}

/** What a run visibly changes on a job: a re-run that fails again still moves `started_at`. */
const runFingerprint = (job: BatchJob | undefined) =>
  job ? `${job.status}|${job.started_at ?? ''}|${job.completed_at ?? ''}|${job.progress}` : ''

/**
 * Jobs a run or retry has queued whose record has not moved yet (#20644 review). `POST /{id}/run`
 * returns before the worker picks the job up, so a retried failed job still reads `failed` and the
 * active-jobs poll would stop; while any queued job is unchanged, the same poll keeps going.
 */
function useAwaitedRuns(jobs: Ref<BatchJob[]>) {
  const awaited = ref(new Map<string, string>())
  const find = (jobId: string) => jobs.value.find((j) => j.job_id === jobId)

  function settle(): void {
    for (const [jobId, before] of awaited.value) {
      const job = find(jobId)
      if (!job || runFingerprint(job) !== before) awaited.value.delete(jobId)
    }
  }

  return {
    waiting: computed(() => awaited.value.size > 0),
    expect: (jobId: string) => awaited.value.set(jobId, runFingerprint(find(jobId))),
    forget: (jobId: string) => awaited.value.delete(jobId),
    settle,
  }
}

/** Run a job and keep polling for it until its record moves; a failed request stops the wait. */
function awaitingRunOf(runs: ReturnType<typeof useAwaitedRuns>, run: (jobId: string) => Promise<BatchJob>) {
  return async (jobId: string): Promise<BatchJob> => {
    runs.expect(jobId)
    try {
      return await run(jobId)
    } catch (err) {
      runs.forget(jobId)
      throw err
    }
  }
}

/**
 * Batch processing screen state. Loads record their failure in the matching error ref;
 * mutations (create, cancel, delete, run, toggle) reject, so the caller reports them.
 */
export function useBatchProcessingState() {
  const batchApi = useBatchProcessingApi()
  const list = useJobsList(batchApi)
  const detail = useJobDetail(batchApi)
  const lists = useTemplatesAndSchedules(batchApi)
  const groups = useJobGroups(list, batchApi)
  const refreshJob = useRefreshJob(batchApi, list, detail)
  const mutations = useMutations(batchApi, list.loadJobs, detail.selectedJob, lists.loadTemplates, lists.loadSchedules)
  const runs = useAwaitedRuns(list.jobs)
  const polling = useJobsPolling(async () => {
    if (!groups.hasActiveJobs.value && !runs.waiting.value) return
    await list.loadJobs()
    runs.settle()
    const selected = detail.selectedJob.value
    if (selected && !isTerminalStatus(selected.status)) await refreshJob(selected.job_id)
  })

  return {
    ...list, ...detail, ...mutations, ...polling, ...lists, ...groups, ...useFilterActions(list), refreshJob,
    awaitingRun: runs.waiting,
    runJob: awaitingRunOf(runs, mutations.runJob),
  }
}

/** Each mutation awaits the backend (rejecting on failure), then reloads what it changed. */
function useMutations(
  batchApi: BatchApi,
  loadJobs: () => Promise<void>,
  selectedJob: { value: BatchJob | null },
  loadTemplates: () => Promise<void>,
  loadSchedules: () => Promise<void>,
) {
  const thenReload = <A extends unknown[], R>(call: (...a: A) => Promise<R>, reload: () => Promise<void>) =>
    async (...args: A): Promise<R> => {
      const result = await call(...args)
      await reload()
      return result
    }

  return {
    createJob: thenReload(batchApi.createJob, loadJobs),
    cancelJob: thenReload(batchApi.cancelJob, loadJobs),
    runJob: thenReload(batchApi.runJob, loadJobs),
    deleteJob: thenReload(async (jobId: string) => {
      const result = await batchApi.deleteJob(jobId)
      if (selectedJob.value?.job_id === jobId) selectedJob.value = null
      return result
    }, loadJobs),
    createTemplate: thenReload(batchApi.createTemplate, loadTemplates),
    deleteTemplate: thenReload(batchApi.deleteTemplate, loadTemplates),
    createSchedule: thenReload(batchApi.createSchedule, loadSchedules),
    toggleSchedule: thenReload(batchApi.toggleSchedule, loadSchedules),
    deleteSchedule: thenReload(batchApi.deleteSchedule, loadSchedules),
  }
}
