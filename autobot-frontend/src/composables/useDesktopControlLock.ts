// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Desktop control-lock composable (Issue #12002, #11506 T1).
 *
 * Wraps the /vnc-proxy/{vncType}/control/{acquire,release,status} endpoints
 * so a human can explicitly take over (and hand back) input control of the
 * agent-driven desktop session, muting agent actuation while held.
 *
 * The lock has a server-side idle-TTL (AUTOBOT_DESKTOP_CONTROL_LOCK_TTL_SECONDS,
 * default 120s) -- while `humanActive` is true and owned by the current user,
 * this composable sends a periodic re-acquire "heartbeat" to keep the lock
 * alive, so navigating away/closing the tab lets it expire naturally rather
 * than muting the agent forever.
 */

import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useUserStore } from '@/stores/useUserStore'

const logger = createLogger('useDesktopControlLock')

// Heartbeat cadence for the frontend re-acquire poll -- a UI polling
// interval (like the 10s connection-status poll in DesktopInterface.vue),
// not a backend cache/TTL value, so it is a local constant rather than an
// env-driven one. Kept comfortably below the backend's default idle-TTL.
const HEARTBEAT_INTERVAL_MS = 30000

export interface DesktopControlLockState {
  success: boolean
  session_id: string
  owner: string | null
  human_active: boolean
  message: string
}

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return fallback
}

export function useDesktopControlLock(vncType: string = 'desktop', sessionId: string = 'default') {
  const userStore = useUserStore()

  const owner = ref<string | null>(null)
  const humanActive = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isMine = computed(() => {
    const username = userStore.currentUser?.username
    return humanActive.value && !!username && owner.value === username
  })

  const basePath = `/vnc-proxy/${vncType}/control`

  async function refreshStatus(): Promise<DesktopControlLockState | null> {
    try {
      const result = await ApiClient.get<DesktopControlLockState>(
        `${basePath}/status?session_id=${encodeURIComponent(sessionId)}`
      )
      owner.value = result.owner
      humanActive.value = result.human_active
      return result
    } catch (err: unknown) {
      logger.error('Failed to fetch control-lock status:', err)
      error.value = extractErrorMessage(err, 'Failed to fetch control status')
      return null
    }
  }

  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  function stopHeartbeat(): void {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function startHeartbeat(): void {
    stopHeartbeat()
    // Periodic re-acquire refreshes the Redis TTL; does NOT fire immediately
    // (the caller just acquired), only on subsequent ticks.
    heartbeatTimer = setInterval(() => {
      void acquire()
    }, HEARTBEAT_INTERVAL_MS)
  }

  // Auto-cleanup when the owning component/effect scope disposes, mirroring
  // usePollingJob's guard (no-op outside an active effect scope).
  if (getCurrentScope()) {
    onScopeDispose(stopHeartbeat)
  }

  async function acquire(): Promise<DesktopControlLockState | null> {
    error.value = null
    loading.value = true
    try {
      const result = await ApiClient.post<DesktopControlLockState>(`${basePath}/acquire`, {
        session_id: sessionId
      })
      owner.value = result.owner
      humanActive.value = result.human_active
      if (!result.success) {
        error.value = result.message
      }
      return result
    } catch (err: unknown) {
      logger.error('Failed to acquire desktop control:', err)
      error.value = extractErrorMessage(err, 'Failed to take control')
      return null
    } finally {
      loading.value = false
    }
  }

  async function takeControl(): Promise<DesktopControlLockState | null> {
    const result = await acquire()
    if (result?.success) {
      startHeartbeat()
    }
    return result
  }

  async function releaseControl(): Promise<DesktopControlLockState | null> {
    error.value = null
    loading.value = true
    stopHeartbeat()
    try {
      const result = await ApiClient.post<DesktopControlLockState>(`${basePath}/release`, {
        session_id: sessionId
      })
      owner.value = result.owner
      humanActive.value = result.human_active
      if (!result.success) {
        error.value = result.message
      }
      return result
    } catch (err: unknown) {
      logger.error('Failed to release desktop control:', err)
      error.value = extractErrorMessage(err, 'Failed to release control')
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    owner,
    humanActive,
    isMine,
    loading,
    error,
    refreshStatus,
    takeControl,
    releaseControl
  }
}
