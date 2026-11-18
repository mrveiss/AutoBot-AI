// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Install metrics API (#19484): the main backend's `/monitoring` routes, read through the shared
 * main-backend client. This is the reader that used to live in the main app's
 * `useInstallMetrics`; it moved here so the SLM can show an install's metrics on its own screen
 * and say plainly when the main app is not answering.
 *
 * Six independent reads. Each is reported on its own (`SectionResult`), so one route failing
 * leaves the others readable, and all six failing is the main app being down. A failed read
 * carries its error and no data: the screen never keeps an earlier reading to show as current.
 * The metric shapes are the kit's; the dashboard overview is declared here for the fields the
 * screen reads (the route returns the monitor's dict).
 */

import type {
  AlertsSummary,
  GPUMetrics,
  NPUMetrics,
  OptimizationRecommendation,
  ServicesSummary,
} from '@autobot/ui'
import { isHttpError } from '@autobot/ui'
import { createAutobotBackendClient } from '@/composables/useAutobotApi'

/**
 * The dashboard's `system` block, as the main backend's monitor stores it and `monitoring_utils.py`
 * reads it. The route is `response_model=dict`, so it publishes no schema and there is no generated
 * type to import: this is the one declaration of the fields the screen reads. The monitor reports
 * no disk figure and no process count, so the screen shows none.
 */
export interface InstallSystemMetrics {
  cpu_usage_percent?: number
  memory_usage_percent?: number
}

export interface InstallAnalysis {
  overall_health?: string
  performance_score?: number
  bottlenecks?: string[]
}

export interface InstallDashboardOverview {
  system?: InstallSystemMetrics | null
  analysis?: InstallAnalysis | null
}

/**
 * The route attaches `analysis` to every reply, derived from whatever the monitor holds. With
 * nothing measured it is the default: healthy, score 0, no bottlenecks. Only a score above 0 or a
 * named bottleneck means the analysis was computed from a measurement.
 */
export function analysisMeasured(analysis: InstallAnalysis | null | undefined): boolean {
  if (!analysis) return false
  return (typeof analysis.performance_score === 'number' && analysis.performance_score > 0) || (analysis.bottlenecks?.length ?? 0) > 0
}

export type SectionResult<D> = { ok: true; data: D } | { ok: false; error: unknown }

export interface InstallMetricsReading {
  dashboard: SectionResult<InstallDashboardOverview>
  services: SectionResult<ServicesSummary>
  alerts: SectionResult<AlertsSummary>
  recommendations: SectionResult<OptimizationRecommendation[]>
  gpu: SectionResult<GPUMetrics>
  npu: SectionResult<NPUMetrics>
}

export const INSTALL_METRICS_SECTIONS = ['dashboard', 'services', 'alerts', 'recommendations', 'gpu', 'npu'] as const

/** How many of the six reads failed. */
export function failedReadCount(reading: InstallMetricsReading): number {
  return INSTALL_METRICS_SECTIONS.filter((key) => !reading[key].ok).length
}

/** All six failed: the main app is down or unreachable, not one route misbehaving. */
export function isMainAppUnavailable(reading: InstallMetricsReading): boolean {
  return failedReadCount(reading) === INSTALL_METRICS_SECTIONS.length
}

/** All six failed with 401/403: the main app answered and refused this session, it is not down. */
export function isMainAppUnauthorised(reading: InstallMetricsReading): boolean {
  return INSTALL_METRICS_SECTIONS.every((key) => {
    const result = reading[key]
    return !result.ok && isHttpError(result.error) && (result.error.status === 401 || result.error.status === 403)
  })
}

export function useInstallMetricsApi() {
  const client = createAutobotBackendClient()

  async function read<D>(path: string): Promise<SectionResult<D>> {
    try {
      return { ok: true, data: await client.get<D>(path, { maxRetries: 1 }) }
    } catch (error) {
      return { ok: false, error }
    }
  }

  async function readAll(): Promise<InstallMetricsReading> {
    const [dashboard, services, alerts, recommendations, gpu, npu] = await Promise.all([
      read<InstallDashboardOverview>('/monitoring/dashboard/overview'),
      read<ServicesSummary>('/monitoring/services/health'),
      read<AlertsSummary>('/monitoring/alerts/check'),
      read<OptimizationRecommendation[]>('/monitoring/optimization/recommendations'),
      read<GPUMetrics>('/monitoring/hardware/gpu'),
      read<NPUMetrics>('/monitoring/hardware/npu'),
    ])
    return { dashboard, services, alerts, recommendations, gpu, npu }
  }

  return { readAll }
}
