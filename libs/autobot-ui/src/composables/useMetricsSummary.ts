// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useMetricsSummary — the headline numbers a monitoring screen shows (health,
// CPU, memory, disk, GPU, NPU, score, open alerts), derived from the shared
// metric shapes. Both apps computed these eight values identically inside
// their own usePrometheusMetrics (#18225); the fetching around them stays per
// app, because the user app reads its install's backend and the SLM reads the
// fleet (owner decision 2026-10-24 on #18225).

import { computed } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { AlertsSummary, GPUMetrics, NPUMetrics, ServicesSummary } from '../types/prometheus-metrics'

export type SystemHealth = ServicesSummary['overall_status'] | 'unknown'

/** The dashboard fields the summary reads; each app's dashboard type has at least these. */
export interface MetricsSummaryDashboard {
  system_metrics?: {
    cpu_percent?: number
    memory_percent?: number
    disk_percent?: number
  } | null
  analysis?: { performance_score?: number } | null
}

export interface MetricsSummarySources {
  dashboard: Ref<MetricsSummaryDashboard | null>
  services: Ref<ServicesSummary | null>
  alerts: Ref<AlertsSummary | null>
  gpuDetails: Ref<GPUMetrics | null>
  npuDetails: Ref<NPUMetrics | null>
}

export interface MetricsSummary {
  systemHealth: ComputedRef<SystemHealth>
  cpuUsage: ComputedRef<number>
  memoryUsage: ComputedRef<number>
  diskUsage: ComputedRef<number>
  gpuUsage: ComputedRef<number>
  npuUsage: ComputedRef<number>
  healthScore: ComputedRef<number>
  activeAlertCount: ComputedRef<number>
}

/** A device that is absent or unavailable reads as 0% busy. */
function utilisation(device: GPUMetrics | NPUMetrics | null): number {
  return device?.available ? (device.utilization_percent ?? 0) : 0
}

export function useMetricsSummary(sources: MetricsSummarySources): MetricsSummary {
  const { dashboard, services, alerts, gpuDetails, npuDetails } = sources
  return {
    systemHealth: computed<SystemHealth>(() => services.value?.overall_status ?? 'unknown'),
    cpuUsage: computed(() => dashboard.value?.system_metrics?.cpu_percent ?? 0),
    memoryUsage: computed(() => dashboard.value?.system_metrics?.memory_percent ?? 0),
    diskUsage: computed(() => dashboard.value?.system_metrics?.disk_percent ?? 0),
    gpuUsage: computed(() => utilisation(gpuDetails.value)),
    npuUsage: computed(() => utilisation(npuDetails.value)),
    healthScore: computed(() => dashboard.value?.analysis?.performance_score ?? 0),
    activeAlertCount: computed(() => alerts.value?.total_count ?? 0),
  }
}
