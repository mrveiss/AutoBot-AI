// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Provision Store (#19834, ported from the SLM app's `stores/provision.ts`, #7096)
 *
 * Fleet provisioning state, lifted out of the setup wizard view so it survives unmounting,
 * a tab refresh (state recovers from the backend GET) and a WebSocket drop (falls back to
 * polling). Short setup over slices: `ws.ts` (live updates), `poller.ts` (fallback),
 * `status.ts` (the poll tick, resync, start/reset).
 */
import { computed } from 'vue'
import { defineStore } from 'pinia'
import { bindSlice } from '../bindSlice'
import { createProvisionContext, formatElapsed } from './context'
import { createStatusPoller, isPollingPaused, retryPolling } from './poller'
import { pollProvisionStatus, reset, restoreFromBackend, start } from './status'
import { connectWs, disconnectWs } from './ws'

export type { ProvisionLogEntry, ProvisionStatus } from './context'

export const useProvisionStore = defineStore('provision', () => {
  const ctx = createProvisionContext()
  ctx.runtime.poller = createStatusPoller(() => pollProvisionStatus(ctx))
  const { status, elapsedSeconds } = ctx.state

  const isRunning = computed(() => status.value === 'running')
  const isComplete = computed(() => status.value === 'completed')
  const isFailed = computed(() => status.value === 'failed')
  const isActive = computed(() => isRunning.value || isComplete.value || isFailed.value)
  const elapsedFormatted = computed(() => formatElapsed(elapsedSeconds.value))
  const pollingPaused = computed(() => isPollingPaused(ctx))

  return {
    ...ctx.state,
    isRunning,
    isComplete,
    isFailed,
    isActive,
    elapsedFormatted,
    pollingPaused,
    ...bindSlice(ctx, { start, restoreFromBackend, reset, connectWs, disconnectWs, retryPolling }),
  }
})
