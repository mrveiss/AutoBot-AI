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

  function getTimeIntervals(): Date[] {
    const intervals: Date[] = []
    const now = new Date()
    let count: number
    let step: number

    switch (timeRange.value) {
      case '1h':
        count = 12
        step = 5 * 60 * 1000
        break
      case '6h':
        count = 24
        step = 15 * 60 * 1000
        break
      case '24h':
        count = 24
        step = 60 * 60 * 1000
        break
      case '7d':
        count = 28
        step = 6 * 60 * 60 * 1000
        break
      default:
        count = 12
        step = 5 * 60 * 1000
    }

    for (let i = count - 1; i >= 0; i--) {
      intervals.push(new Date(now.getTime() - i * step))
    }
    return intervals
  }

  function formatTimeLabel(date: Date): string {
    switch (timeRange.value) {
      case '1h':
      case '6h':
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
      case '24h':
        return date.toLocaleTimeString('en-US', { hour: '2-digit' }) + 'h'
      case '7d':
        return (
          date.toLocaleDateString('en-US', { weekday: 'short' }) +
          ' ' +
          date.toLocaleTimeString('en-US', { hour: '2-digit' })
        )
      default:
        return date.toLocaleTimeString()
    }
  }

  function generateSampleData(): void {
    const machines = ['Main (WSL)', 'Frontend VM', 'NPU Worker', 'Redis VM', 'AI Stack', 'Browser VM']
    const intervals = getTimeIntervals()

    heatmapData.value = machines.map((machineName, machineIdx) => ({
      name: machineName,
      data: intervals.map((interval, idx) => {
        let baseValue = 30 + Math.random() * 20

        const hour = new Date(interval).getHours()
        if (hour >= 9 && hour <= 17) baseValue += 20

        if (machineIdx === 0) baseValue += 10
        if (machineIdx === 2) baseValue += Math.sin(idx / 5) * 15

        if (Math.random() > 0.9) baseValue += 30

        return {
          x: formatTimeLabel(interval),
          y: Math.min(100, Math.max(0, Math.round(baseValue)))
        }
      })
    }))
  }

  function processData(data: MetricsApiResponse): void {
    if (!data.machines || !Array.isArray(data.machines)) {
      generateSampleData()
      return
    }

    heatmapData.value = data.machines.map(m => ({
      name: m.name,
      data: m.metrics.map(metric => ({ x: metric.time, y: metric.value }))
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
        error.value = err instanceof Error ? err.message : 'Failed to load data'
        generateSampleData()
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
