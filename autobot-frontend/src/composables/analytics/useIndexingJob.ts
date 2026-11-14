// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useIndexingJob
 *
 * Encapsulates all indexing job state and logic for the codebase
 * analytics dashboard: polling, progress tracking, cancellation,
 * and the main indexCodebase() entry point.
 *
 * Issue #1579: Extracted from CodebaseAnalytics.vue
 */

import { ref, watch, type Ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import { jobBelongsToSource } from './indexingJobSource'
import { createPollSession } from './pollSession'
import { endedRunOutcome, type RunStateHandle } from './useRunState'

const logger = createLogger('useIndexingJob')

/**
 * Polls that may answer `idle` while this page is still waiting for a request it queued itself
 * before the wait is given up (the request is not visible to the backend until it is queued).
 */
export const IDLE_POLLS_BEFORE_GIVING_UP = 5

interface JobPhase {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed'
}

export interface JobPhasesData {
  phase_list: JobPhase[]
}

export interface JobBatchesData {
  total_batches: number
  completed_batches: number
}

export interface JobStatsData {
  files_scanned: number
  problems_found: number
  functions_found: number
  classes_found: number
  items_stored: number
}

export interface UseIndexingJobDeps {
  /** The root path for indexing. */
  rootPath: Ref<string>
  /** Whether the system is currently analyzing. Shared with other analysis modes. */
  analyzing: Ref<boolean>
  /** Progress bar percentage (0-100). */
  progressPercent: Ref<number>
  /** Human-readable progress status string. */
  progressStatus: Ref<string>
  /** Currently selected code source (if any). */
  selectedSource: Ref<{ id: string } | null>
  /** Names the selected source (the key `useRunState` receives); a change drops the old source's job. */
  sourceKey: () => string
  /** Helper that appends ?source_id= to a URL. */
  withSourceId: (url: string) => string
  /** Toast notification helper. */
  notify: (message: string, type: 'info' | 'success' | 'warning' | 'error') => void
  /** i18n translation function. */
  t: (key: string, params?: Record<string, unknown>) => string
  /** Refs that get cleared/updated during intermediate polling. */
  problemsReport: Ref<unknown[]>
  codebaseStats: Ref<Record<string, unknown> | null>
  declarationAnalysis: Ref<unknown[]>
  duplicateAnalysis: Ref<unknown[]>
  hardcodeAnalysis: Ref<unknown[]>
  chartData: Ref<unknown | null>
  /** How the newest run ended (#21003): re-read when a job ends and when the page opens. */
  runState: Pick<RunStateHandle, 'loadRunState' | 'run' | 'readFailed'>
  /** Show knowledge-base opt-in banner after successful indexing. */
  showKnowledgeBaseOptIn: Ref<boolean>
  /** Callback invoked after a successful index completion to run follow-up scans. */
  onIndexComplete: () => Promise<void>
  /** localStorage key for persisting the root path. */
  storageKeyPath: string
}

export function useIndexingJob(deps: UseIndexingJobDeps) {
  const currentJobId = ref<string | null>(null)
  const currentJobStatus = ref<string | null>(null)
  const jobPhases = ref<JobPhasesData | null>(null)
  const jobBatches = ref<JobBatchesData | null>(null)
  const jobStats = ref<JobStatsData | null>(null)

  // --- Endpoints (#5257) ---------------------------------------------------
  // Shared by pollJobStatus + checkCurrentIndexingJob (same URL, different
  // response-handling). `/index/current` is scoped to the selected source (#20513):
  // the backend holds one current-task slot for all sources and answers idle when
  // that job belongs to another. `/index/cancel` is NOT source-scoped: it acts on
  // the one running job (the backend left it deferred).

  interface CurrentJobRaw {
    has_active_job?: boolean
    task_id?: string
    source_id?: string | null
    status?: string
    position?: number
    progress?: { step?: string; percent?: number }
    error?: string
  }

  const currentJobEndpoint = useFetchEndpoint<CurrentJobRaw, CurrentJobRaw>(
    {
      path: '/api/analytics/codebase/index/current',
      scopeToSource: true,
      requireSource: true,
      pickData: (r) => r, // caller reads endpoint.data.value directly
      label: 'Current indexing job',
    },
    { withSourceId: deps.withSourceId },
  )

  // The request context is the source key the request was made for: a late answer for a source
  // that is no longer selected is dropped (the shared refs hold the new source's state).
  const problemsPollEndpoint = useFetchEndpoint<
    { problems?: unknown[] },
    unknown[],
    string
  >(
    {
      path: '/api/analytics/codebase/problems',
      scopeToSource: true,
      requireSource: true,
      pickData: (r) => r.problems ?? [],
      onSuccess: (list, _raw, forSource) => {
        if (forSource === deps.sourceKey()) deps.problemsReport.value = list
      },
    },
    { withSourceId: deps.withSourceId },
  )

  const statsPollEndpoint = useFetchEndpoint<
    { stats?: Record<string, unknown> },
    Record<string, unknown>,
    string
  >(
    {
      path: '/api/analytics/codebase/stats',
      scopeToSource: true,
      requireSource: true,
      pickData: (r) => r.stats ?? null,
      onSuccess: (stats, _raw, forSource) => {
        if (forSource === deps.sourceKey()) deps.codebaseStats.value = stats
      },
    },
    { withSourceId: deps.withSourceId },
  )

  const cancelEndpoint = useFetchEndpoint<
    { success?: boolean; message?: string },
    { success: boolean; message?: string }
  >({
    path: '/api/analytics/codebase/index/cancel',
    method: 'POST',
    pickData: (r) => ({ success: r.success ?? false, message: r.message }),
    label: 'Index cancel',
  })

  // --- Polling ---

  const { start: _startJobPoller, stop: stopJobPolling } = usePollingJob<void>(
    async () => { await pollJobStatus() },
    { intervalMs: 2000 }
  )

  // A polling session starts not having seen its own job; `queued` or an active job for this
  // source sets it, and only then is a bare `idle` the end of the job rather than a wait.
  let sawOwnJob = false
  let idlePolls = 0
  // Ended by a source switch and by every restart of polling: a poll or follow-up that was
  // already in flight resumes after its `await` and must not write the old session's answer.
  const pollSession = createPollSession()

  const startJobPolling = () => {
    pollSession.renew()
    sawOwnJob = false
    idlePolls = 0
    _startJobPoller('')
  }

  /** This source's own request is queued behind another source's job (#20513): wait, do not finish. */
  const _showQueued = (data: CurrentJobRaw) => {
    sawOwnJob = true
    idlePolls = 0
    // A job tracked until now has ended and the slot holds another source's job: keeping its id
    // would leave Stop enabled, and the cancel route is not source-scoped.
    if (currentJobId.value) deps.progressPercent.value = 0
    else pollSession.noteWait(deps.runState.run.value?.run_id ?? null) // the run before this request
    currentJobId.value = null
    jobPhases.value = jobBatches.value = jobStats.value = null
    deps.analyzing.value = true
    deps.progressStatus.value = deps.t('analytics.codebase.status.queued', { position: data.position })
  }

  // --- Internal helpers ---

  const _updateActiveJobProgress = (
    data: Record<string, unknown>,
  ) => {
    deps.analyzing.value = true
    if (data.phases) jobPhases.value = data.phases as JobPhasesData
    if (data.batches) jobBatches.value = data.batches as JobBatchesData
    if (data.stats) jobStats.value = data.stats as JobStatsData

    const progress = data.progress as Record<string, unknown> | undefined
    if (progress) {
      deps.progressPercent.value = (progress.percent as number) || 0
      const operation = (progress.operation as string) || 'Processing'
      const currentFile = (progress.current_file as string) || ''
      const current = (progress.current as number) || 0
      const total = (progress.total as number) || 0

      const statusParts: string[] = []
      if (currentFile && currentFile !== 'Initializing...') statusParts.push(currentFile)
      if (total > 0) statusParts.push(`(${current}/${total})`)

      deps.progressStatus.value = statusParts.length > 0
        ? `${operation}: ${statusParts.join(' ')}`
        : operation
    }
  }

  const _handleJobFinished = async (
    status: string,
    error?: string,
  ) => {
    const waitedFrom = pollSession.waitBaseline()
    pollSession.renew() // the job is ended once: a poll still in flight is stale and cannot end it again
    const isStale = pollSession.guard()
    const taskId = currentJobId.value
    const tracked = sawOwnJob || !!taskId
    deps.analyzing.value = false
    stopJobPolling()
    jobPhases.value = null
    jobBatches.value = null
    jobStats.value = null
    // #21003: how the run ended decides whether the stored findings are labelled partial.
    const runStateRead = deps.runState.loadRunState()
    if (status === 'idle' && tracked) {
      // The slot of a job that ended is cleared, so `idle` says only that it is over: how it
      // ended is on the run record. An unread record resolves nothing.
      await runStateRead
      if (isStale()) return
      const ended = endedRunOutcome(deps.runState.readFailed.value ? null : deps.runState.run.value, taskId, waitedFrom)
      status = ended?.status ?? status
      error = ended ? ended.error : error
    }

    if (status === 'completed') {
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingCompleted')
      deps.progressPercent.value = 100
      deps.notify(deps.t('analytics.codebase.notify.indexingCompleted'), 'success')
      deps.showKnowledgeBaseOptIn.value = true
      await deps.onIndexComplete()
    } else if (status === 'cancelled') {
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingCancelled')
      deps.notify(deps.t('analytics.codebase.notify.indexingCancelled'), 'warning')
    } else if (status === 'failed' || error) {
      const errMsg = error || deps.t('analytics.codebase.errors.unknown')
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingFailed', { error: errMsg })
      deps.notify(deps.t('analytics.codebase.notify.indexingFailed', { error: errMsg }), 'error')
    }
    if (isStale()) return // the page moved on while the follow-up ran: its job id is not ours to clear
    currentJobId.value = null
    await runStateRead
  }

  const pollJobStatus = async () => {
    const isStale = pollSession.guard()
    await currentJobEndpoint.load()
    if (isStale()) return
    if (currentJobEndpoint.error.value) {
      logger.warn('Job polling error:', currentJobEndpoint.error.value)
      return
    }
    const data = currentJobEndpoint.data.value
    if (!data) return
    // The backend answers only for the requested source (#20513), so this is a second check.
    if (!jobBelongsToSource(data.source_id, deps.selectedSource.value?.id)) return

    currentJobStatus.value = data.status ?? null
    if (data.status === 'queued') {
      _showQueued(data)
    } else if (data.has_active_job) {
      sawOwnJob = true
      idlePolls = 0
      if (data.task_id) currentJobId.value = data.task_id
      _updateActiveJobProgress(data as Record<string, unknown>)
      await pollIntermediateResults()
    } else if (data.status === 'idle' && !sawOwnJob && !currentJobId.value && ++idlePolls <= IDLE_POLLS_BEFORE_GIVING_UP) {
      logger.debug('Waiting for the queued job to appear')
    } else {
      await _handleJobFinished(data.status ?? '', data.error)
    }
  }

  const pollIntermediateResults = async () => {
    // Silent: both endpoints write to deps refs via onSuccess, and errors
    // are logged internally by the composable.
    const forSource = deps.sourceKey()
    await Promise.all([problemsPollEndpoint.load(undefined, forSource), statsPollEndpoint.load(undefined, forSource)])
  }

  // --- Public API ---

  const checkCurrentIndexingJob = async (readRunState = true) => {
    const isStale = pollSession.guard()
    // #21003: opening the page reads how the newest run ended (a GET; it starts nothing).
    // A source switch passes false: `useRunState` re-reads it itself on that switch.
    await Promise.all([currentJobEndpoint.load(), readRunState ? deps.runState.loadRunState() : undefined])
    if (isStale()) return
    if (currentJobEndpoint.error.value) {
      logger.warn(
        'Could not check for running job:',
        currentJobEndpoint.error.value,
      )
      return
    }
    const data = currentJobEndpoint.data.value
    if (!data) return
    if (!jobBelongsToSource(data.source_id, deps.selectedSource.value?.id)) return

    if (data.status === 'queued') {
      // Queued behind another source's job: no job of ours exists yet, so no task id, no
      // "already running" notice and no progress figure; keep polling until it starts.
      startJobPolling()
      _showQueued(data)
    } else if (data.has_active_job) {
      currentJobId.value = data.task_id ?? null
      currentJobStatus.value = data.status ?? null
      deps.analyzing.value = true
      deps.progressStatus.value =
        data.progress?.step ||
        deps.t('analytics.codebase.status.indexingInProgress')
      deps.progressPercent.value = data.progress?.percent || 20
      startJobPolling()
      deps.notify(
        deps.t('analytics.codebase.notify.indexingAlreadyRunning'),
        'info',
      )
    } else if (data.task_id && data.status !== 'idle') {
      deps.progressStatus.value = deps.t(
        'analytics.codebase.status.lastJob',
        { status: data.status },
      )
    }
  }

  const cancelIndexingJob = async () => {
    if (!currentJobId.value) {
      deps.notify(deps.t('analytics.codebase.notify.noActiveJob'), 'warning')
      return
    }

    const isStale = pollSession.guard()
    await cancelEndpoint.load()
    if (isStale()) return // the page moved to another source: its state is not the cancelled job's
    if (cancelEndpoint.error.value) {
      deps.notify(
        deps.t('analytics.codebase.notify.cancelError', {
          error: cancelEndpoint.error.value,
        }),
        'error',
      )
      return
    }

    const data = cancelEndpoint.data.value
    if (data?.success) {
      deps.analyzing.value = false
      stopJobPolling()
      currentJobId.value = null
      deps.progressStatus.value = deps.t(
        'analytics.codebase.status.indexingCancelledByUser',
      )
      deps.notify(
        deps.t('analytics.codebase.notify.indexingJobCancelled'),
        'success',
      )
    } else {
      deps.notify(
        data?.message || deps.t('analytics.codebase.notify.couldNotCancel'),
        'warning',
      )
    }
  }

  // A job, a queued request and a polling session belong to ONE source: on a switch drop them
  // (so Stop cannot hit the old source's running job) and discover the new source's, as page open does.
  watch(deps.sourceKey, () => {
    pollSession.renew()
    stopJobPolling()
    currentJobId.value = null
    currentJobStatus.value = null
    jobPhases.value = null
    jobBatches.value = null
    jobStats.value = null
    sawOwnJob = false
    idlePolls = 0
    deps.analyzing.value = false
    deps.progressPercent.value = 0
    deps.progressStatus.value = deps.t('analytics.codebase.status.ready')
    void checkCurrentIndexingJob(false)
  })

  /**
   * Send an index request with retry on 502/503.
   *
   * #5257: intentionally NOT migrated to useFetchEndpoint — the composable
   * has no retry hook, and the 502/503 handling is domain-specific
   * (backend-warmup vs real error).
   *
   * #6024: assessed for useBackgroundTask migration — not applicable.
   * useBackgroundTask hard-codes POST {baseUrl}/analyze + GET {baseUrl}/status/{id};
   * this endpoint is POST /index (no /analyze suffix). The indexing API also
   * exposes domain-specific statuses (syncing, already_running, queued),
   * intermediate result polling, cancellation, and resume-on-mount that
   * useBackgroundTask does not support. See discovery #6126 for full analysis.
   */
  const _sendIndexRequest = async (
    endpoint: string,
    body: string,
    isStale: () => boolean,
  ): Promise<Response> => {
    const maxRetries = 2
    let response: Response | null = null
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      response = await fetchWithAuth(endpoint, { // fetchWithAuth retained: raw Response needed for 502/503 retry status inspection — exempt (#6256)
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (response.status !== 502 && response.status !== 503) break
      if (attempt < maxRetries) {
        const delay = (attempt + 1) * 3
        if (!isStale()) {
          deps.progressStatus.value = deps.t(
            'analytics.codebase.status.backendRetrying',
            { delay },
          )
        }
        logger.warn(
          `Index request got ${response.status}, retrying (${attempt + 1}/${maxRetries})`,
        )
        await new Promise((r) => setTimeout(r, delay * 1000))
      }
    }
    if (!response || !response.ok) {
      const errorText = response ? await response.text() : 'No response'
      const status = response?.status ?? 0
      if (status === 502 || status === 503) {
        throw new Error(
          'Backend is temporarily unavailable. Please try again in a moment.',
        )
      }
      throw new Error(`Status ${status}: ${errorText}`)
    }
    return response
  }

  /** Handle the index API response status codes. Returns true if early return. */
  const _handleIndexResponseStatus = (
    data: Record<string, unknown>,
  ): boolean => {
    if (data.status === 'syncing') {
      deps.progressStatus.value = deps.t('analytics.codebase.status.syncingRepo')
      deps.notify(deps.t('analytics.codebase.notify.syncStarted'), 'info')
      startJobPolling()
      return true
    } else if (data.status === 'already_running') {
      currentJobId.value = data.task_id as string
      deps.progressStatus.value = deps.t(
        'analytics.codebase.status.monitoringIndexing',
      )
      deps.notify(
        deps.t('analytics.codebase.notify.indexingMonitoring'),
        'info',
      )
    } else if (data.status === 'queued') {
      deps.progressStatus.value = deps.t(
        'analytics.codebase.status.queued',
        { position: data.position },
      )
      deps.notify(deps.t('analytics.codebase.notify.indexingQueued'), 'info')
      startJobPolling()
      return true
    } else {
      currentJobId.value = data.task_id as string
      deps.progressStatus.value = deps.t(
        'analytics.codebase.status.initializingIndexing',
      )
      deps.notify(
        deps.t('analytics.codebase.notify.indexingStarted'),
        'success',
      )
    }
    return false
  }

  /** Main entry point: start indexing the codebase. */
  const indexCodebase = async () => {
    const isStale = pollSession.guard()
    if (currentJobId.value) {
      deps.notify(
        deps.t('analytics.codebase.notify.indexingAlreadyRunning'),
        'warning',
      )
      return
    }

    deps.analyzing.value = true
    deps.progressPercent.value = 10
    deps.progressStatus.value = deps.t(
      'analytics.codebase.status.startingIndexing',
    )
    localStorage.setItem(deps.storageKeyPath, deps.rootPath.value)

    // Clear previous analysis data
    deps.problemsReport.value = []
    deps.codebaseStats.value = null
    deps.declarationAnalysis.value = []
    deps.duplicateAnalysis.value = []
    deps.hardcodeAnalysis.value = []
    deps.chartData.value = null

    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      if (isStale()) return // switched before the request was built: it would index the new source
      const requestBody = JSON.stringify(
        deps.selectedSource.value
          ? { source_id: deps.selectedSource.value.id }
          : { root_path: deps.rootPath.value },
      )
      const response = await _sendIndexRequest(
        `${backendUrl}/api/analytics/codebase/index`,
        requestBody,
        isStale,
      )
      const data = await response.json()
      if (isStale()) return

      if (_handleIndexResponseStatus(data)) return

      deps.progressPercent.value = 5
      await pollJobStatus()
      if (isStale()) return
      startJobPolling()
    } catch (error: unknown) {
      logger.error('Indexing failed:', error)
      if (isStale()) return
      const errorMessage = error instanceof Error ? error.message : String(error)
      deps.progressStatus.value = deps.t(
        'analytics.codebase.status.indexingFailedToStart',
        { error: errorMessage },
      )
      deps.notify(
        deps.t('analytics.codebase.notify.indexingFailed', {
          error: errorMessage,
        }),
        'error',
      )
      deps.analyzing.value = false
    }
  }

  return {
    // State
    currentJobId,
    currentJobStatus,
    jobPhases,
    jobBatches,
    jobStats,
    // Functions
    checkCurrentIndexingJob,
    startJobPolling,
    stopJobPolling,
    pollJobStatus,
    pollIntermediateResults,
    cancelIndexingJob,
    indexCodebase,
  }
}
