// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Provision store status actions (#19834, #7096): the poll tick, resync from the backend, and
 * the start/reset lifecycle. Backend state lives in the SLM API's in-memory provision state, so
 * a backend restart loses tracking (#7096 follow-up: Redis persistence).
 */
import { createLogger } from '@/utils/debugUtils'
import type { ProvisionStatusResult } from '@/utils/slmApi/provision'
import type { ProvisionCtx } from './context'
import { stopPolling } from './poller'
import { connectWs, disconnectWs } from './ws'

const logger = createLogger('ProvisionStore')

function appendLines(ctx: ProvisionCtx, lines: string[]): void {
  for (const line of lines) {
    ctx.state.logs.value.push({ type: 'info', message: line })
  }
}

function noteElapsed(ctx: ProvisionCtx, result: ProvisionStatusResult): void {
  if (result.elapsed_seconds !== undefined) {
    ctx.state.elapsedSeconds.value = Math.round(result.elapsed_seconds)
  }
}

/** One poll tick; a failed read throws so the poller counts it. */
export async function pollProvisionStatus(ctx: ProvisionCtx): Promise<void> {
  const { state, runtime } = ctx
  const result = await ctx.api.getProvisionStatus(runtime.linesSeen)
  if (result.lines.length > 0) {
    appendLines(ctx, result.lines)
    runtime.linesSeen = result.total_lines
  }
  noteElapsed(ctx, result)
  if (result.status === 'completed') {
    state.status.value = 'completed'
    state.finishedAt.value = Date.now()
    stopPolling(ctx)
    connectWs(ctx) // try reconnecting the socket for any final messages
  } else if (result.status === 'failed') {
    state.status.value = 'failed'
    state.error.value = result.error || 'Provisioning failed'
    state.finishedAt.value = Date.now()
    stopPolling(ctx)
  }
}

function applyRestored(ctx: ProvisionCtx, result: ProvisionStatusResult): void {
  const { state } = ctx
  if (result.status === 'running') {
    state.status.value = 'running'
    state.startedAt.value = state.startedAt.value ?? Date.now()
    connectWs(ctx) // reconnect for live updates
  } else if (result.status === 'completed') {
    state.status.value = 'completed'
    state.finishedAt.value = Date.now()
  } else if (result.status === 'failed') {
    state.status.value = 'failed'
    state.error.value = result.error || 'Provisioning failed'
    state.finishedAt.value = Date.now()
  }
}

/**
 * Resync provision state from the backend. Call from any view's onMounted (or app-level setup)
 * to recover state after navigation, tab refresh, or backend restart.
 */
export async function restoreFromBackend(ctx: ProvisionCtx): Promise<void> {
  try {
    const result = await ctx.api.getProvisionStatus(0)
    // 'idle' means no provision has run on this server, or a previous run was reset.
    if (!result.status || result.status === 'idle') {
      return
    }
    ctx.state.logs.value = result.lines.map((line) => ({ type: 'info' as const, message: line }))
    ctx.runtime.linesSeen = result.total_lines
    noteElapsed(ctx, result)
    applyRestored(ctx, result)
  } catch (err) {
    logger.error('Failed to restore provision state from backend', err)
  }
}

/** Reset to idle and disconnect the socket and polling, for a new run after one is acknowledged. */
export function reset(ctx: ProvisionCtx): void {
  const { state, runtime } = ctx
  disconnectWs(ctx)
  state.status.value = 'idle'
  state.stage.value = ''
  state.elapsedSeconds.value = 0
  state.currentTask.value = ''
  state.currentPhase.value = ''
  state.completedPhases.value = new Set()
  state.logs.value = []
  state.error.value = null
  state.startedAt.value = null
  state.finishedAt.value = null
  runtime.linesSeen = 0
  runtime.lastWsMessageAt = 0
}

/**
 * Start a fresh provisioning run: reset state and connect the socket. The caller invokes the
 * actual API that starts the backend playbook; this only sets up live tracking.
 */
export function start(ctx: ProvisionCtx): void {
  reset(ctx)
  ctx.state.status.value = 'running'
  ctx.state.startedAt.value = Date.now()
  connectWs(ctx)
}
