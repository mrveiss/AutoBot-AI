// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * VNC Connection Management Composable
 * Issue #74 - Area 4: Advanced Session Management
 */

import { ref, computed } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useVncConnection')

export interface ConnectionQualitySettings {
  compression_level: number  // 0-9
  quality: number  // 0-9
  encoding: string  // tight, hextile, raw
}

export interface ConnectionSettings {
  auto_reconnect: boolean
  reconnect_delay_ms: number
  max_reconnect_attempts: number
  quality: ConnectionQualitySettings
}

export interface ConnectionMetrics {
  vnc_running: boolean
  vnc_port_reachable: boolean
  websockify_running: boolean
  websockify_processes?: number
  latency_ms?: number
  timestamp: string
}

export function useVncConnection(sessionId: string = 'default') {
  const { isLoading: loading, wrap } = useLoadingState()
  const errors = ref<string[]>([])
  const error = computed<string | null>(() =>
    errors.value.length > 0 ? errors.value.join('; ') : null,
  )
  const settings = ref<ConnectionSettings | null>(null)
  const metrics = ref<ConnectionMetrics | null>(null)

  async function loadSettings(): Promise<void> {
    errors.value = []
    try {
      const data = await wrap(() =>
        ApiClient.get<ConnectionSettings>(`/vnc/connection/settings?session_id=${sessionId}`)
      )
      settings.value = data
    } catch (err: unknown) {
      logger.error('Failed to load connection settings:', err)
      errors.value = [...errors.value, 'Failed to load connection settings']
    }
  }

  async function updateSettings(newSettings: ConnectionSettings): Promise<boolean> {
    errors.value = []
    try {
      await wrap(() =>
        ApiClient.post(`/vnc/connection/settings?session_id=${sessionId}`, newSettings)
      )
      settings.value = newSettings
      return true
    } catch (err: unknown) {
      logger.error('Failed to update connection settings:', err)
      errors.value = [...errors.value, 'Failed to update connection settings']
      return false
    }
  }

  async function loadMetrics(): Promise<void> {
    try {
      const data = await ApiClient.get<ConnectionMetrics>('/vnc/connection/quality-metrics')
      metrics.value = data
    } catch (err: unknown) {
      logger.error('Failed to load connection metrics:', err)
    }
  }

  async function setQualityPreset(preset: 'low' | 'medium' | 'high' | 'best'): Promise<boolean> {
    if (!settings.value) {
      await loadSettings()
      if (!settings.value) return false
    }

    const presets: Record<string, Partial<ConnectionQualitySettings>> = {
      low: { compression_level: 9, quality: 2, encoding: 'tight' },
      medium: { compression_level: 6, quality: 5, encoding: 'tight' },
      high: { compression_level: 3, quality: 7, encoding: 'tight' },
      best: { compression_level: 0, quality: 9, encoding: 'tight' }
    }

    const newSettings: ConnectionSettings = {
      ...settings.value,
      quality: {
        ...settings.value.quality,
        ...presets[preset]
      }
    }

    return updateSettings(newSettings)
  }

  return {
    loading,
    error,
    settings,
    metrics,
    loadSettings,
    updateSettings,
    loadMetrics,
    setQualityPreset
  }
}
