// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Mobile Device Pairing Composable (GH#4463)
 *
 * Provides reactive state and methods for:
 * - Generating QR codes for device pairing
 * - Listing paired devices
 * - Deleting devices
 */

import { ref, computed } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useMobileDevices')

export interface MobileDevice {
  id: string
  device_name: string
  platform: 'ios' | 'android' | 'pwa'
  last_seen_at: string | null
  created_at: string
}

export interface QRChallenge {
  challenge_token: string
  expires_in_seconds: number
}

export function useMobileDevices() {
  const devices = ref<MobileDevice[]>([])
  const currentQR = ref<QRChallenge | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const hasDevices = computed(() => devices.value.length > 0)

  /**
   * Generate a new QR challenge token for device pairing.
   * The token expires in 5 minutes.
   */
  async function generateQRCode(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const response = await apiClient.get<QRChallenge>('/devices/pair-qr')
      currentQR.value = response
      logger.info('QR challenge generated', { expiresIn: response.expires_in_seconds })
    } catch (err: any) {
      error.value = err.message || 'Failed to generate QR code'
      logger.error('QR generation failed', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch the list of paired devices for the current user.
   * Automatically prunes devices inactive for 90+ days.
   */
  async function fetchDevices(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const response = await apiClient.get<{ devices: MobileDevice[] }>('/devices')
      devices.value = response.devices
      logger.info('Fetched devices', { count: devices.value.length })
    } catch (err: any) {
      error.value = err.message || 'Failed to fetch devices'
      logger.error('Device fetch failed', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Delete a paired device.
   */
  async function deleteDevice(deviceId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await apiClient.delete(`/devices/${deviceId}`)
      // Remove from local list
      devices.value = devices.value.filter((d) => d.id !== deviceId)
      logger.info('Device deleted', { deviceId })
    } catch (err: any) {
      error.value = err.message || 'Failed to delete device'
      logger.error('Device deletion failed', { deviceId, error: err })
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Clear the current error message.
   */
  function clearError(): void {
    error.value = null
  }

  /**
   * Clear the current QR challenge (e.g., after it expires).
   */
  function clearQRChallenge(): void {
    currentQR.value = null
  }

  return {
    devices,
    currentQR,
    loading,
    error,
    hasDevices,
    generateQRCode,
    fetchDevices,
    deleteDevice,
    clearError,
    clearQRChallenge,
  }
}
