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

import { ref, type Ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { getConfig } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

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
  } catch (_e) {
    logger.warn('AppConfig failed, using SSOT config backend URL')
    return getConfig().backendUrl
  }
}

/**
 * Clear stuck tasks for a given endpoint.
 * Shared helper used by both 409 recovery and orphan auto-retry.
 */
async function clearStuckTasks(clearUrl: string): Promise<void> {
  const backendUrl = await getBackendUrl()
  await fetchWithAuth(
    `${backendUrl}${clearUrl}?force=true`,
    { method: 'POST' },
  )
}

/**
 * POST to the /analyze endpoint and return the response.
 * Shared helper to avoid duplicating the fetch logic.
 */
async function postAnalyze(
  baseUrl: string,
  qs: string,
  fetchOpts: RequestInit,
): Promise<Response> {
  const backendUrl = await getBackendUrl()
  return fetchWithAuth(`${backendUrl}${baseUrl}/analyze${qs}`, fetchOpts)
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

    running.value = true
    progress.value = 0
    currentStep.value = null
    error.value = null
    wasInterrupted.value = false
    result.value = null

    try {
      const fetchOpts: RequestInit = { method: 'POST' }
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
        await clearStuckTasks(resolvedClearUrl)
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

        await clearStuckTasks(resolvedClearUrl)
        const retryResp = await postAnalyze(baseUrl, qs, fetchOpts)
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
      error.value = e instanceof Error ? e.message : String(e)
      logger.error('Background task start failed:', e)
      running.value = false
      return false
    }
  }

  /**
   * Poll GET /status/{id} every 2 s until completed or failed.
   * Resilient to transient network errors (up to MAX_CONSECUTIVE_ERRORS).
   *
   * @returns 'completed', 'failed', or 'orphaned' to let callers decide on retry.
   */
  const poll = (id: string): Promise<'completed' | 'failed' | 'orphaned' | 'error'> => {
    let consecutiveErrors = 0
    let intervalId: ReturnType<typeof setInterval> | null = null

    return new Promise<'completed' | 'failed' | 'orphaned' | 'error'>((resolve) => {
      const stop = () => {
        if (intervalId !== null) {
          clearInterval(intervalId)
          intervalId = null
        }
      }

      const tick = async () => {
        try {
          const backendUrl = await getBackendUrl()
          const resp = await fetchWithAuth(
            `${backendUrl}${baseUrl}/status/${id}`,
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
            stop()
            resolve('completed')
            return
          }

          if (data.status === 'failed') {
            const orphaned = data.reason === 'orphaned'
              || data.error?.includes('orphaned')
            if (orphaned) {
              wasInterrupted.value = true
              error.value = 'Previous task was interrupted by a server restart.'
              running.value = false
              stop()
              resolve('orphaned')
            } else {
              error.value = data.error || 'Task failed'
              running.value = false
              stop()
              resolve('failed')
            }
            return
          }
        } catch (e: unknown) {
          consecutiveErrors++
          const msg = e instanceof Error ? e.message : String(e)
          logger.warn(
            `Poll error (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS}): ${msg}`,
          )
          if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
            error.value = `Lost connection after ${MAX_CONSECUTIVE_ERRORS} retries`
            running.value = false
            stop()
            resolve('error')
          }
        }
      }

      tick()
      intervalId = setInterval(tick, POLL_INTERVAL_MS)
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
