// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * VNC Connection Management Composable
 * Issue #74 - Area 4: Advanced Session Management
 */

import { ref } from 'vue'
import ApiClient from '@/api/ApiClient'
import { createLogger } from '@/utils/debugUtils'

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
  const loading = ref(false)
  const error = ref<string | null>(null)
  const settings = ref<ConnectionSettings | null>(null)
  const metrics = ref<ConnectionMetrics | null>(null)

  /**
   * Load connection settings
   */
  async function loadSettings(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      const data = await ApiClient.get<ConnectionSettings>(
        `/vnc/connection/settings?session_id=${sessionId}`
      )
      settings.value = data
    } catch (err: any) {
      logger.error('Failed to load connection settings:', err)
      error.value = 'Failed to load connection settings'
    } finally {
      loading.value = false
    }
  }

  /**
   * Update connection settings
   */
  async function updateSettings(newSettings: ConnectionSettings): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      await ApiClient.post(
        `/vnc/connection/settings?session_id=${sessionId}`,
        newSettings
      )
      settings.value = newSettings
      return true
    } catch (err: any) {
      logger.error('Failed to update connection settings:', err)
      error.value = 'Failed to update connection settings'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Load connection quality metrics
   */
  async function loadMetrics(): Promise<void> {
    try {
      const data = await ApiClient.get<ConnectionMetrics>('/vnc/connection/quality-metrics')
      metrics.value = data
    } catch (err: any) {
      logger.error('Failed to load connection metrics:', err)
    }
  }

  /**
   * Update quality preset (quick settings)
   */
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
