// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Exponential backoff poller with circuit breaker and in-flight deduplication.
 *
 * Prevents the 499 (client closed connection) cascade seen in issue #1100 by:
 * - Skipping a poll when the previous one is still in-flight (deduplication)
 * - Backing off exponentially when the backend is failing
 * - Opening a circuit breaker after N consecutive failures and retrying slowly
 * - Respecting page visibility (pauses when tab is hidden)
 */

import { ref, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useBackoffPoller')

export interface BackoffPollerOptions {
  /** Function to call each poll cycle. May throw on error. */
  fn: () => Promise<void>
  /** Base polling interval in ms (used when healthy). Default 10 000 */
  baseInterval?: number
  /** Maximum backoff interval in ms. Default 60 000 */
  maxInterval?: number
  /** Multiply interval by this factor on each failure. Default 2 */
  backoffMultiplier?: number
  /** Number of consecutive failures before opening circuit. Default 3 */
  circuitBreakerThreshold?: number
  /** How long (ms) to wait in open-circuit state before retrying. Default 60 000 */
  circuitBreakerResetMs?: number
}

export interface BackoffPollerReturn {
  /** Start the poller. Safe to call multiple times (no-op if already running). */
  start: () => void
  /** Stop the poller and cancel any pending timer. */
  stop: () => void
  /** Whether the circuit breaker is currently open. */
  isCircuitOpen: ReturnType<typeof ref<boolean>>
  /** Current number of consecutive failures. */
  consecutiveFailures: ReturnType<typeof ref<number>>
  /** Current effective polling interval (ms). */
  currentInterval: ReturnType<typeof ref<number>>
}

export function useBackoffPoller(options: BackoffPollerOptions): BackoffPollerReturn {
  const {
    fn,
    baseInterval = 10_000,
    maxInterval = 60_000,
    backoffMultiplier = 2,
    circuitBreakerThreshold = 3,
    circuitBreakerResetMs = 60_000,
  } = options

  // State
  const isCircuitOpen = ref(false)
  const consecutiveFailures = ref(0)
  const currentInterval = ref(baseInterval)

  let timerId: ReturnType<typeof setTimeout> | null = null
  let inFlight = false
  let running = false

  // ---- helpers ----

  function _clearTimer() {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
  }

  function _scheduleNext(intervalMs: number) {
    _clearTimer()
    if (!running) return
    timerId = setTimeout(_tick, intervalMs)
  }

  async function _tick() {
    if (!running) return

    // Circuit breaker open — schedule a slow retry probe
    if (isCircuitOpen.value) {
      logger.debug('Circuit open — slow probe in', circuitBreakerResetMs, 'ms')
      _scheduleNext(circuitBreakerResetMs)
      return
    }

    // Skip if previous request is still in flight
    if (inFlight) {
      logger.debug('Skipping poll — previous request still in flight')
      _scheduleNext(currentInterval.value)
      return
    }

    inFlight = true
    try {
      await fn()
      // Success: reset backoff
      consecutiveFailures.value = 0
      currentInterval.value = baseInterval
    } catch (err) {
      consecutiveFailures.value++
      const newInterval = Math.min(
        currentInterval.value * backoffMultiplier,
        maxInterval,
      )
      currentInterval.value = newInterval
      logger.warn(
        `Poll failed (attempt ${consecutiveFailures.value}), next in ${newInterval}ms:`,
        err,
      )

      if (consecutiveFailures.value >= circuitBreakerThreshold) {
        isCircuitOpen.value = true
        logger.warn(`Circuit breaker opened after ${consecutiveFailures.value} failures`)
        _scheduleNext(circuitBreakerResetMs)
        inFlight = false
        return
      }
    } finally {
      inFlight = false
    }

    _scheduleNext(currentInterval.value)
  }

  // Pause/resume on page visibility
  const _onVisibilityChange = () => {
    if (document.hidden) {
      _clearTimer()
    } else if (running) {
      // Reset consecutive failures when tab becomes visible again and probe the backend
      if (isCircuitOpen.value) {
        isCircuitOpen.value = false
        consecutiveFailures.value = 0
        currentInterval.value = baseInterval
        logger.debug('Tab visible — circuit reset, resuming polling')
      }
      _scheduleNext(currentInterval.value)
    }
  }

  document.addEventListener('visibilitychange', _onVisibilityChange)

  // ---- public API ----

  function start() {
    if (running) return
    running = true
    logger.debug(`Poller started (base: ${baseInterval}ms, max: ${maxInterval}ms)`)
    _scheduleNext(baseInterval)
  }

  function stop() {
    running = false
    _clearTimer()
    document.removeEventListener('visibilitychange', _onVisibilityChange)
    logger.debug('Poller stopped')
  }

  onUnmounted(stop)

  return { start, stop, isCircuitOpen, consecutiveFailures, currentInterval }
}
