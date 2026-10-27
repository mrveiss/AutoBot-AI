// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useDashboardPoller — the SLM dashboard polling policy in one place (#19482).
 *
 * Owner decision 2026-10-25: a dashboard poller stops after
 * POLL_CONSECUTIVE_ERROR_LIMIT consecutive failures and the screen shows the shared
 * PollingPausedAlert with Retry, instead of polling a down backend forever. Every
 * dashboard migrated off a raw setInterval uses this, so the policy is not
 * re-declared per view.
 *
 * `tick` must throw on failure for it to count. Fetch functions that only record
 * their failure in an error ref are wrapped with `throwIfFailed`.
 */
import type { Ref } from 'vue'
import { usePollingJob, type UsePollingJobReturn } from '@autobot/ui'
import { POLL_CONSECUTIVE_ERROR_LIMIT } from '@/constants/api-timeouts'

export function useDashboardPoller(tick: () => Promise<void>, intervalMs: number): UsePollingJobReturn<void> {
  return usePollingJob(() => tick(), {
    intervalMs,
    maxAttempts: Infinity,
    consecutiveErrorLimit: POLL_CONSECUTIVE_ERROR_LIMIT,
  })
}

/** Wrap a fetch that records failure in `error` (instead of throwing) into a tick that throws. */
export function throwIfFailed(load: () => Promise<void>, error: Readonly<Ref<string | null | undefined>>) {
  return async (): Promise<void> => {
    await load()
    if (error.value) throw new Error(error.value)
  }
}
