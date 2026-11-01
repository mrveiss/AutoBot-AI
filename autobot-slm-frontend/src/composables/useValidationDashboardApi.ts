// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Validation dashboard API (#18278): the main backend's `/validation-dashboard` routes
 * (autobot-backend/api/validation_dashboard.py), read through the shared main-backend client.
 *
 * The screen reads `/status` (is the generator there) and `/report`. `/report` already carries
 * the metrics, trends, alerts and recommendations that `/metrics`, `/trends`, `/alerts` and
 * `/recommendations` each re-derive by regenerating the same report, so one call serves all five
 * sections and they cannot disagree. `POST /generate` is admin-only on the backend.
 *
 * The envelope types are the generated contract's. The contract types `report` as `unknown`
 * (the route returns the generator's dict), so `ValidationReport` below declares the fields the
 * screen reads, taken from `_build_report_dict` in
 * autobot-infrastructure/shared/scripts/validation_dashboard_generator.py.
 */

import { isHttpError } from '@autobot/ui'
import type { components as backend } from '@autobot/backend-contract'
import { createAutobotBackendClient } from '@/composables/useAutobotApi'

type BackendSchemas = backend['schemas']

export type ValidationDashboardStatus = BackendSchemas['ValidationDashboardStatusResponse']
export type ValidationReportEnvelope = BackendSchemas['ValidationDashboardReportResponse']
export type ValidationGenerateRequest = BackendSchemas['DashboardGenerateRequest']
export type ValidationGenerateResponse = BackendSchemas['ValidationDashboardGenerateResponse']

/** One phase, as `_format_phase_details` builds it. `completion_percentage` is null when the phase publishes no score. */
export interface ValidationPhase {
  name: string
  display_name: string
  completion_percentage: number | null
  scored: boolean
  authoritative_gates: string[]
  status: string
  missing_count: number
  requirements_met: number
  total_requirements: number
}

export interface ValidationAlert {
  level: 'critical' | 'warning' | 'info'
  title: string
  message: string
  timestamp: string
}

export interface ValidationRecommendation {
  type: string
  title: string
  description: string
  action: string
  urgency: 'high' | 'medium' | 'low' | 'info'
}

/** The generator's trend series; `{}` when it could not build them. */
export interface ValidationTrends {
  maturity_trend?: { timestamp: string; value: number }[]
  phase_completion_trend?: { timestamp: string; completed_phases: number }[]
  capability_growth?: { timestamp: string; capabilities: number }[]
}

export interface ValidationReport {
  generated_at: string
  system_overview: {
    overall_maturity: number
    /** What the headline figure measures ("completion", or presence on a CI-mode run). */
    measures: string
    total_phases: number
    completed_phases: number
    system_health: string
    active_capabilities: number
  }
  phase_details: ValidationPhase[]
  progression_status: { can_progress: boolean; next_available: string[]; blocked_phases: string[] }
  metrics: {
    completion_statistics: { average_completion: number; min_completion: number; max_completion: number; phases_above_50: number; phases_above_90: number }
    system_maturity: { overall_score: number; development_stage: string; capability_ratio: number }
    progression_metrics: { eligible_for_progression: boolean; progression_velocity: number; blocks_count: number; available_count: number }
    quality_indicators: { validation_score: number; error_rate: number; recent_changes: number }
  }
  trends: ValidationTrends
  recommendations: ValidationRecommendation[]
  alerts: ValidationAlert[]
}

export const VALIDATION_UNAVAILABLE_STATUS = 503

/** True when the backend says the dashboard generator is not installed or failed to load (503). */
export function isValidationGeneratorUnavailable(err: unknown): boolean {
  return isHttpError(err) && err.status === VALIDATION_UNAVAILABLE_STATUS
}

export function useValidationDashboardApi() {
  const client = createAutobotBackendClient()

  /** Rejects with a 503 (see isValidationGeneratorUnavailable) when the generator is missing. */
  function getStatus(): Promise<ValidationDashboardStatus> {
    // One attempt: a missing generator answers 503 at once, and the screen says so
    return client.get<ValidationDashboardStatus>('/validation-dashboard/status', { maxRetries: 1 })
  }

  /** The report the generator builds now, with its metrics, trends, alerts and recommendations; null when the route sent none. */
  async function getReport(): Promise<ValidationReport | null> {
    const envelope = await client.get<ValidationReportEnvelope>('/validation-dashboard/report', { maxRetries: 1 })
    return (envelope.report as ValidationReport | null | undefined) ?? null
  }

  /** Admin only. Starts the HTML dashboard build in the background; answers `status: "initiated"`. Omitted fields take the route's defaults. */
  function generate(request: Partial<ValidationGenerateRequest> = {}): Promise<ValidationGenerateResponse> {
    return client.post<ValidationGenerateResponse>('/validation-dashboard/generate', request)
  }

  return { getStatus, getReport, generate }
}
