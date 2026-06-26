// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Network Status Composable
 *
 * Issue #3275: Offline mode — core functionality available without network connectivity
 *
 * Detects network availability within 5 seconds and exposes reactive state.
 * Uses Navigator.onLine as fast initial signal, then probes the backend health
 * endpoint for confirmation (handles captive portals and VPN splits).
 *
 * "Online" means the browser can reach the backend. It says nothing about whether
 * the backend itself can reach external services — server-side features like
 * web research and cloud LLM calls run from the backend's outbound connectivity
 * and are NOT gated by this composable.
 *
 * FeatureConnectivity tiers (#6566):
 *   - 'local-only'       — works without browser→backend connectivity at all
 *                          (purely client-rendered views; no API calls).
 *   - 'requires-network' — needs the browser to reach the backend; disable
 *                          submit/CTA buttons when offline. Reserve for features
 *                          that genuinely cannot be queued (e.g., realtime
 *                          streams). Do NOT use for backend-executed features
 *                          like web research, RAG, or cloud LLMs.
 *   - 'prefers-network'  — works offline via cache/queue; show staleness hints.
 */

import { ref, readonly, onMounted, onScopeDispose, getCurrentInstance, getCurrentScope } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useNetworkStatus')

export type FeatureConnectivity = 'local-only' | 'requires-network' | 'prefers-network'

export interface NetworkStatus {
  isOnline: boolean
  /** True while the initial probe is still in-flight */
  isChecking: boolean
  /** Timestamp of last successful probe (ms since epoch), null if never succeeded */
  lastOnlineAt: number | null
}

// Module-level singleton so all callers share one probe loop
const _isOnline = ref<boolean>(typeof navigator !== 'undefined' ? navigator.onLine : true)
const _isChecking = ref<boolean>(true)
const _lastOnlineAt = ref<number | null>(null)

let _probeTimer: ReturnType<typeof setInterval> | null = null
let _refCount = 0

// BUG8: a single slow/transient probe used to flip the whole app to "offline".
// Require N consecutive failures before declaring offline so one timeout while
// the backend is briefly busy doesn't mislabel a clearly-connected app.
const OFFLINE_FAILURE_THRESHOLD = 2
let _consecutiveFailures = 0

/** Mark a failed probe; only transition to offline after the threshold is hit. */
function _registerProbeFailure(): void {
  _consecutiveFailures++
  if (_consecutiveFailures >= OFFLINE_FAILURE_THRESHOLD && _isOnline.value) {
    // Log only on the actual online → offline transition (not every cycle).
    logger.info(`Network probe failed ${_consecutiveFailures}x — marking offline`)
    _isOnline.value = false
  }
}

/** Probe the backend health endpoint — avoids trusting captive-portal "connected" state */
async function _probe(): Promise<void> {
  const url = `${getApiBase()}/health`
  try {
    const res = await fetch(url, {
      method: 'HEAD',
      cache: 'no-store',
      signal: AbortSignal.timeout(4500), // must resolve within 5 s window
    })
    const online = res.ok || res.status < 500
    if (online) {
      _consecutiveFailures = 0
      if (!_isOnline.value) {
        logger.info('Network status changed: online')
      }
      _isOnline.value = true
      _lastOnlineAt.value = Date.now()
    } else {
      _registerProbeFailure()
    }
  } catch {
    _registerProbeFailure()
  } finally {
    _isChecking.value = false
  }
}

function _startProbeLoop(): void {
  _probe()
  _probeTimer = setInterval(_probe, 30_000)
}

function _stopProbeLoop(): void {
  if (_probeTimer !== null) {
    clearInterval(_probeTimer)
    _probeTimer = null
  }
}

function _handleOnline(): void {
  logger.info('Browser online event — scheduling probe')
  _isChecking.value = true
  _probe()
}

function _handleOffline(): void {
  logger.info('Browser offline event')
  _isOnline.value = false
  _isChecking.value = false
}

/**
 * Returns whether a feature is available in the current network state.
 *
 * @param connectivity - Feature connectivity requirement
 * @returns true if the feature can be used right now
 */
export function isFeatureAvailable(
  connectivity: FeatureConnectivity,
  online: boolean,
): boolean {
  if (connectivity === 'local-only') return true
  if (connectivity === 'requires-network') return online
  // 'prefers-network' — available offline but callers may show a warning
  return true
}

export function useNetworkStatus() {
  // Refcount must stay balanced: only register both hooks when we have a
  // component instance (so onMounted runs), then tie cleanup to scope-dispose.
  if (getCurrentInstance()) {
    onMounted(() => {
      _refCount++
      if (_refCount === 1) {
        window.addEventListener('online', _handleOnline)
        window.addEventListener('offline', _handleOffline)
        _startProbeLoop()
      }
    })

    if (getCurrentScope()) {
      onScopeDispose(() => {
        _refCount--
        if (_refCount === 0) {
          window.removeEventListener('online', _handleOnline)
          window.removeEventListener('offline', _handleOffline)
          _stopProbeLoop()
        }
      })
    }
  }

  return {
    isOnline: readonly(_isOnline),
    isChecking: readonly(_isChecking),
    lastOnlineAt: readonly(_lastOnlineAt),
    isFeatureAvailable: (connectivity: FeatureConnectivity) =>
      isFeatureAvailable(connectivity, _isOnline.value),
  }
}
