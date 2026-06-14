// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useDevices.ts - Mobile device management composable (GH#4463, MVA-1619)
 * Manages paired mobile devices for push notifications.
 */

import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useDevices')

export interface Device {
  id: string
  device_name: string
  platform: 'ios' | 'android' | 'pwa'
  last_seen_at: string | null
  created_at: string
}

export interface DeviceListResponse {
  devices: Device[]
}

// Module-level singleton state
const devices = ref<Device[]>([])
const { isLoading: loading, wrap } = useLoadingState()
const error = ref<string | null>(null)

export function useDevices() {
  const api = useApiClient()

  const sortedDevices = computed(() => {
    return [...devices.value].sort((a, b) => {
      const timeA = new Date(a.last_seen_at || a.created_at).getTime()
      const timeB = new Date(b.last_seen_at || b.created_at).getTime()
      return timeB - timeA // Most recent first
    })
  })

  async function fetchDevices() {
    return wrap(async () => {
      try {
        error.value = null
        const response = await api.get<DeviceListResponse>('/devices')
        devices.value = response.devices || []
        logger.debug('Fetched devices:', devices.value.length)
      } catch (err: any) {
        const msg = err?.message || 'Failed to load devices'
        error.value = msg
        logger.error('Failed to fetch devices:', err)
        throw err
      }
    })
  }

  async function deleteDevice(deviceId: string) {
    return wrap(async () => {
      try {
        error.value = null
        await api.delete(`/devices/${deviceId}`)
        devices.value = devices.value.filter(d => d.id !== deviceId)
        logger.info('Device deleted:', deviceId)
      } catch (err: any) {
        const msg = err?.message || 'Failed to delete device'
        error.value = msg
        logger.error('Failed to delete device:', err)
        throw err
      }
    })
  }

  async function getQRChallenge() {
    return wrap(async () => {
      try {
        error.value = null
        const response = await api.get('/devices/pair-qr')
        logger.debug('Got QR challenge')
        return response
      } catch (err: any) {
        const msg = err?.message || 'Failed to get pairing QR code'
        error.value = msg
        logger.error('Failed to get QR challenge:', err)
        throw err
      }
    })
  }

  async function pairDevice(payload: {
    challenge_token: string
    device_name: string
    device_token: string
    platform: string
  }) {
    return wrap(async () => {
      try {
        error.value = null
        const response = await api.post<{ device_id?: string }>('/devices/pair', payload)
        // Refresh the device list after successful pairing
        await fetchDevices()
        logger.info('Device paired:', response.device_id)
        return response
      } catch (err: any) {
        const msg = err?.message || 'Failed to pair device'
        error.value = msg
        logger.error('Failed to pair device:', err)
        throw err
      }
    })
  }

  return {
    devices: computed(() => sortedDevices.value),
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    fetchDevices,
    deleteDevice,
    getQRChallenge,
    pairDevice
  }
}
