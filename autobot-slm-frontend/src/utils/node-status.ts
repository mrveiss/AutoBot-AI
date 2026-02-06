// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Node Status Utilities
 *
 * Shared utilities for node status display across components.
 *
 * Issue #737 Phase 3: Unified data models
 */

import type { NodeStatus, HealthStatus } from '@/types/slm'

/**
 * Status categories for styling purposes.
 */
export type StatusCategory = 'healthy' | 'warning' | 'error' | 'neutral'

/**
 * Map status string to category for consistent styling.
 */
export function getStatusCategory(status: string): StatusCategory {
  switch (status) {
    case 'healthy':
    case 'online':
    case 'running':
      return 'healthy'
    case 'degraded':
    case 'warning':
    case 'pending':
    case 'enrolling':
    case 'registered':
      return 'warning'
    case 'unhealthy':
    case 'error':
    case 'failed':
    case 'critical':
      return 'error'
    case 'offline':
    case 'unknown':
    case 'stopped':
    case 'maintenance':
    default:
      return 'neutral'
  }
}

/**
 * Get Tailwind background color class for status.
 */
export function getStatusBgColor(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'bg-green-500'
    case 'warning':
      return 'bg-yellow-500'
    case 'error':
      return 'bg-red-500'
    case 'neutral':
    default:
      return 'bg-gray-400'
  }
}

/**
 * Get Tailwind text color class for status.
 */
export function getStatusTextColor(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'text-green-600'
    case 'warning':
      return 'text-yellow-600'
    case 'error':
      return 'text-red-600'
    case 'neutral':
    default:
      return 'text-gray-500'
  }
}

/**
 * Get Tailwind badge classes for status display.
 */
export function getStatusBadgeClass(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'bg-green-100 text-green-800'
    case 'warning':
      return 'bg-yellow-100 text-yellow-800'
    case 'error':
      return 'bg-red-100 text-red-800'
    case 'neutral':
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

/**
 * Get status indicator dot classes.
 */
export function getStatusDotClass(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'bg-green-500'
    case 'warning':
      return 'bg-yellow-500 animate-pulse'
    case 'error':
      return 'bg-red-500'
    case 'neutral':
    default:
      return 'bg-gray-400'
  }
}

/**
 * Get human-readable status label.
 */
export function getStatusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, ' ')
}

/**
 * Check if status indicates node is operational.
 */
export function isOperational(status: NodeStatus | HealthStatus | string): boolean {
  return ['healthy', 'online', 'degraded'].includes(status)
}

/**
 * Check if status indicates node needs attention.
 */
export function needsAttention(status: NodeStatus | HealthStatus | string): boolean {
  return ['degraded', 'unhealthy', 'error', 'failed'].includes(status)
}

/**
 * Get color for metric value (CPU, memory, disk).
 */
export function getMetricColor(value: number): string {
  if (value >= 90) return 'text-red-500'
  if (value >= 70) return 'text-yellow-500'
  return 'text-green-500'
}

/**
 * Get progress bar color class for metric.
 */
export function getMetricBarColor(value: number): string {
  if (value >= 90) return 'bg-red-500'
  if (value >= 70) return 'bg-yellow-500'
  return 'bg-green-500'
}
