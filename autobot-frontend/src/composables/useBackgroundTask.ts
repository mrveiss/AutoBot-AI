// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Shared composable for background task polling (#1304).
 *
 * Replaces duplicated POST-start + GET-poll patterns across analytics
 * endpoints with a single reusable composable.
 *
 * Usage:
 *   const deps = useBackgroundTask('/api/analytics/codebase/analytics/dependencies')
 *   await deps.start()          // POST /analyze, poll /status/{id}
 *   // deps.result now holds the response
 *
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, onUnmounted, type Ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { getConfig } from '@/config/ssot-config'
import apiClient from '@/utils/ApiClient'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'

const logger = createLogger('useBackgroundTask')

const POLL_INTERVAL_MS = 2000
const MAX_CONSECUTIVE_ERRORS = 5

export interface TaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  current_step: string | null
  started_at: string | null
  completed_at: string | null
  error: string | null
  reason: string | null
  result: Record<string, unknown> | null
}

async function getBackendUrl(): Promise<string> {
  try {
    return await appConfig.getServiceUrl('backend')
  } catch {
    logger.warn('AppConfig failed, using SSOT config backend URL')
    return getConfig().backendUrl
  }
}

/**
 * Clear stuck tasks for a given endpoint.
 * Shared helper used by both 409 recovery and orphan auto-retry.
 */
async function clearStuckTasks(clearUrl: string, signal?: AbortSignal): Promise<void> {
  // Note: apiClient.post does not support AbortSignal; signal parameter kept for API compatibility.
  void signal
  await apiClient.post<unknown>(`${clearUrl}?force=true`)
}

/**
 * POST to the /analyze endpoint and return the response.
 * Shared helper to avoid duplicating the fetch logic.
 *
 * fetchWithAuth retained: callers check response.status === 409 for conflict detection.
 * ApiClient throws on non-2xx making status inspection impossible. Exempt.
 */
async function postAnalyze(
  baseUrl: string,
  qs: string,
  fetchOpts: RequestInit,
): Promise<Response> {
  const backendUrl = await getBackendUrl()
  return fetchWithAuth(`${backendUrl}${baseUrl}/analyze${qs}`, fetchOpts) // fetchWithAuth retained: callers inspect response.status === 409 — exempt (#6256)
}

/**
 * Reusable background-task composable.
 *
 * @param baseUrl  API path prefix (e.g. `/api/analytics/codebase/analytics/dependencies`).
 *                 Must expose `POST {baseUrl}/analyze` and `GET {baseUrl}/status/{id}`.
 * @param clearStuckUrl  Optional URL for clearing stuck tasks (defaults to
 *                       `{baseUrl}/tasks/clear-stuck`). Set to empty string to disable.
 */
