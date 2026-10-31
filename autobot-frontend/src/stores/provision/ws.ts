// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Provision store WebSocket lifecycle (#19834, #7096): live updates while open, with polling as
 * the fallback when the socket fails or closes mid-run. The socket is on the page origin under
 * `/slm/api`, like every other SLM request.
 */
import { createLogger } from '@/utils/debugUtils'
import { slmWsUrl } from '@/utils/slmApi'
import { HEARTBEAT_STALE_MS, STALE_CHECK_INTERVAL_MS, type ProvisionCtx } from './context'
import { startPolling, stopPolling } from './poller'

const logger = createLogger('ProvisionStore')

// ── Stale-heartbeat watcher ─────────────────────────────────────────────────
// If the WebSocket goes silent (tab backgrounded, network blip) for longer than
// HEARTBEAT_STALE_MS, clear the stuck `currentTask` so the UI does not show an outdated
// "Still running... [task]" line.

function startStaleTaskWatcher(ctx: ProvisionCtx): void {
  const { state, runtime } = ctx
  if (runtime.staleTaskTimer !== null) return
  runtime.staleTaskTimer = window.setInterval(() => {
    if (state.currentTask.value && Date.now() - runtime.lastWsMessageAt > HEARTBEAT_STALE_MS) {
      logger.debug('Clearing stale heartbeat — no WS message for', Date.now() - runtime.lastWsMessageAt, 'ms')
      state.currentTask.value = ''
    }
  }, STALE_CHECK_INTERVAL_MS)
}

function stopStaleTaskWatcher(ctx: ProvisionCtx): void {
  if (ctx.runtime.staleTaskTimer !== null) {
    clearInterval(ctx.runtime.staleTaskTimer)
    ctx.runtime.staleTaskTimer = null
  }
}

// ── Messages ────────────────────────────────────────────────────────────────

interface WsMessage {
  type?: string
  log_type?: string
  message: string
  stage?: string
  status?: string
  elapsed_seconds?: number
  error?: string
}

function handlePhaseLog(ctx: ProvisionCtx, msg: WsMessage): void {
  const { state } = ctx
  const m = msg.message.match(/Provision Phase\s+(\S+):/)
  if (m) {
    if (state.currentPhase.value) state.completedPhases.value.add(state.currentPhase.value)
    state.currentPhase.value = m[1]
  }
  state.currentTask.value = ''
  state.logs.value.push({ type: 'phase', message: msg.message })
}

function handleLogMessage(ctx: ProvisionCtx, msg: WsMessage): void {
  const { state } = ctx
  if (msg.log_type === 'heartbeat') {
    state.currentTask.value = msg.message
  } else if (msg.log_type === 'phase') {
    handlePhaseLog(ctx, msg)
  } else {
    if (msg.log_type === 'task') state.currentTask.value = ''
    state.logs.value.push({ type: (msg.log_type || 'info') as 'info', message: msg.message })
  }
  ctx.runtime.linesSeen = state.logs.value.length
}

function handleCompleted(ctx: ProvisionCtx): void {
  const { state } = ctx
  if (state.currentPhase.value) state.completedPhases.value.add(state.currentPhase.value)
  state.currentTask.value = ''
  state.status.value = 'completed'
  state.finishedAt.value = Date.now()
  disconnectWs(ctx)
}

function handleFailed(ctx: ProvisionCtx, msg: WsMessage): void {
  const { state } = ctx
  state.logs.value.push({ type: 'error', message: msg.error || 'Provisioning failed' })
  state.status.value = 'failed'
  state.error.value = msg.error || 'Provisioning failed'
  state.finishedAt.value = Date.now()
  disconnectWs(ctx)
}

function handleStatusMessage(ctx: ProvisionCtx, msg: WsMessage): void {
  const { state } = ctx
  state.stage.value = msg.stage || ''
  state.elapsedSeconds.value = Math.round(msg.elapsed_seconds || 0)
  if (msg.status === 'completed') {
    handleCompleted(ctx)
  } else if (msg.status === 'failed') {
    handleFailed(ctx, msg)
  } else if (msg.status === 'running' && state.status.value === 'idle') {
    // Provision started elsewhere (e.g. from another tab) — pick up state
    state.status.value = 'running'
    state.startedAt.value = Date.now()
  }
}

export function handleWsMessage(ctx: ProvisionCtx, event: MessageEvent): void {
  ctx.runtime.lastWsMessageAt = Date.now()
  try {
    const msg: WsMessage = JSON.parse(event.data)
    if (msg.type === 'log') handleLogMessage(ctx, msg)
    else if (msg.type === 'status') handleStatusMessage(ctx, msg)
    else if (msg.type === 'ping') ctx.runtime.ws?.send('pong')
  } catch {
    // Ignore non-JSON messages
  }
}

// ── Connection ──────────────────────────────────────────────────────────────

function wireSocket(ctx: ProvisionCtx, ws: WebSocket): void {
  const { state, runtime } = ctx
  ws.onopen = () => {
    logger.info('Provision WebSocket connected')
    state.wsConnected.value = true
    runtime.lastWsMessageAt = Date.now()
    stopPolling(ctx)
    startStaleTaskWatcher(ctx)
  }
  ws.onmessage = (event) => handleWsMessage(ctx, event)
  ws.onclose = () => {
    logger.debug('Provision WebSocket closed')
    runtime.ws = null
    state.wsConnected.value = false
    stopStaleTaskWatcher(ctx)
    // Fall back to polling if provision is still running
    if (state.status.value === 'running') startPolling(ctx)
  }
  ws.onerror = (err) => {
    logger.error('Provision WebSocket error', err)
  }
}

export function connectWs(ctx: ProvisionCtx): void {
  const { runtime } = ctx
  if (runtime.ws?.readyState === WebSocket.OPEN || runtime.ws?.readyState === WebSocket.CONNECTING) {
    return
  }
  try {
    runtime.ws = new WebSocket(slmWsUrl('/ws/provision'))
  } catch (e) {
    logger.error('Failed to open provision WebSocket', e)
    startPolling(ctx) // fall back to polling immediately
    return
  }
  wireSocket(ctx, runtime.ws)
}

export function disconnectWs(ctx: ProvisionCtx): void {
  const { runtime, state } = ctx
  if (runtime.ws) {
    runtime.ws.onclose = null // suppress the fallback trigger
    runtime.ws.close()
    runtime.ws = null
  }
  state.wsConnected.value = false
  stopPolling(ctx)
  stopStaleTaskWatcher(ctx)
}
