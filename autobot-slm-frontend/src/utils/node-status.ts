// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Node Status Utilities
 *
 * Shared utilities for node status display across components.
 *
 * Issue #737 Phase 3: Unified data models
 */

import type { NodeStatus, NodeHealthStatus, ServiceStatus } from '@/types/slm'

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
      return 'bg-autobot-dot-ok'
    case 'warning':
      return 'bg-autobot-dot-warn'
    case 'error':
      return 'bg-autobot-dot-bad'
    case 'neutral':
    default:
      return 'bg-autobot-dot-idle'
  }
}

/**
 * Get Tailwind text color class for status.
 */
export function getStatusTextColor(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'text-autobot-success'
    case 'warning':
      return 'text-autobot-warning'
    case 'error':
      return 'text-autobot-error'
    case 'neutral':
    default:
      return 'text-autobot-text-tertiary'
  }
}

/**
 * Get Tailwind badge classes for status display.
 */
export function getStatusBadgeClass(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'warning':
      return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    case 'error':
      return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    case 'neutral':
    default:
      return 'bg-autobot-bg-tertiary text-autobot-text-primary'
  }
}

/**
 * Get status indicator dot classes.
 */
export function getStatusDotClass(status: string): string {
  const category = getStatusCategory(status)
  switch (category) {
    case 'healthy':
      return 'bg-autobot-dot-ok'
    case 'warning':
      return 'bg-autobot-dot-warn animate-pulse'
    case 'error':
      return 'bg-autobot-dot-bad'
    case 'neutral':
    default:
      return 'bg-autobot-dot-idle'
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
export function isOperational(status: NodeStatus | NodeHealthStatus | string): boolean {
  return ['healthy', 'online', 'degraded'].includes(status)
}

/**
 * Check if status indicates node needs attention.
 */
export function needsAttention(status: NodeStatus | NodeHealthStatus | string): boolean {
  return ['degraded', 'unhealthy', 'error', 'failed'].includes(status)
}

/**
 * Get color for metric value (CPU, memory, disk).
 */
export function getMetricColor(value: number): string {
  if (value >= 90) return 'text-autobot-error'
  if (value >= 70) return 'text-autobot-warning'
  return 'text-autobot-success'
}

/**
 * Get progress bar color class for metric.
 */
export function getMetricBarColor(value: number): string {
  if (value >= 90) return 'bg-autobot-dot-bad'
  if (value >= 70) return 'bg-autobot-dot-warn'
  return 'bg-autobot-dot-ok'
}

/**
 * Normalize a full NodeStatus value to the three-value display union used by
 * NodeHealthCard ('online' | 'offline' | 'unknown').
 *
 * Mapping rationale:
 *   online / healthy / degraded                  -> 'online'  (reachable, serving)
 *   offline / unhealthy / error / decommissioned -> 'offline' (unreachable or broken)
 *   registered / pending / enrolling / maintenance -> 'unknown' (transitional)
 *
 * Issue #3195
 */
export function normalizeNodeStatus(status: NodeStatus | string): 'online' | 'offline' | 'unknown' {
  switch (status) {
    case 'online':
    case 'healthy':
    case 'degraded':
      return 'online'
    case 'offline':
    case 'unhealthy':
    case 'error':
    case 'decommissioned':
      return 'offline'
    case 'registered':
    case 'pending':
    case 'enrolling':
    case 'maintenance':
    default:
      return 'unknown'
  }
}

/**
 * Normalize a service status string to the four-value union used by
 * ServiceActionButtons ('running' | 'stopped' | 'failed' | 'unknown').
 *
 * `ServiceStatus` is wider since #15401 -- it carries the agent's full run-state
 * vocabulary -- so this is a narrowing, not a no-op: `starting`, `stopping`,
 * `completed` and `crash-loop` collapse to `unknown` here, as they always did
 * when those values arrived as plain strings.
 *
 * Issue #3195
 */
export function normalizeServiceStatus(status: ServiceStatus | string): 'running' | 'stopped' | 'failed' | 'unknown' {
  switch (status) {
    case 'running':
      return 'running'
    case 'stopped':
      return 'stopped'
    case 'failed':
      return 'failed'
    default:
      return 'unknown'
  }
}