export function useBackgroundTask(baseUrl: string, clearStuckUrl?: string) {
  const running: Ref<boolean> = ref(false)
  const progress: Ref<number> = ref(0)
  const currentStep: Ref<string | null> = ref(null)
  const error: Ref<string | null> = ref(null)
  const wasInterrupted: Ref<boolean> = ref(false)
  const result: Ref<Record<string, unknown> | null> = ref(null)
  const taskId: Ref<string | null> = ref(null)
  const taskStatus: Ref<TaskStatus | null> = ref(null)

  const resolvedClearUrl = clearStuckUrl ?? `${baseUrl}/tasks/clear-stuck`

  // AbortControllers for in-flight requests
  let _startController: AbortController | null = null
  let _pollController: AbortController | null = null

  /**
   * POST to start the analysis, then poll until done.
   * Handles 409 conflict and orphaned tasks by auto-clearing and retrying once.
   *
   * @param body   Optional JSON body for the POST request.
   * @param query  Optional query params appended to the URL.
   * @returns true if task completed successfully, false otherwise.
   */
  const start = async (
    body?: Record<string, unknown>,
    query?: Record<string, string>,
  ): Promise<boolean> => {
    // #1432: Skip if already running to prevent 409 retry storms
    if (running.value) {
      logger.debug('Task already running, skipping start')
      return false
    }

    _startController?.abort()
    _startController = new AbortController()
    const signal = _startController.signal

    running.value = true
    progress.value = 0
    currentStep.value = null
    error.value = null
    wasInterrupted.value = false
    result.value = null

    try {
      const fetchOpts: RequestInit = { method: 'POST', signal }
      if (body) {
        fetchOpts.headers = { 'Content-Type': 'application/json' }
        fetchOpts.body = JSON.stringify(body)
      }

      const qs = query
        ? '?' + new URLSearchParams(query).toString()
        : ''

      let response = await postAnalyze(baseUrl, qs, fetchOpts)

      // Auto-clear stuck tasks on 409 and retry once
      if (response.status === 409 && resolvedClearUrl) {
        logger.info('Task conflict (409), clearing stuck tasks…')
        await clearStuckTasks(resolvedClearUrl, signal)
        response = await postAnalyze(baseUrl, qs, fetchOpts)
      }

      if (!response.ok) {
        const detail = response.status === 409
          ? 'Another analysis is still running. Please wait.'
          : `Start failed: ${response.statusText}`
        throw new Error(detail)
      }

      const data = await response.json()
      if (!data.task_id) {
        throw new Error('No task_id in response')
      }

      taskId.value = data.task_id
      taskStatus.value = { ...data, progress: 0, current_step: null, result: null }

      const pollResult = await poll(data.task_id)

      // Auto-retry once if orphaned: clear stuck tasks and start fresh
      if (pollResult === 'orphaned' && resolvedClearUrl) {
        logger.info('Task orphaned, clearing stuck tasks and retrying…')
        wasInterrupted.value = false
        error.value = null
        progress.value = 0

        // Check abort before retry
        if (signal.aborted) return false

        await clearStuckTasks(resolvedClearUrl, signal)
        const retryOpts: RequestInit = { method: 'POST', signal }
        if (body) {
          retryOpts.headers = { 'Content-Type': 'application/json' }
          retryOpts.body = JSON.stringify(body)
        }
        const retryResp = await postAnalyze(baseUrl, qs, retryOpts)
        if (!retryResp.ok) {
          throw new Error(`Retry failed: ${retryResp.statusText}`)
        }
        const retryData = await retryResp.json()
        if (!retryData.task_id) {
          throw new Error('No task_id in retry response')
        }
        taskId.value = retryData.task_id
        taskStatus.value = { ...retryData, progress: 0, current_step: null, result: null }
        await poll(retryData.task_id)
      }

      return !error.value
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        running.value = false
        return false
      }
      error.value = e instanceof Error ? e.message : String(e)
      logger.error('Background task start failed:', e)
      running.value = false
      return false
    }
  }

  /**
   * Poll GET /status/{id} every 2 s until completed or failed.
   * Resilient to transient network errors (up to MAX_CONSECUTIVE_ERRORS).
   * Uses usePollingJob internally; returns a Promise for caller convenience.
   *
   * @returns 'completed', 'failed', or 'orphaned' to let callers decide on retry.
   */
  const poll = (id: string): Promise<'completed' | 'failed' | 'orphaned' | 'error'> => {
    let consecutiveErrors = 0
    let resolved = false

    _pollController?.abort()
    _pollController = new AbortController()
    const pollSignal = _pollController.signal

    type PollResult = { done: boolean; outcome: 'completed' | 'failed' | 'orphaned' | 'error' | 'running' }

    return new Promise<'completed' | 'failed' | 'orphaned' | 'error'>((resolve) => {
      const settle = (outcome: 'completed' | 'failed' | 'orphaned' | 'error') => {
        if (!resolved) { resolved = true; resolve(outcome) }
      }

      const poller = usePollingJob<PollResult>(
        async () => {
          try {
            const backendUrl = await getBackendUrl()
            const resp = await fetchWithAuth( // fetchWithAuth retained: AbortController signal for polling abort — exempt (#6256)
              `${backendUrl}${baseUrl}/status/${id}`,
              { signal: pollSignal },
            )
            if (!resp.ok) throw new Error(`Status ${resp.status}`)

            const data: TaskStatus = await resp.json()
            taskStatus.value = data
            progress.value = data.progress ?? 0
            currentStep.value = data.current_step ?? null
            consecutiveErrors = 0

            if (data.status === 'completed') {
              result.value = data.result ?? null
              progress.value = 100
              running.value = false
              return { done: true, outcome: 'completed' }
            }

            if (data.status === 'failed') {
              const orphaned = data.reason === 'orphaned' || data.error?.includes('orphaned')
              if (orphaned) {
                wasInterrupted.value = true
                error.value = 'Previous task was interrupted by a server restart.'
              } else {
                error.value = data.error || 'Task failed'
              }
              running.value = false
              return { done: true, outcome: orphaned ? 'orphaned' : 'failed' }
            }

            return { done: false, outcome: 'running' }
          } catch (e: unknown) {
            if (e instanceof DOMException && e.name === 'AbortError') {
              running.value = false
              return { done: true, outcome: 'error' }
            }
            consecutiveErrors++
            const msg = e instanceof Error ? e.message : String(e)
            logger.warn(`Poll error (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS}): ${msg}`)
            if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
              error.value = `Lost connection after ${MAX_CONSECUTIVE_ERRORS} retries`
              running.value = false
              return { done: true, outcome: 'error' }
            }
            return { done: false, outcome: 'running' }
          }
        },
        {
          intervalMs: POLL_INTERVAL_MS,
          maxAttempts: 600, // 20 minutes max — terminal status settles much earlier
          isComplete: (r) => r.done,
          onDone: (r) => settle(r.outcome as 'completed' | 'failed' | 'orphaned' | 'error'),
        }
      )

      poller.start(id)
    })
  }

  /** Reset all state. */
  const reset = () => {
    running.value = false
    progress.value = 0
    currentStep.value = null
    error.value = null
    wasInterrupted.value = false
    result.value = null
    taskId.value = null
    taskStatus.value = null
  }

  onUnmounted(() => {
    _startController?.abort()
    _pollController?.abort()
  })

  return {
    running,
    progress,
    currentStep,
    error,
    wasInterrupted,
    result,
    taskId,
    taskStatus,
    start,
    reset,
  }
}

export default useBackgroundTask
