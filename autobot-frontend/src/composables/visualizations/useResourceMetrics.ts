// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useResourceMetrics
 *
 * Encapsulates the backend fetch and data-processing logic for the
 * ResourceHeatmap component (#6086).
 *
 * Responsibilities:
 *  - Fetch `/monitoring/metrics/history` via fetchWithAuth
 *  - Manage reactive `heatmapData`, `isLoading`, and `error` state
 *  - Transform raw API response into ApexCharts heatmap series format
 *  - Fall back to generated sample data when the API is unavailable
 *  - Expose `selectedMetric`, `timeRange`, `fetchData`, and `updateData`
 *    so the component owns zero fetching logic
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useResourceMetrics')

export type HeatmapPoint = { x: string; y: number }
export type HeatmapSeries = { name: string; data: HeatmapPoint[] }

interface MetricsApiResponse {
  machines: Array<{ name: string; metrics: Array<{ time: string; value: number }> }>
}

export function useResourceMetrics(machine: () => string) {
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)
  const selectedMetric = ref('cpu')
  const timeRange = ref('1h')
  const heatmapData = ref<HeatmapSeries[]>([])

  // ── Helpers ──────────────────────────────────────────────────────────────

  function formatTimeLabel(date: Date): string {
    switch (timeRange.value) {
      case '1h':
      case '6h':
        return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
      case '24h':
        return date.toLocaleTimeString(undefined, { hour: '2-digit' })
      case '7d':
        return (
          date.toLocaleDateString(undefined, { weekday: 'short' }) +
          ' ' +
          date.toLocaleTimeString(undefined, { hour: '2-digit' })
        )
      default:
        return date.toLocaleTimeString()
    }
  }

  function processData(data: MetricsApiResponse): void {
    // No machines reported is an empty heatmap, never invented values (#19270).
    if (!data.machines || !Array.isArray(data.machines)) {
      heatmapData.value = []
      return
    }

    heatmapData.value = data.machines.map(m => ({
      name: m.name,
      // The backend sends ISO timestamps; label them for the selected range (#19270).
      data: m.metrics.map(metric => ({ x: formatTimeLabel(new Date(metric.time)), y: metric.value }))
    }))
  }

  // ── Public API ────────────────────────────────────────────────────────────

  async function fetchData(): Promise<void> {
    error.value = null
    await wrap(async () => {
      try {
        const data = await apiClient.get<MetricsApiResponse>(
          `${getApiBase()}/monitoring/metrics/history?metric=${selectedMetric.value}&range=${timeRange.value}&machine=${machine()}`
        )
        processData(data)
      } catch (err) {
        logger.error('Failed to fetch heatmap data:', err)
        error.value = err instanceof Error ? err.message : String(err) // shown under the translated heading
        heatmapData.value = [] // the error state shows; no invented values behind it (#19270)
      }
    })
  }

  function updateData(): void {
    fetchData()
  }

  return {
    isLoading,
    error,
    selectedMetric,
    timeRange,
    heatmapData,
    fetchData,
    updateData
  }
}
