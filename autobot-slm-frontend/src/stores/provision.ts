// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Provision Store (#7096)
 *
 * Pinia store for fleet provisioning state. Lifts state out of
 * SetupWizardView so it survives:
 *   - Component unmount (user navigates to another page)
 *   - Browser tab refresh (state recovers from backend GET)
 *   - WebSocket disconnect (auto-falls back to polling)
 *
 * Architecture:
 *   - WS for live updates while open (low-latency)
 *   - Polling as fallback (handles tab background, network blips)
 *   - GET /provision-status on mount (resync after reload/navigation)
 *
 * Backend state lives in SLM API (api/setup_wizard.py:_provision_state)
 * which is currently in-memory only. Backend restart loses tracking
 * (filed as #7096 follow-up — Redis persistence).
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { getConfig } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProvisionStore')

export type ProvisionStatus = 'idle' | 'running' | 'completed' | 'failed'

export interface ProvisionLogEntry {
  type: 'info' | 'task' | 'success' | 'error' | 'warning' | 'phase'
  message: string
}

const POLL_INTERVAL_MS = 3000
const HEARTBEAT_STALE_MS = 30000  // Clear stuck "Still running..." after 30s without WS update

export const useProvisionStore = defineStore('provision', () => {
  const api = useSlmApi()

  // ── State ───────────────────────────────────────────────────────────────
  const status = ref<ProvisionStatus>('idle')
  const stage = ref('')
  const elapsedSeconds = ref(0)
  const currentTask = ref('')
  const currentPhase = ref('')
  const completedPhases = ref<Set<string>>(new Set())
  const logs = ref<ProvisionLogEntry[]>([])
  const error = ref<string | null>(null)
  const startedAt = ref<number | null>(null)
  const finishedAt = ref<number | null>(null)
  const wsConnected = ref(false)

  // ── Computed ────────────────────────────────────────────────────────────
  const isRunning = computed(() => status.value === 'running')
  const isComplete = computed(() => status.value === 'completed')
  const isFailed = computed(() => status.value === 'failed')
  const isActive = computed(() => isRunning.value || isComplete.value || isFailed.value)
  const elapsedFormatted = computed(() => formatElapsed(elapsedSeconds.value))

  function formatElapsed(seconds: number): string {
    if (seconds < 60) return `${seconds}s`
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}m ${secs}s`
  }

  // ── Internal: WebSocket lifecycle ───────────────────────────────────────
  let ws: WebSocket | null = null
  let pollTimer: number | null = null
  let linesSeen = 0
  let lastWsMessageAt = 0
  let staleTaskTimer: number | null = null

  function connectWs(): void {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
      return
    }
    const cfg = getConfig()
    const apiPrefix = cfg.apiBaseUrl.startsWith('/') ? cfg.apiBaseUrl : ''
    const url = `${cfg.wsBaseUrl}${apiPrefix}/api/ws/provision`

    try {
      ws = new WebSocket(url)
    } catch (e) {
      logger.error('Failed to open provision WebSocket', e)
      // Fall back to polling immediately
      startPolling()
      return
    }

    ws.onopen = () => {
      logger.info('Provision WebSocket connected')
      wsConnected.value = true
      lastWsMessageAt = Date.now()
      stopPolling()
      startStaleTaskWatcher()
    }
    ws.onmessage = handleWsMessage
    ws.onclose = () => {
      logger.debug('Provision WebSocket closed')
      ws = null
      wsConnected.value = false
      stopStaleTaskWatcher()
      // Fall back to polling if provision is still running
      if (isRunning.value) {
        startPolling()
      }
    }
    ws.onerror = (err) => {
      logger.error('Provision WebSocket error', err)
    }
  }

  function disconnectWs(): void {
    if (ws) {
      ws.onclose = null  // Suppress fallback trigger
      ws.close()
      ws = null
    }
    wsConnected.value = false
    stopPolling()
    stopStaleTaskWatcher()
  }

  function handleWsMessage(event: MessageEvent): void {
    lastWsMessageAt = Date.now()
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'log') {
        if (msg.log_type === 'heartbeat') {
          currentTask.value = msg.message
        } else if (msg.log_type === 'phase') {
          const m = msg.message.match(/Provision Phase\s+(\S+):/)
          if (m) {
            if (currentPhase.value) completedPhases.value.add(currentPhase.value)
            currentPhase.value = m[1]
          }
          currentTask.value = ''
          logs.value.push({ type: 'phase', message: msg.message })
        } else {
          if (msg.log_type === 'task') currentTask.value = ''
          logs.value.push({
            type: msg.log_type || 'info',
            message: msg.message,
          })
        }
        linesSeen = logs.value.length
      } else if (msg.type === 'status') {
        stage.value = msg.stage || ''
        elapsedSeconds.value = Math.round(msg.elapsed_seconds || 0)

        if (msg.status === 'completed') {
          if (currentPhase.value) completedPhases.value.add(currentPhase.value)
          currentTask.value = ''
          status.value = 'completed'
          finishedAt.value = Date.now()
          disconnectWs()
        } else if (msg.status === 'failed') {
          logs.value.push({
            type: 'error',
            message: msg.error || 'Provisioning failed',
          })
          status.value = 'failed'
          error.value = msg.error || 'Provisioning failed'
          finishedAt.value = Date.now()
          disconnectWs()
        } else if (msg.status === 'running' && status.value === 'idle') {
          // Provision started elsewhere (e.g. from another tab) — pick up state
          status.value = 'running'
          startedAt.value = Date.now()
        }
      } else if (msg.type === 'ping') {
        ws?.send('pong')
      }
    } catch {
      // Ignore non-JSON messages
    }
  }

  // ── Internal: polling fallback ──────────────────────────────────────────
  function startPolling(): void {
    if (pollTimer !== null) return
    logger.info('Starting provision polling fallback')
    pollTimer = window.setInterval(async () => {
      try {
        const result = await api.getProvisionStatus(linesSeen)
        if (result.lines.length > 0) {
          for (const line of result.lines) {
            logs.value.push({ type: 'info', message: line })
          }
          linesSeen = result.total_lines
        }
        if (result.elapsed_seconds !== undefined) {
          elapsedSeconds.value = Math.round(result.elapsed_seconds)
        }
        if (result.status === 'completed') {
          status.value = 'completed'
          finishedAt.value = Date.now()
          stopPolling()
          // Try reconnecting WS for any final messages
          connectWs()
        } else if (result.status === 'failed') {
          status.value = 'failed'
          error.value = result.error || 'Provisioning failed'
          finishedAt.value = Date.now()
          stopPolling()
        }
      } catch (err) {
        logger.error('Provision polling error', err)
      }
    }, POLL_INTERVAL_MS) as unknown as number
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ── Internal: stale-heartbeat watcher ───────────────────────────────────
  // If the WebSocket goes silent (browser tab backgrounded, network blip)
  // for longer than HEARTBEAT_STALE_MS, clear the stuck `currentTask` so
  // the UI doesn't display an outdated "Still running... [task]" line.
  function startStaleTaskWatcher(): void {
    if (staleTaskTimer !== null) return
    staleTaskTimer = window.setInterval(() => {
      if (currentTask.value && Date.now() - lastWsMessageAt > HEARTBEAT_STALE_MS) {
        logger.debug('Clearing stale heartbeat — no WS message for', Date.now() - lastWsMessageAt, 'ms')
        currentTask.value = ''
      }
    }, 5000) as unknown as number
  }

  function stopStaleTaskWatcher(): void {
    if (staleTaskTimer !== null) {
      clearInterval(staleTaskTimer)
      staleTaskTimer = null
    }
  }

  // ── Public actions ──────────────────────────────────────────────────────

  /**
   * Start a fresh provisioning run. Resets state and connects WS.
   * Caller is responsible for invoking the actual API to start the
   * backend playbook (this only sets up live tracking).
   */
  function start(): void {
    reset()
    status.value = 'running'
    startedAt.value = Date.now()
    connectWs()
  }

  /**
   * Resync provision state from the backend. Call from any view's
   * onMounted (or app-level setup) to recover state after navigation,
   * tab refresh, or backend restart.
   */
  async function restoreFromBackend(): Promise<void> {
    try {
      const result = await api.getProvisionStatus(0)
      // Backend returns 'idle' if no provision has ever run on this server,
      // OR if a previous run was reset. Either way, leave store at idle.
      if (!result.status || result.status === 'idle') {
        return
      }

      // Replay buffered log lines
      logs.value = result.lines.map((line) => ({
        type: 'info' as const,
        message: line,
      }))
      linesSeen = result.total_lines
      if (result.elapsed_seconds !== undefined) {
        elapsedSeconds.value = Math.round(result.elapsed_seconds)
      }

      if (result.status === 'running') {
        status.value = 'running'
        startedAt.value = startedAt.value ?? Date.now()
        // Reconnect WS for live updates
        connectWs()
      } else if (result.status === 'completed') {
        status.value = 'completed'
        finishedAt.value = Date.now()
      } else if (result.status === 'failed') {
        status.value = 'failed'
        error.value = result.error || 'Provisioning failed'
        finishedAt.value = Date.now()
      }
    } catch (err) {
      logger.error('Failed to restore provision state from backend', err)
    }
  }

  /**
   * Reset store to idle. Disconnects WS/polling. Use after the user
   * acknowledges a completed/failed run and is ready for a new one.
   */
  function reset(): void {
    disconnectWs()
    status.value = 'idle'
    stage.value = ''
    elapsedSeconds.value = 0
    currentTask.value = ''
    currentPhase.value = ''
    completedPhases.value = new Set()
    logs.value = []
    error.value = null
    startedAt.value = null
    finishedAt.value = null
    linesSeen = 0
    lastWsMessageAt = 0
  }

  return {
    // State
    status,
    stage,
    elapsedSeconds,
    currentTask,
    currentPhase,
    completedPhases,
    logs,
    error,
    startedAt,
    finishedAt,
    wsConnected,
    // Computed
    isRunning,
    isComplete,
    isFailed,
    isActive,
    elapsedFormatted,
    // Actions
    start,
    restoreFromBackend,
    reset,
    connectWs,
    disconnectWs,
  }
})
