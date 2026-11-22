// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useMetricsSummary, type MetricsSummarySources } from '../useMetricsSummary'
import type { GPUMetrics, NPUMetrics, ServicesSummary, AlertsSummary } from '../../types/prometheus-metrics'

function sources(): MetricsSummarySources {
  return {
    dashboard: ref(null),
    services: ref(null),
    alerts: ref(null),
    gpuDetails: ref(null),
    npuDetails: ref(null),
  }
}

describe('useMetricsSummary', () => {
  it('reads unknown health and zeros before anything has loaded', () => {
    const s = useMetricsSummary(sources())
    expect(s.systemHealth.value).toBe('unknown')
    for (const key of ['cpuUsage', 'memoryUsage', 'diskUsage', 'gpuUsage', 'npuUsage', 'healthScore', 'activeAlertCount'] as const) {
      expect(s[key].value, key).toBe(0)
    }
  })

  it('follows the sources as they load', () => {
    const src = sources()
    const s = useMetricsSummary(src)
    src.dashboard.value = { system_metrics: { cpu_percent: 41, memory_percent: 62, disk_percent: 70 }, analysis: { performance_score: 88 } }
    src.services.value = { overall_status: 'degraded' } as ServicesSummary
    src.alerts.value = { total_count: 3 } as AlertsSummary
    src.gpuDetails.value = { available: true, utilization_percent: 55 } as GPUMetrics
    src.npuDetails.value = { available: true, utilization_percent: 12 } as NPUMetrics
    expect(s.systemHealth.value).toBe('degraded')
    expect([s.cpuUsage.value, s.memoryUsage.value, s.diskUsage.value]).toEqual([41, 62, 70])
    expect([s.gpuUsage.value, s.npuUsage.value]).toEqual([55, 12])
    expect(s.healthScore.value).toBe(88)
    expect(s.activeAlertCount.value).toBe(3)
  })

  it('reads an unavailable accelerator as 0% busy, whatever it reports', () => {
    const src = sources()
    const s = useMetricsSummary(src)
    src.gpuDetails.value = { available: false, utilization_percent: 90 } as GPUMetrics
    src.npuDetails.value = { available: false, utilization_percent: 90 } as NPUMetrics
    expect([s.gpuUsage.value, s.npuUsage.value]).toEqual([0, 0])
  })

  it('treats a missing system_metrics block as zeros', () => {
    const src = sources()
    const s = useMetricsSummary(src)
    src.dashboard.value = { system_metrics: null, analysis: null }
    expect([s.cpuUsage.value, s.healthScore.value]).toEqual([0, 0])
  })
})
