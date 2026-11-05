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
import { createAutobotBackendClient } from '@/composables/useAutobotApi'

export interface InstallSystemMetrics {
  cpu_percent?: number
  memory_percent?: number
  disk_percent?: number
  process_count?: number
}

export interface InstallAnalysis {
  overall_health?: string
  performance_score?: number
  bottlenecks?: string[]
}

export interface InstallDashboardOverview {
  system_metrics?: InstallSystemMetrics | null
  analysis?: InstallAnalysis | null
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
