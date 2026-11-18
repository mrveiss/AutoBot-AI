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

/** Apply one polled snapshot of a run that is still the current one. */
function applyPolled(ctx: ProvisionCtx, result: ProvisionStatusResult): void {
  const { state, runtime } = ctx
  runtime.revision++
  if (result.status === 'idle') {
    // The backend no longer tracks the run (it restarted): the local run is lost, not running.
    reset(ctx)
    return
  }
  if (result.lines.length > 0) {
    appendLines(ctx, result.lines)
    runtime.linesSeen = result.total_lines
  }
  noteElapsed(ctx, result)
  if (result.status === 'completed') {
    state.status.value = 'completed'
    state.finishedAt.value = Date.now()
    stopPolling(ctx) // the server sends no terminal frame to a late socket, so none is opened
  } else if (result.status === 'failed') {
    state.status.value = 'failed'
    state.error.value = result.error || 'Provisioning failed'
    state.finishedAt.value = Date.now()
    stopPolling(ctx)
  }
}

/**
 * One poll tick; a failed read throws so the poller counts it. At most one read is in flight per
 * polling run, so every read starts from the cursor the previous one committed, and a read that
 * resolves after its run was stopped (a reset, or a socket taking over) is dropped.
 */
export async function pollProvisionStatus(ctx: ProvisionCtx): Promise<void> {
  const { runtime } = ctx
  const generation = runtime.pollGeneration
  if (runtime.pollInFlight === generation) return
  runtime.pollInFlight = generation
  try {
    const result = await ctx.api.getProvisionStatus(runtime.linesSeen)
    if (generation !== runtime.pollGeneration) return
    applyPolled(ctx, result)
  } finally {
    if (runtime.pollInFlight === generation) runtime.pollInFlight = null
  }
}

function applyRestored(ctx: ProvisionCtx, result: ProvisionStatusResult): void {
  const { state } = ctx
  if (result.status === 'running') {
    state.status.value = 'running'
    state.startedAt.value = state.startedAt.value ?? Date.now()
    connectWs(ctx) // reconnect for live updates
    return
  }
  if (result.status !== 'completed' && result.status !== 'failed') return
  state.status.value = result.status
  if (result.status === 'failed') state.error.value = result.error || 'Provisioning failed'
  state.finishedAt.value = Date.now()
  disconnectWs(ctx) // a finished run needs neither a socket, its heartbeat watcher nor polling
}

/**
 * Resync provision state from the backend. Call from any view's onMounted (or app-level setup)
 * to recover state after navigation, tab refresh, or backend restart. A snapshot that newer
 * tracking data (a socket frame, a poll result, a reset) overtook while it was in flight is dropped.
 */
export async function restoreFromBackend(ctx: ProvisionCtx): Promise<void> {
  const revision = ctx.runtime.revision
  try {
    const result = await ctx.api.getProvisionStatus(0)
    if (revision !== ctx.runtime.revision) return
    if (!result.status) return
    // 'idle' is authoritative: no provision has run on this server, a previous run was reset, or
    // the backend restarted and lost the run the store still shows.
    if (result.status === 'idle') {
      reset(ctx)
      return
    }
    ctx.runtime.revision++
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
  runtime.revision++
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
