// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Provision store polling fallback (#19834, #19482): the shared dashboard policy. The poller
 * lives in the store's scope, so it outlives the wizard view (#7096); it stops after repeated
 * failures, and `pollingPaused` lets the screen show the paused alert, whose Retry calls
 * `retryPolling`.
 */
import { usePollingJob } from '@/composables/usePollingJob'
import { createLogger } from '@/utils/debugUtils'
import { POLL_CONSECUTIVE_ERROR_LIMIT, POLL_INTERVAL_MS, type ProvisionCtx } from './context'

const logger = createLogger('ProvisionStore')

/** Create the poller for `tick`; a failed read must throw so the poller counts it. */
export function createStatusPoller(tick: () => Promise<void>) {
  return usePollingJob(() => tick(), {
    intervalMs: POLL_INTERVAL_MS,
    maxAttempts: Infinity,
    consecutiveErrorLimit: POLL_CONSECUTIVE_ERROR_LIMIT,
  })
}

function poller(ctx: ProvisionCtx) {
  if (!ctx.runtime.poller) throw new Error('The provision poller is not created')
  return ctx.runtime.poller
}

export function startPolling(ctx: ProvisionCtx): void {
  if (poller(ctx).isPolling.value) return
  logger.info('Starting provision polling fallback')
  poller(ctx).start('')
}

export function stopPolling(ctx: ProvisionCtx): void {
  poller(ctx).stop()
}

/** Retry after the poller paused on repeated failures. */
export function retryPolling(ctx: ProvisionCtx): void {
  logger.info('Restarting provision polling after a pause')
  poller(ctx).start('')
}

export function isPollingPaused(ctx: ProvisionCtx): boolean {
  return poller(ctx).pausedOnErrors.value
}
