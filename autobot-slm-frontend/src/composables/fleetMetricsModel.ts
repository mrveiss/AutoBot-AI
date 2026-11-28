// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * fleetMetricsModel — the view-model and wire shapes useFleetMetrics reads and
 * presents, plus the two pure helpers that summarise them. Split out of
 * useFleetMetrics.ts (#18225) to keep that file under its size ceiling.
 */
import type { GPUMetrics, NPUMetrics } from '@autobot/ui'
import type { GPUNodeStatus } from '@/types/slm'

// ===== Type Definitions =====

/**
 * Host-level metrics as this composable presents them — a client-side
 * VIEW-MODEL, not a wire shape.
 *
 * Renamed from `SystemMetrics` in #13138: it collided with the generated
 * `components['schemas']['SystemMetrics']` (the `/health/metrics` response,
 * autobot-slm-backend/api/health.py:59) while sharing almost nothing with it —
 * `fetchDashboard` below synthesises every field from `/monitoring/dashboard`'s
 * `fleet_metrics` averages, and `timestamp` here is `Date.now()`, not an ISO
 * string. Deriving it would have been actively harmful.
 */
export interface SystemMetricsViewModel {
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  network_bytes_sent: number
  network_bytes_recv: number
  process_count: number
  timestamp: number
}

/**
 * Dashboard shape this composable exposes — a client-side VIEW-MODEL.
 *
 * Renamed from `DashboardOverview` in #13138: it collided with the generated
 * `components['schemas']['DashboardOverview']` (api/monitoring.py:118), which
 * `fetchDashboard` deliberately REMAPS into this shape (see the mapping right
 * below). The real wire model is derived, under its own name, in
 * `types/api-responses.ts`.
 */
export interface DashboardViewModel {
  system_metrics?: SystemMetricsViewModel
  gpu_metrics?: GPUMetrics
  npu_metrics?: NPUMetrics
  hardware_acceleration?: Record<string, boolean>
  analysis?: {
    overall_health: string
    performance_score: number
    bottlenecks: string[]
    resource_utilization: Record<string, number>
  }
  timestamp?: number
}

export interface NodeMetricsDetailed {
  node_id: string
  hostname: string
  ip_address: string
  status: string
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  services_running: number
  services_failed: number
}

export interface FleetMetricsDetailed {
  total_nodes: number
  online_nodes: number
  degraded_nodes: number
  offline_nodes: number
  avg_cpu_percent: number
  avg_memory_percent: number
  avg_disk_percent: number
  total_services: number
  running_services: number
  failed_services: number
  nodes: NodeMetricsDetailed[]
  timestamp: string
}

export interface PerformanceOverview {
  avg_response_time_ms: number
  p50_response_time_ms: number
  p95_response_time_ms: number
  p99_response_time_ms: number
  request_rate: number
  error_rate: number
  trace_count: number
  error_count: number
  timestamp: string
}

export interface NPUFleetMetrics {
  total_npu_nodes: number
  online_npu_nodes: number
  total_workers: number
  active_workers: number
  avg_utilization_percent: number
  total_inferences: number
  avg_inference_time_ms: number
}

/**
 * Transport-local wire shapes for the four endpoints whose responses this
 * composable REMAPS rather than assigns. They exist only to type the
 * `slmApiClient.get<T>()` calls that replace an untyped `response.json()`;
 * deriving and naming them from the generated contract is #13138's scope and is
 * deliberately not widened here.
 */
export interface DashboardWire {
  fleet_metrics?: {
    avg_cpu_percent?: number
    avg_memory_percent?: number
    avg_disk_percent?: number
    total_services?: number
  }
  health_summary?: {
    overall_status?: string
    health_score?: number
    issues?: string[]
  }
}

export interface MonitoringHealthWire {
  overall_status?: string
  health_score?: number
}

export interface MonitoringAlertsWire {
  total_count?: number
  critical_count?: number
  warning_count?: number
  alerts?: Record<string, unknown>[]
}

export interface NpuNodesWire {
  nodes?: Record<string, unknown>[]
}

/** Mean of the values a tool could read; 0 only when it read none of them. */
function meanOfKnown(values: (number | null | undefined)[]): number {
  const known = values.filter((value): value is number => value != null)
  return known.length ? known.reduce((sum, value) => sum + value, 0) / known.length : 0
}

/**
 * The fleet's measured GPUs as one GPUMetrics, or null when none is measured
 * (#15226): an unmeasured fleet is unknown, not a fleet sitting at 0%.
 */
export function summariseGpus(nodes: GPUNodeStatus[]): GPUMetrics | null {
  const devices = nodes.flatMap((node) => (node.devices ?? []).filter((device) => device.monitored))
  if (devices.length === 0) return null
  const used = devices.reduce((sum, device) => sum + (device.memory_used_mb ?? 0), 0)
  const total = devices.reduce((sum, device) => sum + (device.memory_total_mb ?? 0), 0)
  return {
    available: true,
    utilization_percent: meanOfKnown(devices.map((device) => device.utilization_percent)),
    memory_utilization_percent: total ? (used / total) * 100 : 0,
    temperature_celsius: Math.max(0, ...devices.map((device) => device.temperature_celsius ?? 0)),
    power_watts: devices.reduce((sum, device) => sum + (device.power_watts ?? 0), 0),
    name: devices.length === 1 ? (devices[0].name ?? undefined) : undefined,
  }
}
