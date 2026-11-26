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

import { computed, getCurrentScope, onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage } from '@/utils/errorExtract'
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
  owner?: string | null
  human_active: boolean
  message: string
}

/**
 * @param hostId the selected /secrets host id; it is the lock key (#22145).
 */
export function useDesktopControlLock(hostId: MaybeRefOrGetter<string | null | undefined>, vncType: string = 'desktop') {
  // Read on every call: switching the host retargets the lock (the state below is reset on a switch).
  const currentHostId = () => toValue(hostId) ?? ''
  const userStore = useUserStore()

  const owner = ref<string | null>(null)
  const humanActive = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isMine = computed(() => {
    const username = userStore.currentUser?.username
    return humanActive.value && !!username && owner.value === username
  })

  // Typed contract keys: ApiClient.call applies the configured API base (getApiBase) itself.
  const path = { vnc_type: vncType }

  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  // Bumped on every host switch: a response that began under an older generation (even for the same host,
  // A -> B -> A) is stale and must not write state, start a heartbeat or leave a lock held.
  let generation = 0

  function stopHeartbeat(): void {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function startHeartbeat(): void {
    stopHeartbeat()
    // Periodic re-acquire refreshes the Redis TTL; does NOT fire immediately
    // (the caller just acquired/confirmed ownership), only on subsequent
    // ticks. `silent: true` so this background refresh never toggles
    // `loading` (would otherwise flicker/disable the Take/Release button
    // every 30s -- #12002 review nit).
    heartbeatTimer = setInterval(() => {
      void acquire({ silent: true })
    }, HEARTBEAT_INTERVAL_MS)
  }

  // Auto-cleanup when the owning component/effect scope disposes, mirroring
  // usePollingJob's guard (no-op outside an active effect scope).
  if (getCurrentScope()) {
    onScopeDispose(stopHeartbeat)
  }

  // A different host is a different lock: drop the old host's state and heartbeat, then read the new one.
  // If the user held the OLD host's lock, hand it back to the agent there (using the old id) first.
  watch(currentHostId, async (_next, previous) => {
    generation += 1
    const heldOld = !!previous && isMine.value
    stopHeartbeat()
    owner.value = null
    humanActive.value = false
    if (heldOld) await releaseHost(previous)
    void refreshStatus()
  })

  async function releaseHost(hostId: string): Promise<void> {
    try {
      await ApiClient.call('post', '/api/vnc-proxy/{vnc_type}/control/release', {
        path,
        body: { session_id: hostId }
      })
    } catch (err: unknown) {
      logger.warn('Could not release the previous host control lock:', err)
    }
  }

  async function refreshStatus(): Promise<DesktopControlLockState | null> {
    const host = currentHostId()
    if (!host) return null
    const startedIn = generation
    try {
      const result: DesktopControlLockState = await ApiClient.call(
        'get',
        '/api/vnc-proxy/{vnc_type}/control/status',
        { path, query: { session_id: host } }
      )
      if (startedIn !== generation) return null // the selection changed while this was in flight
      owner.value = result.owner ?? null
      humanActive.value = result.human_active
      // Resume the heartbeat if we discover (e.g. after a page reload/remount)
      // that we already hold the lock -- otherwise its idle-TTL silently
      // expires while the UI still shows "You have control" (#12002 review fix).
      if (result.human_active && result.owner === userStore.currentUser?.username) {
        startHeartbeat()
      } else {
        stopHeartbeat()
      }
      return result
    } catch (err: unknown) {
      logger.error('Failed to fetch control-lock status:', err)
      if (startedIn !== generation) return null
      error.value = extractErrorMessage(err, 'Failed to fetch control status')
      return null
    }
  }

  async function acquire(options: { silent?: boolean } = {}): Promise<DesktopControlLockState | null> {
    const { silent = false } = options
    error.value = null
    const host = currentHostId()
    if (!host) return null
    const startedIn = generation
    if (!silent) {
      loading.value = true
    }
    try {
      const result: DesktopControlLockState = await ApiClient.call(
        'post',
        '/api/vnc-proxy/{vnc_type}/control/acquire',
        { path, body: { session_id: host } }
      )
      if (startedIn !== generation) {
        // The server granted a lock the user has since navigated away from: hand it back on THAT host.
        if (result.success) await releaseHost(host)
        return null
      }
      owner.value = result.owner ?? null
      humanActive.value = result.human_active
      if (!result.success) {
        error.value = result.message
      }
      return result
    } catch (err: unknown) {
      if (silent) {
        logger.warn('Silent heartbeat re-acquire failed:', err)
      } else {
        logger.error('Failed to acquire desktop control:', err)
      }
      if (startedIn !== generation) return null
      error.value = extractErrorMessage(err, 'Failed to take control')
      return null
    } finally {
      if (!silent) {
        loading.value = false
      }
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
    const host = currentHostId()
    if (!host) return null
    const startedIn = generation
    loading.value = true
    stopHeartbeat()
    try {
      const result: DesktopControlLockState = await ApiClient.call(
        'post',
        '/api/vnc-proxy/{vnc_type}/control/release',
        { path, body: { session_id: host } }
      )
      if (startedIn !== generation) return null
      owner.value = result.owner ?? null
      humanActive.value = result.human_active
      if (!result.success) {
        error.value = result.message
      }
      return result
    } catch (err: unknown) {
      logger.error('Failed to release desktop control:', err)
      if (startedIn !== generation) return null
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
