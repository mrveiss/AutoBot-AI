// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Advanced Control composable (#12162, #12102, #11506 T1 — Stage 1;
 * #12169, #12102 — Stage 2 streaming sessions; #12173, #12102 — Stage 3
 * system monitoring + emergency-stop).
 *
 * Wraps `advancedControlApiClient`'s takeover-management, desktop
 * streaming, and system-monitoring endpoints for the admin-only Advanced
 * Control panel.
 */

import { ref } from 'vue'
import { isHttpError } from '@autobot/ui'
import apiClient from '@/utils/ApiClient'
import { getMonitoringWebSocketUrl as buildMonitoringWebSocketUrl } from '@/utils/advancedControlWs'
import type {
  PendingTakeoverRequest,
  ActiveTakeoverSession,
  TakeoverSystemStatus,
  TakeoverCompletionRequest,
  StreamingSession,
  StreamingCapabilities,
  StreamingSessionRequest,
  TakeoverRequest,
  SystemMonitoringResponse,
  SystemHealthResponse,
} from '@/types/advancedControl'
import type { components } from '@/types/generated/api'
import { createLogger } from '@/utils/debugUtils'
import { useUserStore } from '@/stores/useUserStore'

const logger = createLogger('useAdvancedControl')

type Schemas = components['schemas']

/** The backend's own `detail` when it sent one, else the error text, else the fallback. */
function failureText(err: unknown, fallback: string): string {
  if (isHttpError(err) && err.detail) return err.detail
  return err instanceof Error && err.message ? err.message : fallback
}

type Settled<T> = { ok: true; value: T } | { ok: false; message: string }

/** One call's outcome as data, so a parallel load can tolerate a partial failure. */
async function settle<T>(request: Promise<T>, fallback: string): Promise<Settled<T>> {
  try {
    return { ok: true, value: await request }
  } catch (err) {
    return { ok: false, message: failureText(err, fallback) }
  }
}

