// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, readonly } from 'vue'
import apiClient from '@/utils/ApiClient'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('usePushNotifications')

export type PushPermissionState = 'default' | 'granted' | 'denied' | 'unsupported'

// Module-level singleton — subscription state survives navigation
const _subscribed = ref(false)
const _permissionState = ref<PushPermissionState>('default')
const _loading = ref(false)
const _error = ref<string | null>(null)

function _getPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'Notification' in window &&
    'serviceWorker' in navigator &&
    'PushManager' in window
  )
}

function _urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  return Uint8Array.from(Array.from(rawData).map((c) => c.charCodeAt(0)))
}

async function _getVapidPublicKey(): Promise<string> {
  const data = await apiClient.get<{ vapidPublicKey: string }>(
    `${getApiBase()}/push/vapid-public-key`,
  )
  return data.vapidPublicKey
}

// Sync subscription state once the SW is ready (fire-and-forget, best-effort)
if (_getPushSupported()) {
  _permissionState.value = Notification.permission as PushPermissionState
  navigator.serviceWorker.ready
    .then((reg) => reg.pushManager.getSubscription())
    .then((sub) => {
      _subscribed.value = sub !== null
    })
    .catch(() => {})
}

/**
 * Composable for Web Push Notification lifecycle (GH#4459).
 *
 * - requestPermission() asks the user for Notification permission.
 * - subscribe() fetches VAPID key, creates PushSubscription, POSTs to backend.
 * - unsubscribe() removes subscription locally and DELETEs from backend.
 * - State is module-level so it survives navigation without re-requesting.
 */
export function usePushNotifications() {
  const isSupported = _getPushSupported()

  if (!isSupported) {
    _permissionState.value = 'unsupported'
  }

  async function requestPermission(): Promise<PushPermissionState> {
    if (!isSupported) {
      _permissionState.value = 'unsupported'
      return 'unsupported'
    }
    const result = await Notification.requestPermission()
    _permissionState.value = result as PushPermissionState
    return result as PushPermissionState
  }

  async function subscribe(): Promise<void> {
    if (!isSupported) {
      _error.value = 'Push notifications are not supported in this browser.'
      return
    }
    if (_loading.value) return

    _loading.value = true
    _error.value = null

    try {
      let permission: PushPermissionState = Notification.permission as PushPermissionState
      if (permission === 'default') {
        permission = await requestPermission()
      }
      if (permission !== 'granted') {
        _error.value =
          permission === 'denied'
            ? 'Notification permission denied. Enable it in your browser settings.'
            : 'Notification permission was not granted.'
        return
      }

      const reg = await navigator.serviceWorker.ready
      const vapidPublicKey = await _getVapidPublicKey()
      const applicationServerKey = _urlBase64ToUint8Array(vapidPublicKey)

      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey as BufferSource,
      })

      const json = subscription.toJSON()
      const keys = json.keys as { p256dh?: string; auth?: string } | undefined

      await apiClient.post(`${getApiBase()}/push/subscribe`, {
        endpoint: json.endpoint,
        p256dh: keys?.p256dh ?? '',
        auth: keys?.auth ?? '',
      })

      _subscribed.value = true
      logger.info('Push subscription created')
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Push subscribe failed:', msg)
      _error.value = `Could not enable push notifications: ${msg}`
    } finally {
      _loading.value = false
    }
  }

  async function unsubscribe(): Promise<void> {
    if (!isSupported || _loading.value) return

    _loading.value = true
    _error.value = null

    try {
      const reg = await navigator.serviceWorker.ready
      const subscription = await reg.pushManager.getSubscription()

      if (subscription) {
        // DELETE with body — use fetchWithAuth since ApiClient.delete has no body support
        const base = getApiBase()
        const response = await fetchWithAuth(`${location.origin}${base}/push/unsubscribe`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ endpoint: subscription.endpoint }),
        })
        if (!response.ok && response.status !== 404) {
          throw new Error(`HTTP ${response.status}`)
        }
        await subscription.unsubscribe()
      }

      _subscribed.value = false
      logger.info('Push subscription removed')
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Push unsubscribe failed:', msg)
      _error.value = `Could not disable push notifications: ${msg}`
    } finally {
      _loading.value = false
    }
  }

  return {
    subscribed: readonly(_subscribed),
    permissionState: readonly(_permissionState),
    loading: readonly(_loading),
    error: readonly(_error),
    isSupported,
    requestPermission,
    subscribe,
    unsubscribe,
  }
}
