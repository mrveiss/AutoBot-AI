// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — shared Prometheus/monitoring metric shapes (#14907).
 *
 * `usePrometheusMetrics.ts` is declared once per app (`autobot-frontend`,
 * `autobot-slm-frontend`) because the surrounding polling/transport logic is
 * legitimately different per app (see each composable's own docs). But eight
 * type names were declared IDENTICALLY-NAMED, near-identically-shaped in
 * both files — that vocabulary belongs in one place even though the
 * composables themselves stay per-app. Domain-only types (`WorkflowMetrics`,
 * `GithubMetrics`, `MultiModalMetrics` in main; `NodeMetricsDetailed`,
 * `FleetMetricsDetailed`, `NPUFleetMetrics`, `PerformanceOverview` in the
 * SLM) are NOT here — they have no cross-app counterpart and stay local.
 *
 * Each shape below is the UNION of both apps' prior fields: every field the
 * main app's version had that the SLM's lacked is preserved as optional, so
 * neither app's existing object literals or consumers narrow.
 */

/** GPU telemetry (Issue #469 extended the main app's copy with #optional fields). */
export interface GPUMetrics {
  available: boolean
  utilization_percent: number
  memory_utilization_percent: number
  temperature_celsius: number
  power_watts: number
  name?: string
  thermal_throttling?: boolean
  /** Main-only (#469) — the SLM's copy did not carry these two. */
  gpu_id?: string
  power_throttling?: boolean
}

/** NPU telemetry (Issue #469 extended the main app's copy with #optional fields). */
export interface NPUMetrics {
  available: boolean
  utilization_percent: number
  acceleration_ratio: number
  inference_count: number
  wsl_limitation?: boolean
  /** Main-only (#469) — the SLM's copy did not carry these three. */
  hardware_detected?: boolean
  driver_available?: boolean
  openvino_support?: boolean
}

/** Per-service health snapshot — identical in both apps. */
export interface ServiceHealth {
  name: string
  host: string
  port: number
  status: 'healthy' | 'degraded' | 'critical' | 'offline'
  response_time_ms: number
  health_score: number
  uptime_hours: number
}

/** Fleet-wide service health rollup — identical in both apps. */
export interface ServicesSummary {
  total_services: number
  healthy_services: number
  degraded_services: number
  critical_services: number
  overall_status: 'healthy' | 'degraded' | 'critical'
  health_percentage: number
  services: ServiceHealth[]
}

/**
 * Performance alert from the monitoring system.
 * Issue #474 extended the main app's copy with AlertManager-specific fields.
 */
export interface PerformanceAlert {
  category: string
  severity: 'info' | 'warning' | 'critical' | 'high'
  message: string
  recommendation: string
  timestamp: number
  /** Main-only (#474) — AlertManager fields, optional for backward compat. */
  source?: 'alertmanager' | 'autobot_monitor'
  alertname?: string
  fingerprint?: string
  description?: string
  starts_at?: string
  ends_at?: string | null
  status?: string
  labels?: Record<string, string>
}

/**
 * Alert summary from the backend.
 * Issue #474 extended the main app's copy with `high_count` + source breakdown.
 */
export interface AlertsSummary {
  total_count: number
  critical_count: number
  warning_count: number
  /** Main-only (#474). */
  high_count?: number
  alerts: PerformanceAlert[]
  sources?: {
    alertmanager: number
    autobot_monitor: number
  }
}

/** Optimization recommendation — identical in both apps. */
export interface OptimizationRecommendation {
  category: string
  priority: 'high' | 'medium' | 'low'
  recommendation: string
  action: string
  expected_improvement: string
}

/** Options accepted by both apps' `usePrometheusMetrics()`. */
export interface UsePrometheusMetricsOptions {
  /** Auto-fetch on mount (default: true) */
  autoFetch?: boolean
  /** Polling interval in milliseconds (default: 30000 = 30s) */
  pollInterval?: number
  /** Enable WebSocket real-time updates (default: false) */
  useWebSocket?: boolean
  /** Main-only — WebSocket update interval in seconds (default: 2). */
  wsUpdateInterval?: number
}
