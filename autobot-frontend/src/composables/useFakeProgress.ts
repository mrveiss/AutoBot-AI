// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useFakeProgress — simulated progress counter for long-running operations
 * where the backend provides no real progress signal.
 *
 * The counter increments by `step` every `intervalMs` until it reaches `cap`.
 * It never advances past `cap` automatically — only a `finish()` call jumps
 * the counter to `target`, signalling completion.
 *
 * Extracted from KnowledgeAdvanced.vue (#5237), where three populate actions
 * and one clear action share the same fake-progress scaffold while backend
 * work runs.
 *
 * @example
 * ```ts
 * const fake = useFakeProgress({ target: 150, intervalMs: 100 })
 * fake.start()
 * try {
 *   await ApiClient.post<any>('/populate', {})
 *   fake.finish()
 * } finally {
 *   fake.stop()
 * }
 * ```
 */

import { ref, readonly, onScopeDispose, getCurrentScope } from 'vue'
import type { Ref } from 'vue'

export interface UseFakeProgressOptions {
  /** Target value the counter completes at. Default 100. */
  target?: number
  /** Ms between ticks. Default 100. */
  intervalMs?: number
  /** Increment applied per tick. Default 1. */
  step?: number
  /** Ceiling the auto-ticker will not exceed. Only `finish()` reaches `target`. Default `target - 1`. */
  cap?: number
}

export interface UseFakeProgressStartOverrides {
  /** Override the constructor-level target for this run. */
  target?: number
  /** Override the constructor-level cap for this run. */
  cap?: number
  /** Override the constructor-level step for this run. */
  step?: number
  /** Override the constructor-level interval for this run. */
  intervalMs?: number
}

export interface UseFakeProgressReturn {
  /** Current progress counter. Starts at 0, caps at `cap`, jumps to `target` on finish(). */
  progress: Readonly<Ref<number>>
  /** True while the interval is active. */
  isRunning: Readonly<Ref<boolean>>
  /**
   * Start ticking up toward `cap`. If already running, resets to 0 and restarts.
   * Optional overrides replace constructor values for this run only; next call
   * without overrides reverts to constructor defaults.
   */
  start: (overrides?: UseFakeProgressStartOverrides) => void
  /** Jump to `target` (as configured for the current run) and stop ticking. */
  finish: () => void
  /** Halt at current value without completing. */
  stop: () => void
  /** Reset to 0 and halt. */
  reset: () => void
}

export function useFakeProgress(
  options: UseFakeProgressOptions = {}
): UseFakeProgressReturn {
  const defaultTarget = options.target ?? 100
  const defaultIntervalMs = options.intervalMs ?? 100
  const defaultStep = options.step ?? 1
  const defaultCap = options.cap ?? defaultTarget - 1

  // Active run configuration (re-assigned each start() so overrides apply)
  let activeTarget = defaultTarget
  let activeCap = defaultCap

  const progress = ref(0)
  const isRunning = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  function clearTimer(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function stop(): void {
    clearTimer()
    isRunning.value = false
  }

  function start(overrides: UseFakeProgressStartOverrides = {}): void {
    clearTimer()
    activeTarget = overrides.target ?? defaultTarget
    activeCap = overrides.cap ?? (overrides.target !== undefined
      ? overrides.target - 1
      : defaultCap)
    const runStep = overrides.step ?? defaultStep
    const runInterval = overrides.intervalMs ?? defaultIntervalMs

    progress.value = 0
    isRunning.value = true
    timer = setInterval(() => {
      if (progress.value >= activeCap) return
      progress.value = Math.min(progress.value + runStep, activeCap)
    }, runInterval)
  }

  function finish(): void {
    clearTimer()
    progress.value = activeTarget
    isRunning.value = false
  }

  function reset(): void {
    clearTimer()
    activeTarget = defaultTarget
    activeCap = defaultCap
    progress.value = 0
    isRunning.value = false
  }

  if (getCurrentScope()) {
    onScopeDispose(stop)
  }

  return {
    progress: readonly(progress),
    isRunning: readonly(isRunning),
    start,
    finish,
    stop,
    reset
  }
}
