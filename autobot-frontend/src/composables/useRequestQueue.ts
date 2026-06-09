// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Request Queue Composable
 *
 * Issue #4415: Backpressure for concurrent LLM calls.
 *
 * Provides a priority-ordered queue with deduplication so that at most
 * `concurrency` promises are in-flight at any time.  Callers sharing the
 * same `dedupeKey` receive the same promise whether the request is still
 * queued or already in-flight.
 */

import { ref, readonly } from 'vue'
import type { Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useRequestQueue')

export type Priority = 'high' | 'normal' | 'low'

const PRIORITY_ORDER: Record<Priority, number> = { high: 0, normal: 1, low: 2 }

export interface QueuedRequest<T> {
  fn: () => Promise<T>
  priority: Priority
  dedupeKey?: string
}

export interface UseRequestQueue {
  enqueue<T>(req: QueuedRequest<T>): Promise<T>
  readonly pending: Ref<number>
  readonly active: Ref<number>
  cancel(dedupeKey: string): void
}

interface QueueEntry<T = unknown> {
  fn: () => Promise<T>
  priority: Priority
  dedupeKey?: string
  /** The caller-facing promise returned by enqueue() */
  callerPromise: Promise<T>
  resolve: (value: T | PromiseLike<T>) => void
  reject: (reason?: unknown) => void
  cancelled: boolean
}

export function useRequestQueue(options?: { concurrency?: number }): UseRequestQueue {
  const concurrency = options?.concurrency ?? 3

  const _pending = ref(0)
  const _active = ref(0)

  // Queue entries sorted by priority on insertion
  const _queue: QueueEntry[] = []

  // Deduplication maps — keyed by dedupeKey, value is the caller-facing promise
  const _inflightByKey = new Map<string, Promise<unknown>>()
  const _pendingByKey = new Map<string, Promise<unknown>>()

  function _insertSorted(entry: QueueEntry): void {
    // Binary-insert to keep queue sorted by priority ascending (high=0 first)
    const rank = PRIORITY_ORDER[entry.priority]
    let lo = 0
    let hi = _queue.length
    while (lo < hi) {
      const mid = (lo + hi) >>> 1
      if (PRIORITY_ORDER[_queue[mid].priority] <= rank) lo = mid + 1
      else hi = mid
    }
    _queue.splice(lo, 0, entry)
    _pending.value++
  }

  function _tick(): void {
    while (_active.value < concurrency && _queue.length > 0) {
      const entry = _queue.shift()!
      _pending.value--

      if (entry.cancelled) {
        // Already cancelled — clean up dedup and skip
        if (entry.dedupeKey) _pendingByKey.delete(entry.dedupeKey)
        entry.reject(new DOMException('Request cancelled', 'AbortError'))
        continue
      }

      _active.value++
      logger.debug(`Starting request (active=${_active.value}, pending=${_pending.value})`)

      if (entry.dedupeKey) {
        // Promote from pending→inflight using the same caller-facing promise
        _pendingByKey.delete(entry.dedupeKey)
        _inflightByKey.set(entry.dedupeKey, entry.callerPromise as Promise<unknown>)
      }

      entry.fn().then(
        (value) => {
          if (entry.dedupeKey) _inflightByKey.delete(entry.dedupeKey)
          _active.value--
          logger.debug(`Request resolved (active=${_active.value})`)
          entry.resolve(value)
          _tick()
        },
        (err) => {
          if (entry.dedupeKey) _inflightByKey.delete(entry.dedupeKey)
          _active.value--
          logger.debug(`Request rejected (active=${_active.value})`)
          entry.reject(err)
          _tick()
        },
      )
    }
  }

  function enqueue<T>(req: QueuedRequest<T>): Promise<T> {
    const { fn, priority, dedupeKey } = req

    // Dedup: already in-flight? Return the same caller-facing promise.
    if (dedupeKey && _inflightByKey.has(dedupeKey)) {
      logger.debug(`Dedupe hit (in-flight): ${dedupeKey}`)
      return _inflightByKey.get(dedupeKey) as Promise<T>
    }

    // Dedup: already in the queue? Return the same caller-facing promise.
    if (dedupeKey && _pendingByKey.has(dedupeKey)) {
      logger.debug(`Dedupe hit (queued): ${dedupeKey}`)
      return _pendingByKey.get(dedupeKey) as Promise<T>
    }

    // Build the caller-facing promise before inserting into the queue so that
    // _tick() can immediately register it as the inflight dedup promise.
    let resolve!: (value: T | PromiseLike<T>) => void
    let reject!: (reason?: unknown) => void
    const callerPromise = new Promise<T>((res, rej) => {
      resolve = res
      reject = rej
    })

    const entry: QueueEntry<T> = {
      fn,
      priority,
      dedupeKey,
      callerPromise,
      resolve,
      reject,
      cancelled: false,
    }
    _insertSorted(entry as QueueEntry)

    if (dedupeKey) {
      _pendingByKey.set(dedupeKey, callerPromise as Promise<unknown>)
    }

    // Kick the scheduler
    _tick()

    return callerPromise
  }

  function cancel(dedupeKey: string): void {
    let cancelled = 0
    for (const entry of _queue) {
      if (entry.dedupeKey === dedupeKey && !entry.cancelled) {
        entry.cancelled = true
        cancelled++
      }
    }
    if (cancelled > 0) {
      logger.debug(`Cancelled ${cancelled} pending request(s) with key: ${dedupeKey}`)
    }
    // In-flight requests cannot be cancelled here — callers should use AbortSignal for that
  }

  return {
    enqueue,
    pending: readonly(_pending),
    active: readonly(_active),
    cancel,
  }
}

/**
 * Module-level singleton for shared use across composables.
 * Concurrency defaults to 3 simultaneous in-flight requests.
 */
export const requestQueue = useRequestQueue()
