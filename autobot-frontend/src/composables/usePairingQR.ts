/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 *
 * usePairingQR Composable (MVA-3003)
 *
 * Handles QR code pairing lifecycle for mobile device pairing.
 * - Fetches challenge token from backend
 * - Generates QR code data URL
 * - Manages countdown timer
 * - Detects device pairing completion via polling
 */

import { ref, computed, onUnmounted } from 'vue'
import QRCode from 'qrcode'
import { createLogger } from '@/utils/debugUtils'
import { getApiClient } from '@/utils/ApiClient'

interface QRChallengeResponse {
  challenge_token: string
  expires_in_seconds: number
}

export function usePairingQR() {
  const logger = createLogger('usePairingQR')
  const apiClient = getApiClient()

  // State
  const challengeToken = ref<string | null>(null)
  const qrDataUrl = ref<string | null>(null)
  const expiresInSeconds = ref<number>(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const isPaired = ref(false)

  // Computed
  const isExpired = computed(() => expiresInSeconds.value <= 0)
  const minutesRemaining = computed(() => Math.floor(expiresInSeconds.value / 60))
  const secondsRemaining = computed(() => expiresInSeconds.value % 60)
  const formattedTime = computed(() =>
    `${minutesRemaining.value}:${secondsRemaining.value.toString().padStart(2, '0')}`
  )

  // Timers
  let countdownInterval: number | null = null
  let pairingCheckInterval: number | null = null

  // Methods
  async function fetchChallenge() {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.get('/devices/pair-qr')
      challengeToken.value = response.challenge_token
      expiresInSeconds.value = response.expires_in_seconds

      // Generate QR code
      const qrUrl = `autobot://pair?token=${response.challenge_token}`
      qrDataUrl.value = await QRCode.toDataURL(qrUrl, {
        width: 300,
        margin: 2,
        color: {
          dark: '#000000',
          light: '#FFFFFF'
        }
      })

      // Start countdown
      startCountdown()

      // Start polling for pairing completion
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
    stopCountdown()
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

  async function startPairingCheck() {
    stopPairingCheck()
    // Poll every 2 seconds to check if device was paired
    pairingCheckInterval = window.setInterval(async () => {
      try {
        const devices = await apiClient.get('/devices')
        // If device count increased, pairing succeeded
        // (More robust: check for device with matching token, but backend doesn't expose that)
        // For now, trust that any new device during the challenge window is the paired one
        if (devices.devices && devices.devices.length > 0) {
          // Check if any device was created in the last 10 seconds
          const recentDevice = devices.devices.find((d: any) => {
            const createdAt = new Date(d.created_at)
            const now = new Date()
            return (now.getTime() - createdAt.getTime()) < 10000 // 10 seconds
          })

          if (recentDevice) {
            isPaired.value = true
            stopPairingCheck()
            stopCountdown()
            logger.info('Device paired successfully')
          }
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

  // Cleanup on unmount
  onUnmounted(() => {
    stopCountdown()
    stopPairingCheck()
  })

  return {
    // State
    challengeToken,
    qrDataUrl,
    expiresInSeconds,
    loading,
    error,
    isPaired,

    // Computed
    isExpired,
    formattedTime,

    // Methods
    fetchChallenge,
    reset
  }
}
