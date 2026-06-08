// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * usePollingJob — managed setInterval wrapper for task-status polling.
 *
 * Extracted from KB components that each manually managed setInterval with
 * inconsistent cleanup and error handling (#5191).
 *
 * Features:
 * - Auto-cleanup via `onScopeDispose` — no component-unmount leaks
 * - Last-caller-wins race protection: re-calling `start()` abandons in-flight fetches
 * - `isComplete` callback decides terminal state; `onDone` fires once
 * - Errors stored in `error` ref; polling continues on transient errors until `maxAttempts`
 *
 * @example
 * ```ts
 * const { start, stop, data, isPolling } = usePollingJob(
 *   (taskId) => pollJobStatusAPI(taskId),
 *   {
 *     intervalMs: 2000,
 *     isComplete: (r) => r.status === 'SUCCESS' || r.status === 'FAILURE',
 *     onDone: (r) => { if (r.status === 'SUCCESS') refreshStats() }
 *   }
 * )
 * start(taskId)
 * ```
 */

import { ref, readonly, onScopeDispose, getCurrentScope, isRef } from 'vue'
import type { Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('usePollingJob')

export interface UsePollingJobOptions<T> {
  /** Poll interval in milliseconds. Accepts a plain number or a `Ref<number>` for reactive intervals. Default: 2000. */
  intervalMs?: number | Ref<number>
  /** Maximum attempts before auto-stopping. Default: 60. */
  maxAttempts?: number
  /** Callback fired once when `isComplete` returns true. */
  onDone?: (data: T) => void
  /** Return true to stop polling (terminal state reached). Default: never complete. */
  isComplete?: (data: T) => boolean
  /**
   * Stop polling after N consecutive errors (independent of `maxAttempts`).
   * Resets to 0 on any successful poll tick.
   *
   * Use for endpoints that 404 repeatedly — these would otherwise spam the
   * console forever when backend routes are missing.  Default: unlimited.
   *
   * #6765: circuit-breaker for mass-404 endpoints.
   */
  consecutiveErrorLimit?: number
}

export interface UsePollingJobReturn<T> {
  isPolling: Readonly<Ref<boolean>>
  data: Readonly<Ref<T | null>>
  error: Readonly<Ref<Error | null>>
  attempts: Readonly<Ref<number>>
  /**
   * Start polling for the given taskId. Any in-flight polling is stopped first.
   * Pass an empty string when the fetcher doesn't need a task key.
   */
  start: (taskId: string) => void
  /** Stop polling and clear the interval. Safe to call multiple times. */
  stop: () => void
}

export function usePollingJob<T>(
  fetcher: (taskId: string) => Promise<T>,
  options: UsePollingJobOptions<T> = {}
): UsePollingJobReturn<T> {
  const {
    maxAttempts = 60,
    onDone,
    isComplete,
    consecutiveErrorLimit
  } = options

  const isPolling = ref(false)
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<Error | null>(null)
  const attempts = ref(0)

  let timer: ReturnType<typeof setInterval> | null = null
  let currentTaskId: string | null = null
  let consecutiveErrors = 0

  function stop(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    isPolling.value = false
    currentTaskId = null
  }

  async function poll(taskId: string): Promise<void> {
    // Race guard — if a newer start() replaced this taskId, abandon the tick
    if (taskId !== currentTaskId) return

    attempts.value += 1
    try {
      const result = await fetcher(taskId)
      if (taskId !== currentTaskId) return
      consecutiveErrors = 0
      data.value = result
      if (isComplete?.(result) ?? false) {
        stop()
        onDone?.(result)
        return
      }
    } catch (err) {
      if (taskId !== currentTaskId) return
      consecutiveErrors += 1
      error.value = err instanceof Error ? err : new Error(String(err))
      logger.warn(`polling attempt ${attempts.value} failed: ${error.value.message}`)
      if (consecutiveErrorLimit !== undefined && consecutiveErrors >= consecutiveErrorLimit) {
        logger.info(`polling stopped after ${consecutiveErrors} consecutive errors (consecutiveErrorLimit=${consecutiveErrorLimit})`)
        stop()
        return
      }
    }

    if (attempts.value >= maxAttempts) {
      logger.info(`polling reached maxAttempts (${maxAttempts}), stopping`)
      stop()
    }
  }

  function start(taskId: string): void {
    stop()
    currentTaskId = taskId
    attempts.value = 0
    consecutiveErrors = 0
    error.value = null
    data.value = null
    isPolling.value = true
    // Fire immediately so callers don't wait `intervalMs` before the first tick
    void poll(taskId)
    const ms = isRef(options.intervalMs) ? options.intervalMs.value : (options.intervalMs ?? 2000)
    timer = setInterval(() => void poll(taskId), ms)
  }

  // Auto-cleanup when owning scope (component / effectScope) disposes
  if (getCurrentScope()) {
    onScopeDispose(stop)
  }

  return {
    isPolling: readonly(isPolling),
    data: readonly(data) as Readonly<Ref<T | null>>,
    error: readonly(error),
    attempts: readonly(attempts),
    start,
    stop
  }
}
