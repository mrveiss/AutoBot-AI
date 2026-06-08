// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Helper: runTimed
 *
 * Times an async operation and fans the result out to success / failure
 * handlers with the elapsed duration. Optionally toggles a loading ref
 * around the operation.
 *
 * Extracts the shared kernel of the two `notifyTimed` helpers that were
 * inlined in useAnalyticsDataFetchers (#5112) and useCodeSmellAnalysis
 * (#5153 A-1 / PR #5157). Issue #5153 scope D-2.
 *
 * NB: this is a plain async function, not a composable. It holds no
 * reactive state of its own; the loading ref (when provided) is owned
 * by the caller.
 */

import type { Ref } from 'vue'

export interface RunTimedOptions {
  /**
   * Optional loading ref. Set to `true` before `fn()` starts and `false`
   * in `finally` — including when `onSuccess` or `onFail` throws.
   */
  loadingRef?: Ref<boolean>
}

/**
 * @param fn        operation being timed
 * @param onSuccess called on fulfilled `fn()` with (result, elapsedMs)
 * @param onFail    called on rejected `fn()` with (errorMessage, elapsedMs, originalError)
 * @param options   see {@link RunTimedOptions}
 */
export async function runTimed<T>(
  fn: () => Promise<T>,
  onSuccess: (result: T, elapsedMs: number) => void,
  onFail: (errorMessage: string, elapsedMs: number, err: unknown) => void,
  options?: RunTimedOptions,
): Promise<void> {
  const startTime = Date.now()
  if (options?.loadingRef) options.loadingRef.value = true
  try {
    let result: T
    try {
      result = await fn()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      onFail(message, Date.now() - startTime, err)
      return
    }
    // Handler errors must propagate (they are not fn-failures); the outer
    // finally still resets the loading ref either way.
    onSuccess(result, Date.now() - startTime)
  } finally {
    if (options?.loadingRef) options.loadingRef.value = false
  }
}