export function useAdvancedControl() {
  const userStore = useUserStore()

  const pendingTakeovers = ref<PendingTakeoverRequest[]>([])
  const activeTakeovers = ref<ActiveTakeoverSession[]>([])
  const takeoverStatus = ref<TakeoverSystemStatus | null>(null)
  const streamingSessions = ref<StreamingSession[]>([])
  const streamingCapabilities = ref<StreamingCapabilities | null>(null)
  const systemStatus = ref<SystemMonitoringResponse | null>(null)
  const systemHealth = ref<SystemHealthResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Run one mutation. Resolves true on success after `refresh` (when given); a failure lands in
   * `error` (the backend's `detail` when it sent one) and resolves false, never throws.
   */
  async function mutate(request: () => Promise<unknown>, fallback: string, refresh?: () => Promise<void>): Promise<boolean> {
    error.value = null
    try {
      await request()
      if (refresh) await refresh()
      return true
    } catch (err) {
      logger.error(`${fallback}:`, err)
      error.value = failureText(err, fallback)
      return false
    }
  }

  /** Tolerate a per-call failure (log, leave that slice unchanged); only an all-failed load sets `error`. */
  function reportLoad(results: Settled<unknown>[], labels: string[], fallback: string): void {
    results.forEach((r, i) => {
      if (!r.ok) logger.error(`Failed to load ${labels[i]}:`, r.message)
    })
    if (results.every((r) => !r.ok)) {
      error.value = results.map((r) => (r.ok ? '' : r.message)).find(Boolean) || fallback
    }
  }

  /**
   * Loads pending requests, active sessions, and system status in parallel.
   * Partial failures are tolerated per-call — a failed call logs and leaves
   * its slice of state unchanged rather than aborting the whole refresh.
   */
  async function loadTakeovers(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [pending, active, status] = await Promise.all([
        settle(apiClient.call('get', '/api/advanced-control/takeover/pending'), 'Failed to load pending takeovers'),
        settle(apiClient.call('get', '/api/advanced-control/takeover/active'), 'Failed to load active takeovers'),
        settle(apiClient.call('get', '/api/advanced-control/takeover/status'), 'Failed to load takeover status'),
      ])
      if (pending.ok) pendingTakeovers.value = pending.value.pending_requests as PendingTakeoverRequest[]
      if (active.ok) activeTakeovers.value = active.value.active_sessions as ActiveTakeoverSession[]
      if (status.ok) takeoverStatus.value = status.value as unknown as TakeoverSystemStatus
      reportLoad([pending, active, status], ['pending takeovers', 'active takeovers', 'takeover status'], 'Failed to load takeovers')
    } finally {
      loading.value = false
    }
  }

  async function approve(requestId: string): Promise<boolean> {
    const humanOperator = userStore.currentUser?.username ?? 'unknown'
    return mutate(
      () =>
        apiClient.call('post', '/api/advanced-control/takeover/{request_id}/approve', {
          path: { request_id: requestId },
          body: { human_operator: humanOperator },
        }),
      'Failed to approve takeover',
      loadTakeovers
    )
  }

  async function pause(sessionId: string): Promise<boolean> {
    return mutate(
      () => apiClient.call('post', '/api/advanced-control/takeover/sessions/{session_id}/pause', { path: { session_id: sessionId } }),
      'Failed to pause session',
      loadTakeovers
    )
  }

  async function resume(sessionId: string): Promise<boolean> {
    return mutate(
      () => apiClient.call('post', '/api/advanced-control/takeover/sessions/{session_id}/resume', { path: { session_id: sessionId } }),
      'Failed to resume session',
      loadTakeovers
    )
  }

  async function complete(sessionId: string, completion: TakeoverCompletionRequest = {}): Promise<boolean> {
    return mutate(
      () =>
        apiClient.call('post', '/api/advanced-control/takeover/sessions/{session_id}/complete', {
          path: { session_id: sessionId },
          body: completion,
        }),
      'Failed to complete session',
      loadTakeovers
    )
  }

  /** The capability summary (name, version, features, endpoints) of the Advanced Control API. */
  function getControlInfo() {
    return apiClient.call('get', '/api/advanced-control/')
  }

  async function requestTakeover(request: TakeoverRequest): Promise<boolean> {
    return mutate(
      () => apiClient.call('post', '/api/advanced-control/takeover/request', { body: request as Schemas['TakeoverRequest'] }),
      'Failed to request takeover',
      loadTakeovers
    )
  }

  async function action(sessionId: string, actionType: string, actionData: Record<string, unknown> = {}): Promise<boolean> {
    return mutate(
      () =>
        apiClient.call('post', '/api/advanced-control/takeover/sessions/{session_id}/action', {
          path: { session_id: sessionId },
          body: { action_type: actionType, action_data: actionData },
        }),
      'Failed to execute action'
    )
  }

  /**
   * Loads active streaming sessions and streaming capabilities in parallel.
   * Partial failures are tolerated per-call, mirroring loadTakeovers.
   */
  async function loadStreaming(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [sessions, caps] = await Promise.all([
        settle(apiClient.call('get', '/api/advanced-control/streaming/sessions'), 'Failed to load streaming sessions'),
        settle(apiClient.call('get', '/api/advanced-control/streaming/capabilities'), 'Failed to load streaming capabilities'),
      ])
      if (sessions.ok) streamingSessions.value = sessions.value.sessions as StreamingSession[]
      if (caps.ok) streamingCapabilities.value = caps.value as unknown as StreamingCapabilities
      reportLoad([sessions, caps], ['streaming sessions', 'streaming capabilities'], 'Failed to load streaming sessions')
    } finally {
      loading.value = false
    }
  }

  async function createStreaming(request: StreamingSessionRequest): Promise<boolean> {
    // The contract marks the defaulted resolution and depth required; the backend fills a missing one.
    const body = request as { user_id: string; resolution: string; depth: number }
    return mutate(
      () => apiClient.call('post', '/api/advanced-control/streaming/create', { body }),
      'Failed to create streaming session',
      loadStreaming
    )
  }

  async function terminateStreaming(sessionId: string): Promise<boolean> {
    return mutate(
      () => apiClient.call('delete', '/api/advanced-control/streaming/{session_id}', { path: { session_id: sessionId } }),
      'Failed to terminate streaming session',
      loadStreaming
    )
  }

  /**
   * Loads comprehensive system status and the quick health check in
   * parallel. Partial failures are tolerated per-call, mirroring
   * loadTakeovers/loadStreaming.
   */
  async function loadMonitoring(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [status, health] = await Promise.all([
        settle(apiClient.call('get', '/api/advanced-control/system/status'), 'Failed to load system status'),
        settle(apiClient.call('get', '/api/advanced-control/system/health'), 'Failed to load system health'),
      ])
      if (status.ok) systemStatus.value = status.value as unknown as SystemMonitoringResponse
      if (health.ok) systemHealth.value = health.value as unknown as SystemHealthResponse
      reportLoad([status, health], ['system status', 'system health'], 'Failed to load system monitoring data')
    } finally {
      loading.value = false
    }
  }

  /**
   * Triggers an emergency stop of all autonomous operations (a
   * CRITICAL-priority, auto-approved takeover request). Reloads monitoring
   * data on success so the resulting takeover shows up immediately.
   */
  async function emergencyStop(): Promise<boolean> {
    return mutate(
      () => apiClient.call('post', '/api/advanced-control/system/emergency-stop'),
      'Failed to activate emergency stop',
      loadMonitoring
    )
  }

  /** Passthrough to the monitoring WebSocket URL builder. */
  function getMonitoringWebSocketUrl(): string {
    return buildMonitoringWebSocketUrl()
  }

  return {
    pendingTakeovers,
    activeTakeovers,
    takeoverStatus,
    streamingSessions,
    streamingCapabilities,
    systemStatus,
    systemHealth,
    loading,
    error,
    loadTakeovers,
    getControlInfo,
    requestTakeover,
    approve,
    pause,
    resume,
    complete,
    action,
    loadStreaming,
    createStreaming,
    terminateStreaming,
    loadMonitoring,
    emergencyStop,
    getMonitoringWebSocketUrl,
  }
}
