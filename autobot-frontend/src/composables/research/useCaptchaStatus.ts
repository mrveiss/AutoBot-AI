// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Captcha Status Composable
 *
 * Issue #6082: Encapsulates captcha state management, WebSocket events,
 * countdown timer, and API mutations (resolve/skip) for CaptchaNotification.
 */

import { ref, computed, watch, onUnmounted } from 'vue'
// GH#9062: migrated from useGlobalWebSocket — captcha events flow through the
// LiveEventManager (global channel), so useEventBus is the correct subscriber.
import { useEventBus } from '@/composables/useEventBus'
import apiClient from '@/utils/ApiClient'
import { getApiBase, getServiceUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCaptchaStatus')

// ============================================================================
// Types
// ============================================================================

export interface CaptchaEvent {
  captcha_id: string
  url: string
  captcha_type: string
  screenshot?: string
  timeout_seconds: number
  timestamp: string
  message: string
}

// ============================================================================
// Composable
// ============================================================================

export function useCaptchaStatus() {
  const activeCaptcha = ref<CaptchaEvent | null>(null)
  const timeRemaining = ref(0)
  const isSubmitting = ref(false)
  let timerInterval: ReturnType<typeof setInterval> | null = null

  // --------------------------------------------------------------------------
  // Timer
  // --------------------------------------------------------------------------

  function startTimer() {
    stopTimer()
    timerInterval = setInterval(() => {
      if (timeRemaining.value > 0) {
        timeRemaining.value--
      } else {
        activeCaptcha.value = null
        stopTimer()
      }
    }, 1000)
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval)
      timerInterval = null
    }
  }

  // --------------------------------------------------------------------------
  // WebSocket handlers
  // --------------------------------------------------------------------------

  function handleCaptchaDetected(data: CaptchaEvent | { payload: CaptchaEvent }) {
    const eventData = 'payload' in data ? data.payload : data
    activeCaptcha.value = eventData
    timeRemaining.value = eventData.timeout_seconds
    startTimer()
  }

  function handleCaptchaTimeout(data: { captcha_id: string } | { payload: { captcha_id: string } }) {
    const eventData = 'payload' in data ? data.payload : data
    if (activeCaptcha.value?.captcha_id === eventData.captcha_id) {
      activeCaptcha.value = null
      stopTimer()
    }
  }

  function handleCaptchaResolved(data: { captcha_id: string } | { payload: { captcha_id: string } }) {
    const eventData = 'payload' in data ? data.payload : data
    if (activeCaptcha.value?.captcha_id === eventData.captcha_id) {
      activeCaptcha.value = null
      stopTimer()
    }
  }

  // Events arrive as LiveEvent{ event_type, payload }. The handlers already
  // extract payload via the defensive `'payload' in data ? data.payload : data` check.
  const { subscribe } = useEventBus()
  subscribe('global', (event) => {
    if (event.event_type === 'captcha_detected')
      handleCaptchaDetected(event as unknown as { payload: CaptchaEvent })
    else if (event.event_type === 'captcha_timeout')
      handleCaptchaTimeout(event as unknown as { payload: { captcha_id: string } })
    else if (event.event_type === 'captcha_resolved')
      handleCaptchaResolved(event as unknown as { payload: { captcha_id: string } })
  })

  // --------------------------------------------------------------------------
  // Computed
  // --------------------------------------------------------------------------

  const captchaTypeLabel = computed(() => {
    const types: Record<string, string> = {
      recaptcha: 'reCAPTCHA',
      hcaptcha: 'hCaptcha',
      cloudflare: 'Cloudflare Challenge',
      unknown: 'Unknown CAPTCHA'
    }
    return types[activeCaptcha.value?.captcha_type || 'unknown'] || 'CAPTCHA'
  })

  const truncatedUrl = computed(() => {
    const url = activeCaptcha.value?.url || ''
    if (url.length > 60) {
      return url.substring(0, 57) + '...'
    }
    return url
  })

  const progressPercentage = computed(() => {
    if (!activeCaptcha.value) return 0
    return (timeRemaining.value / activeCaptcha.value.timeout_seconds) * 100
  })

  // --------------------------------------------------------------------------
  // Utilities
  // --------------------------------------------------------------------------

  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  /**
   * Open the browser session's VNC view (#17423).
   *
   * The URL comes from SSOT -- `getServiceUrl('vnc')`, built in `ssot-config`
   * from the configured VM host and VNC port -- and from nowhere else. This
   * used to prefer a field on the CAPTCHA payload and fall back to a URL built
   * inline from two VITE_* variables with hardcoded defaults -- a
   * browser-LOCAL address, right only where the browser runs beside the user,
   * and wrong in a way that shows nothing: the window opens and points at
   * nothing. The literals are deliberately not repeated here; a comment that
   * quotes what a guard forbids becomes the guard's next finding (#16750).
   *
   * The payload field is gone as well. `_notify_captcha_detected` publishes on
   * `global`, which every authenticated client may subscribe to, so shipping
   * one tenant's browser session URL there disclosed it to all of them
   * (#17363); nothing populates it now.
   *
   * `getServiceUrl` returns `string | undefined`, so the guard is required and
   * not defensive. Refusing loudly is the point: the previous behaviour opened
   * a window at a URL it had invented.
   */
  function openVnc() {
    const vncUrl = getServiceUrl('vnc')
    if (!vncUrl) {
      logger.error('No VNC URL configured; cannot open the CAPTCHA browser view')
      return
    }
    window.open(vncUrl, '_blank', 'noopener,noreferrer')
  }

  // --------------------------------------------------------------------------
  // Mutations
  // --------------------------------------------------------------------------

  async function markSolved() {
    if (!activeCaptcha.value || isSubmitting.value) return

    isSubmitting.value = true
    try {
      await apiClient.post<unknown>(`${getApiBase()}/captcha/${activeCaptcha.value.captcha_id}/resolve`)
      activeCaptcha.value = null
      stopTimer()
    } catch (error) {
      logger.error('Failed to mark CAPTCHA as solved:', error)
    } finally {
      isSubmitting.value = false
    }
  }

  async function skipCaptcha() {
    if (!activeCaptcha.value || isSubmitting.value) return

    isSubmitting.value = true
    try {
      await apiClient.post<unknown>(`${getApiBase()}/captcha/${activeCaptcha.value.captcha_id}/skip`)
      activeCaptcha.value = null
      stopTimer()
    } catch (error) {
      logger.error('Failed to skip CAPTCHA:', error)
    } finally {
      isSubmitting.value = false
    }
  }

  // --------------------------------------------------------------------------
  // Lifecycle
  // --------------------------------------------------------------------------

  watch(activeCaptcha, (newVal: CaptchaEvent | null) => {
    if (!newVal) {
      stopTimer()
    }
  })

  onUnmounted(() => {
    stopTimer()
  })

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    activeCaptcha,
    timeRemaining,
    isSubmitting,
    captchaTypeLabel,
    truncatedUrl,
    progressPercentage,
    formatTime,
    openVnc,
    markSolved,
    skipCaptcha,
  }
}
