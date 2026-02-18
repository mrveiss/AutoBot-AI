/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
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

/**
 * Format component name for display
 */
export function formatComponentName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

/**
 * Format timestamp for display
 */
export function formatTimestamp(timestamp: string): string {
  if (!timestamp) return 'N/A'
  try {
    return new Date(timestamp).toLocaleTimeString()
  } catch {
    return timestamp
  }
}

/**
 * Format relative timestamp
 */
export function formatRelativeTime(timestamp: string): string {
  if (!timestamp) return 'N/A'
  try {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`
    return date.toLocaleDateString()
  } catch {
    return timestamp
  }
}
