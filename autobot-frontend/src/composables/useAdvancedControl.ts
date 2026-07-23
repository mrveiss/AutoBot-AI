// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Advanced Control composable (#12162, #12102, #11506 T1 — Stage 1;
 * #12169, #12102 — Stage 2 streaming sessions).
 *
 * Wraps `advancedControlApiClient`'s takeover-management and desktop
 * streaming endpoints for the admin-only Advanced Control panel.
 * Monitoring endpoints are out of scope (see AdvancedControlView.vue
 * placeholder).
 */

import { ref } from 'vue'
import { advancedControlApiClient } from '@/utils/AdvancedControlApiClient'
import type {
  PendingTakeoverRequest,
  ActiveTakeoverSession,
  TakeoverSystemStatus,
  TakeoverCompletionRequest,
  StreamingSession,
  StreamingCapabilities,
  StreamingSessionRequest,
} from '@/utils/AdvancedControlApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useUserStore } from '@/stores/useUserStore'

const logger = createLogger('useAdvancedControl')

export function useAdvancedControl() {
  const userStore = useUserStore()

  const pendingTakeovers = ref<PendingTakeoverRequest[]>([])
  const activeTakeovers = ref<ActiveTakeoverSession[]>([])
  const takeoverStatus = ref<TakeoverSystemStatus | null>(null)
  const streamingSessions = ref<StreamingSession[]>([])
  const streamingCapabilities = ref<StreamingCapabilities | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Loads pending requests, active sessions, and system status in parallel.
   * Partial failures are tolerated per-call — a failed call logs and leaves
   * its slice of state unchanged rather than aborting the whole refresh.
   */
  async function loadTakeovers(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [pendingRes, activeRes, statusRes] = await Promise.all([
        advancedControlApiClient.getPendingTakeovers(),
        advancedControlApiClient.getActiveTakeovers(),
        advancedControlApiClient.getTakeoverStatus(),
      ])

      if (pendingRes.success && pendingRes.data) {
        pendingTakeovers.value = pendingRes.data.pending_requests
      } else if (!pendingRes.success) {
        logger.error('Failed to load pending takeovers:', pendingRes.error)
      }

      if (activeRes.success && activeRes.data) {
        activeTakeovers.value = activeRes.data.active_sessions
      } else if (!activeRes.success) {
        logger.error('Failed to load active takeovers:', activeRes.error)
      }

      if (statusRes.success && statusRes.data) {
        takeoverStatus.value = statusRes.data
      } else if (!statusRes.success) {
        logger.error('Failed to load takeover status:', statusRes.error)
      }

      if (!pendingRes.success && !activeRes.success && !statusRes.success) {
        error.value = pendingRes.error || activeRes.error || statusRes.error || 'Failed to load takeovers'
      }
    } catch (err) {
      logger.error('Failed to load takeovers:', err)
      error.value = err instanceof Error ? err.message : 'Failed to load takeovers'
    } finally {
      loading.value = false
    }
  }

  async function approve(requestId: string): Promise<boolean> {
    error.value = null
    try {
      const humanOperator = userStore.currentUser?.username ?? 'unknown'
      const res = await advancedControlApiClient.approveTakeover(requestId, {
        human_operator: humanOperator,
      })
      if (!res.success) {
        error.value = res.error || 'Failed to approve takeover'
        return false
      }
      await loadTakeovers()
      return true
    } catch (err) {
      logger.error('Failed to approve takeover:', err)
      error.value = err instanceof Error ? err.message : 'Failed to approve takeover'
      return false
    }
  }

  async function pause(sessionId: string): Promise<boolean> {
    error.value = null
    try {
      const res = await advancedControlApiClient.pauseTakeoverSession(sessionId)
      if (!res.success) {
        error.value = res.error || 'Failed to pause session'
        return false
      }
      await loadTakeovers()
      return true
    } catch (err) {
      logger.error('Failed to pause session:', err)
      error.value = err instanceof Error ? err.message : 'Failed to pause session'
      return false
    }
  }

  async function resume(sessionId: string): Promise<boolean> {
    error.value = null
    try {
      const res = await advancedControlApiClient.resumeTakeoverSession(sessionId)
      if (!res.success) {
        error.value = res.error || 'Failed to resume session'
        return false
      }
      await loadTakeovers()
      return true
    } catch (err) {
      logger.error('Failed to resume session:', err)
      error.value = err instanceof Error ? err.message : 'Failed to resume session'
      return false
    }
  }

  async function complete(sessionId: string, completion: TakeoverCompletionRequest = {}): Promise<boolean> {
    error.value = null
    try {
      const res = await advancedControlApiClient.completeTakeoverSession(sessionId, completion)
      if (!res.success) {
        error.value = res.error || 'Failed to complete session'
        return false
      }
      await loadTakeovers()
      return true
    } catch (err) {
      logger.error('Failed to complete session:', err)
      error.value = err instanceof Error ? err.message : 'Failed to complete session'
      return false
    }
  }

  async function action(sessionId: string, actionType: string, actionData: Record<string, unknown> = {}): Promise<boolean> {
    error.value = null
    try {
      const res = await advancedControlApiClient.executeTakeoverAction(sessionId, {
        action_type: actionType,
        action_data: actionData,
      })
      if (!res.success) {
        error.value = res.error || 'Failed to execute action'
        return false
      }
      return true
    } catch (err) {
      logger.error('Failed to execute takeover action:', err)
      error.value = err instanceof Error ? err.message : 'Failed to execute action'
      return false
    }
  }

  /**
   * Loads active streaming sessions and streaming capabilities in parallel.
   * Partial failures are tolerated per-call, mirroring loadTakeovers.
   */
  async function loadStreaming(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [sessionsRes, capsRes] = await Promise.all([
        advancedControlApiClient.listStreamingSessions(),
        advancedControlApiClient.getStreamingCapabilities(),
      ])

      if (sessionsRes.success && sessionsRes.data) {
        streamingSessions.value = sessionsRes.data.sessions
      } else if (!sessionsRes.success) {
        logger.error('Failed to load streaming sessions:', sessionsRes.error)
      }

      if (capsRes.success && capsRes.data) {
        streamingCapabilities.value = capsRes.data
      } else if (!capsRes.success) {
        logger.error('Failed to load streaming capabilities:', capsRes.error)
      }

      if (!sessionsRes.success && !capsRes.success) {
        error.value = sessionsRes.error || capsRes.error || 'Failed to load streaming sessions'
      }
    } catch (err) {
      logger.error('Failed to load streaming sessions:', err)
      error.value = err instanceof Error ? err.message : 'Failed to load streaming sessions'
    } finally {
      loading.value = false
    }
  }

  async function createStreaming(request: StreamingSessionRequest): Promise<boolean> {
    error.value = null
    try {
      const res = await advancedControlApiClient.createStreamingSession(request)
      if (!res.success) {
        error.value = res.error || 'Failed to create streaming session'
        return false
      }
      await loadStreaming()
      return true
    } catch (err) {
      logger.error('Failed to create streaming session:', err)
      error.value = err instanceof Error ? err.message : 'Failed to create streaming session'
      return false
    }
  }

  async function terminateStreaming(sessionId: string): Promise<boolean> {
    error.value = null
    try {
      const res = await advancedControlApiClient.terminateStreamingSession(sessionId)
      if (!res.success) {
        error.value = res.error || 'Failed to terminate streaming session'
        return false
      }
      await loadStreaming()
      return true
    } catch (err) {
      logger.error('Failed to terminate streaming session:', err)
      error.value = err instanceof Error ? err.message : 'Failed to terminate streaming session'
      return false
    }
  }

  return {
    pendingTakeovers,
    activeTakeovers,
    takeoverStatus,
    streamingSessions,
    streamingCapabilities,
    loading,
    error,
    loadTakeovers,
    approve,
    pause,
    resume,
    complete,
    action,
    loadStreaming,
    createStreaming,
    terminateStreaming,
  }
}
