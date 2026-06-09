// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Shared types for System Validation Dashboard (Issue #581)
 */

/**
 * VM Health status for infrastructure monitoring
 */
export interface VMHealth {
  name: string
  ip: string
  port: number
  status: VMStatus
  responseTime: number
  healthScore: number
  lastCheck: string
  services: string[]
}

/**
 * VM status values
 */
export type VMStatus = 'healthy' | 'degraded' | 'critical' | 'offline'

/**
 * Health history entry for timeline
 */
export interface HealthHistoryEntry {
  timestamp: string
  score: number
  status: string
  componentScores: Record<string, number>
}

/**
 * Recommendation from validation
 */
export interface Recommendation {
  component: string
  recommendation: string
}

/**
 * Component validation status
 */
export interface ComponentStatus {
  status: string
  score: number
  message: string
  lastValidated?: string
  details?: Record<string, unknown>
}

/**
 * Quick component status from API
 */
export interface ComponentQuickStatus {
  status: string
  score: number
  message: string
}

/**
 * Validation result from comprehensive validation
 */
export interface ValidationResult {
  validation_id: string
  status: string
  overall_score: number
  component_scores: Record<string, number>
  recommendations: string[]
  test_results: Record<string, unknown>
  execution_time: number
  timestamp: string
}

/**
 * System status from validation API
 */
export interface SystemStatus {
  validation_system: string
  available_validations: string[]
  last_validation: string | null
  system_health: string
  timestamp: string
}

/**
 * Quick validation response
 */
export interface QuickValidationResponse {
  status: string
  overall_score: number
  components: Record<string, ComponentQuickStatus>
  timestamp: string
}

/**
 * Health score classification
 */
export type HealthClass = 'excellent' | 'good' | 'warning' | 'degraded' | 'critical'

/**
 * Get health class from score
 */
export function getHealthClass(score: number): HealthClass {
  if (score >= 90) return 'excellent'
  if (score >= 70) return 'good'
  if (score >= 50) return 'warning'
  if (score >= 30) return 'degraded'
  return 'critical'
}

