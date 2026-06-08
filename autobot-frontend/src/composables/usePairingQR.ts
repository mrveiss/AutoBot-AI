// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * usePairingQR Composable (MVA-2993)
 *
 * Handles QR code pairing lifecycle for mobile device pairing.
 * - Fetches challenge token from backend (GET /api/devices/pair-qr)
 * - Generates QR code data URL using the `qrcode` package
 * - Manages countdown timer (5-minute TTL)
 * - Detects device pairing completion via polling (GET /api/devices)
 */

import { ref, computed, onUnmounted } from 'vue'
import QRCode from 'qrcode'
import { createLogger } from '@/utils/debugUtils'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('usePairingQR')

interface QRChallengeResponse {
  challenge_token: string
  expires_in_seconds: number
}

interface DeviceResponse {
  id: string
  device_name: string
  platform: string
  last_seen_at: string | null
  created_at: string
}

interface DeviceListResponse {
  devices: DeviceResponse[]
}

export function usePairingQR() {
  const challengeToken = ref<string | null>(null)
  const qrDataUrl = ref<string | null>(null)
  const expiresInSeconds = ref<number>(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const isPaired = ref(false)

  const isExpired = computed(() => expiresInSeconds.value <= 0)
  const formattedTime = computed(() => {
    const m = Math.floor(expiresInSeconds.value / 60)
    const s = expiresInSeconds.value % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  })

  let countdownInterval: number | null = null
  let pairingCheckInterval: number | null = null

  async function fetchChallenge() {
    stopCountdown()
    stopPairingCheck()
    loading.value = true
    error.value = null
    isPaired.value = false
    qrDataUrl.value = null

    try {
      const response: QRChallengeResponse = await apiClient.get(
        `${getApiBase()}/devices/pair-qr`
      )
      challengeToken.value = response.challenge_token
      expiresInSeconds.value = response.expires_in_seconds

      const qrUrl = `autobot://pair?token=${response.challenge_token}`
      qrDataUrl.value = await QRCode.toDataURL(qrUrl, {
        width: 300,
        margin: 2,
        color: { dark: '#000000', light: '#FFFFFF' },
      })

      startCountdown()
      startPairingCheck()
      logger.info('QR challenge fetched successfully')
    } catch (err) {
      error.value = 'Failed to generate QR code. Please try again.'
      logger.error('Failed to fetch QR challenge:', err)
    } finally {
      loading.value = false
    }
  }

  function startCountdown() {
    countdownInterval = window.setInterval(() => {
      if (expiresInSeconds.value > 0) {
        expiresInSeconds.value--
      } else {
        stopCountdown()
      }
    }, 1000)
  }

  function stopCountdown() {
    if (countdownInterval !== null) {
      clearInterval(countdownInterval)
      countdownInterval = null
    }
  }

  function startPairingCheck() {
    pairingCheckInterval = window.setInterval(async () => {
      try {
        const data: DeviceListResponse = await apiClient.get(
          `${getApiBase()}/devices`
        )
        if (!data.devices?.length) return

        const recentDevice = data.devices.find((d) => {
          const age = Date.now() - new Date(d.created_at).getTime()
          return age < 10_000
        })

        if (recentDevice) {
          isPaired.value = true
          stopPairingCheck()
          stopCountdown()
          logger.info('Device paired: %s (%s)', recentDevice.device_name, recentDevice.id)
        }
      } catch (err) {
        logger.warn('Pairing check failed:', err)
      }
    }, 2000)
  }

  function stopPairingCheck() {
    if (pairingCheckInterval !== null) {
      clearInterval(pairingCheckInterval)
      pairingCheckInterval = null
    }
  }

  function reset() {
    stopCountdown()
    stopPairingCheck()
    challengeToken.value = null
    qrDataUrl.value = null
    expiresInSeconds.value = 0
    error.value = null
    isPaired.value = false
  }

  onUnmounted(() => {
    stopCountdown()
    stopPairingCheck()
  })

  return {
    challengeToken,
    qrDataUrl,
    expiresInSeconds,
    loading,
    error,
    isPaired,
    isExpired,
    formattedTime,
    fetchChallenge,
    reset,
  }
}
