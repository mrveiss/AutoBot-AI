// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Composable: useCodebaseIndexing
 * Manages indexing job lifecycle: start, poll, cancel, progress tracking.
 * Issue #2228/#2230: Extracted from CodebaseAnalytics.vue script section.
 */
import type { Ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type { CodeSource, Problem, JobPhasesData, JobBatchesData, JobStatsData } from '@/types/codebaseAnalytics'

const logger = createLogger('useCodebaseIndexing')

export interface IndexingDeps {
  rootPath: Ref<string>
  selectedSource: Ref<CodeSource | null>
  withSourceId: (url: string) => string
  analyzing: Ref<boolean>
  progressPercent: Ref<number>
  progressStatus: Ref<string>
  currentJobId: Ref<string | null>
  currentJobStatus: Ref<string | null>
  jobPollingInterval: Ref<ReturnType<typeof setInterval> | null>
  jobPhases: Ref<JobPhasesData | null>
  jobBatches: Ref<JobBatchesData | null>
  jobStats: Ref<JobStatsData | null>
  problemsReport: Ref<Problem[]>
  codebaseStats: Ref<Record<string, unknown> | null>
  showKnowledgeBaseOptIn: Ref<boolean>
  notify: (message: string, type: 'info' | 'success' | 'warning' | 'error') => void
  t: (key: string, params?: Record<string, unknown>) => string
  onIndexingComplete: () => Promise<void>
}

export function useCodebaseIndexing(deps: IndexingDeps) {
  function startJobPolling(): void {
    if (deps.jobPollingInterval.value) clearInterval(deps.jobPollingInterval.value)
    deps.jobPollingInterval.value = setInterval(async () => { await pollJobStatus() }, 2000)
  }
  function stopJobPolling(): void {
    if (deps.jobPollingInterval.value) { clearInterval(deps.jobPollingInterval.value); deps.jobPollingInterval.value = null }
  }

  function _updateActiveJobProgress(data: Record<string, unknown>): void {
    deps.analyzing.value = true
    if (data.phases) deps.jobPhases.value = data.phases as JobPhasesData
    if (data.batches) deps.jobBatches.value = data.batches as JobBatchesData
    if (data.stats) deps.jobStats.value = data.stats as JobStatsData
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
      deps.progressStatus.value = statusParts.length > 0 ? `${operation}: ${statusParts.join(' ')}` : operation
    }
  }

  async function _handleJobFinished(status: string, error?: string): Promise<void> {
    deps.analyzing.value = false
    stopJobPolling()
    deps.jobPhases.value = null; deps.jobBatches.value = null; deps.jobStats.value = null
    if (status === 'completed') {
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingCompleted')
      deps.progressPercent.value = 100
      deps.notify(deps.t('analytics.codebase.notify.indexingCompleted'), 'success')
      deps.showKnowledgeBaseOptIn.value = true
      await deps.onIndexingComplete()
    } else if (status === 'cancelled') {
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingCancelled')
      deps.notify(deps.t('analytics.codebase.notify.indexingCancelled'), 'warning')
    } else if (status === 'failed' || error) {
      const errMsg = error || deps.t('analytics.codebase.errors.unknown')
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingFailed', { error: errMsg })
      deps.notify(deps.t('analytics.codebase.notify.indexingFailed', { error: errMsg }), 'error')
    }
    deps.currentJobId.value = null
  }

  async function pollIntermediateResults(): Promise<void> {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const problemsResponse = await fetchWithAuth(deps.withSourceId(`${backendUrl}/api/analytics/codebase/problems`))
      if (problemsResponse.ok) { const d = await problemsResponse.json(); deps.problemsReport.value = d.problems || [] }
      const statsResponse = await fetchWithAuth(deps.withSourceId(`${backendUrl}/api/analytics/codebase/stats`))
      if (statsResponse.ok) { const d = await statsResponse.json(); if (d.stats) deps.codebaseStats.value = d.stats }
    } catch (_error: unknown) { /* Silent */ }
  }

  async function pollJobStatus(): Promise<void> {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/current`)
      if (!response.ok) return
      const data = await response.json()
      deps.currentJobStatus.value = data.status
      if (data.has_active_job) { _updateActiveJobProgress(data); await pollIntermediateResults() }
      else { await _handleJobFinished(data.status, data.error) }
    } catch (error: unknown) { logger.warn('Job polling error:', error instanceof Error ? error.message : String(error)) }
  }

  async function checkCurrentIndexingJob(): Promise<void> {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/current`)
      if (response.ok) {
        const data = await response.json()
        if (data.has_active_job) {
          deps.currentJobId.value = data.task_id; deps.currentJobStatus.value = data.status
          deps.analyzing.value = true
          deps.progressStatus.value = data.progress?.step || deps.t('analytics.codebase.status.indexingInProgress')
          deps.progressPercent.value = data.progress?.percent || 20
          startJobPolling()
          deps.notify(deps.t('analytics.codebase.notify.indexingAlreadyRunning'), 'info')
        } else if (data.task_id && data.status !== 'idle') {
          deps.progressStatus.value = deps.t('analytics.codebase.status.lastJob', { status: data.status })
        }
      }
    } catch (error: unknown) { logger.warn('Could not check for running job:', error instanceof Error ? error.message : String(error)) }
  }

  async function _sendIndexRequest(endpoint: string, body: string): Promise<Response> {
    const maxRetries = 2
    let response: Response | null = null
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      response = await fetchWithAuth(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      if (response.status !== 502 && response.status !== 503) break
      if (attempt < maxRetries) {
        const delay = (attempt + 1) * 3
        deps.progressStatus.value = deps.t('analytics.codebase.status.backendRetrying', { delay })
        logger.warn(`Index request got ${response.status}, retrying (${attempt + 1}/${maxRetries})`)
        await new Promise((r) => setTimeout(r, delay * 1000))
      }
    }
    if (!response || !response.ok) {
      const errorText = response ? await response.text() : 'No response'
      const status = response?.status ?? 0
      if (status === 502 || status === 503) throw new Error('Backend is temporarily unavailable. Please try again in a moment.')
      throw new Error(`Status ${status}: ${errorText}`)
    }
    return response
  }

  function _handleIndexResponseStatus(data: Record<string, unknown>): boolean {
    if (data.status === 'syncing') { deps.progressStatus.value = deps.t('analytics.codebase.status.syncingRepo'); deps.notify(deps.t('analytics.codebase.notify.syncStarted'), 'info'); startJobPolling(); return true }
    else if (data.status === 'already_running') { deps.currentJobId.value = data.task_id as string; deps.progressStatus.value = deps.t('analytics.codebase.status.monitoringIndexing'); deps.notify(deps.t('analytics.codebase.notify.indexingMonitoring'), 'info') }
    else if (data.status === 'queued') { deps.progressStatus.value = deps.t('analytics.codebase.status.queued', { position: data.position }); deps.notify(deps.t('analytics.codebase.notify.indexingQueued'), 'info'); startJobPolling(); return true }
    else { deps.currentJobId.value = data.task_id as string; deps.progressStatus.value = deps.t('analytics.codebase.status.initializingIndexing'); deps.notify(deps.t('analytics.codebase.notify.indexingStarted'), 'success') }
    return false
  }

  async function indexCodebase(): Promise<void> {
    if (deps.currentJobId.value) { deps.notify(deps.t('analytics.codebase.notify.indexingAlreadyRunning'), 'warning'); return }
    deps.analyzing.value = true; deps.progressPercent.value = 10
    deps.progressStatus.value = deps.t('analytics.codebase.status.startingIndexing')
    localStorage.setItem('codebase-analytics-path', deps.rootPath.value)
    deps.problemsReport.value = []; deps.codebaseStats.value = null
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const requestBody = JSON.stringify(deps.selectedSource.value ? { source_id: deps.selectedSource.value.id } : { root_path: deps.rootPath.value })
      const response = await _sendIndexRequest(`${backendUrl}/api/analytics/codebase/index`, requestBody)
      const data = await response.json()
      if (_handleIndexResponseStatus(data)) return
      deps.progressPercent.value = 5; await pollJobStatus(); startJobPolling()
    } catch (error: unknown) {
      logger.error('Indexing failed:', error)
      const errorMessage = error instanceof Error ? error.message : String(error)
      deps.progressStatus.value = deps.t('analytics.codebase.status.indexingFailedToStart', { error: errorMessage })
      deps.notify(deps.t('analytics.codebase.notify.indexingFailed', { error: errorMessage }), 'error')
      deps.analyzing.value = false
    }
  }

  async function cancelIndexingJob(): Promise<void> {
    if (!deps.currentJobId.value) { deps.notify(deps.t('analytics.codebase.notify.noActiveJob'), 'warning'); return }
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/cancel`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      if (response.ok) {
        const data = await response.json()
        if (data.success) { deps.analyzing.value = false; stopJobPolling(); deps.currentJobId.value = null; deps.progressStatus.value = deps.t('analytics.codebase.status.indexingCancelledByUser'); deps.notify(deps.t('analytics.codebase.notify.indexingJobCancelled'), 'success') }
        else { deps.notify(data.message || deps.t('analytics.codebase.notify.couldNotCancel'), 'warning') }
      } else { deps.notify(deps.t('analytics.codebase.notify.cancelFailed'), 'error') }
    } catch (error: unknown) { deps.notify(deps.t('analytics.codebase.notify.cancelError', { error: error instanceof Error ? error.message : String(error) }), 'error') }
  }

  function handleStop(scanRunnerCancel: () => void, scanRunnerRunning: Ref<boolean>): void {
    if (deps.analyzing.value && deps.currentJobId.value) cancelIndexingJob()
    if (scanRunnerRunning.value) scanRunnerCancel()
  }

  return { checkCurrentIndexingJob, indexCodebase, cancelIndexingJob, handleStop, pollJobStatus, startJobPolling, stopJobPolling }
}
