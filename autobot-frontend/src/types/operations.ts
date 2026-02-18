/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * TypeScript types for Long-Running Operations
 * Issue #591 - Long-Running Operations Tracker
 */

/**
 * Operation status enum matching backend OperationStatus
 */
export type OperationStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'timeout'
  | 'cancelled'
  | 'paused'

/**
 * Operation type enum matching backend OperationType
 */
export type OperationType =
  | 'codebase_indexing'
  | 'comprehensive_test_suite'
  | 'kb_population'
  | 'security_scan'
  | 'code_analysis'
  | 'migration'
  | 'other'

/**
 * Operation priority levels
 */
export type OperationPriority = 'low' | 'normal' | 'high' | 'critical'

/**
 * Single operation data structure
 */
export interface Operation {
  operation_id: string
  name: string
  description: string
  operation_type: OperationType
  status: OperationStatus
  priority: OperationPriority
  progress: number // 0-100
  current_step: string
  estimated_items: number
  processed_items: number
  created_at: string // ISO timestamp
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  context: Record<string, unknown>
  checkpoints_count: number
  can_resume: boolean
}

/**
 * Operations list response from backend
 */
export interface OperationsListResponse {
  operations: Operation[]
  total_count: number
  active_count: number
  completed_count: number
  failed_count: number
}

/**
 * Operation health check response
 */
export interface OperationsHealthResponse {
  status: 'healthy' | 'unavailable' | 'error'
  active_operations: number
  total_operations: number
  redis_connected: boolean
  background_processor_running: boolean
  message?: string
}

/**
 * Create operation request
 */
export interface CreateOperationRequest {
  operation_type: OperationType
  name: string
  description?: string
  priority?: OperationPriority
  estimated_items?: number
  context?: Record<string, unknown>
  execute_immediately?: boolean
}

/**
 * Operation creation response
 */
export interface CreateOperationResponse {
  operation_id: string
  status: string
}

/**
 * Resume operation response
 */
export interface ResumeOperationResponse {
  status: string
  new_operation_id: string
  resumed_from: string
  original_operation_id: string
}

/**
 * Cancel operation response
 */
export interface CancelOperationResponse {
  status: string
  operation_id: string
}

/**
 * Filter options for operations list
 */
export interface OperationsFilter {
  status?: OperationStatus
  operation_type?: OperationType
  limit?: number
}

/**
 * Status display configuration
 */
export interface StatusConfig {
  label: string
  color: string
  icon: string
  bgClass: string
  textClass: string
}

/**
 * Map of operation statuses to display configuration
 */
export const STATUS_CONFIG: Record<OperationStatus, StatusConfig> = {
  pending: {
    label: 'Pending',
    color: 'gray',
    icon: 'fas fa-clock',
    bgClass: 'bg-gray-100',
    textClass: 'text-gray-700'
  },
  running: {
    label: 'Running',
    color: 'blue',
    icon: 'fas fa-spinner fa-spin',
    bgClass: 'bg-blue-100',
    textClass: 'text-blue-700'
  },
  completed: {
    label: 'Completed',
    color: 'green',
    icon: 'fas fa-check-circle',
    bgClass: 'bg-green-100',
    textClass: 'text-green-700'
  },
  failed: {
    label: 'Failed',
    color: 'red',
    icon: 'fas fa-times-circle',
    bgClass: 'bg-red-100',
    textClass: 'text-red-700'
  },
  timeout: {
    label: 'Timeout',
    color: 'orange',
    icon: 'fas fa-hourglass-end',
    bgClass: 'bg-orange-100',
    textClass: 'text-orange-700'
  },
  cancelled: {
    label: 'Cancelled',
    color: 'yellow',
    icon: 'fas fa-ban',
    bgClass: 'bg-yellow-100',
    textClass: 'text-yellow-700'
  },
  paused: {
    label: 'Paused',
    color: 'purple',
    icon: 'fas fa-pause-circle',
    bgClass: 'bg-purple-100',
    textClass: 'text-purple-700'
  }
}

/**
 * Map of operation types to display labels
 */
export const OPERATION_TYPE_LABELS: Record<OperationType, string> = {
  codebase_indexing: 'Codebase Indexing',
  comprehensive_test_suite: 'Test Suite',
  kb_population: 'Knowledge Base',
  security_scan: 'Security Scan',
  code_analysis: 'Code Analysis',
  migration: 'Migration',
  other: 'Other'
}

/**
 * Map of operation types to icons
 */
export const OPERATION_TYPE_ICONS: Record<OperationType, string> = {
  codebase_indexing: 'fas fa-code',
  comprehensive_test_suite: 'fas fa-vial',
  kb_population: 'fas fa-database',
  security_scan: 'fas fa-shield-alt',
  code_analysis: 'fas fa-search',
  migration: 'fas fa-exchange-alt',
  other: 'fas fa-cog'
}

/**
 * Priority display configuration
 */
export const PRIORITY_CONFIG: Record<OperationPriority, { label: string; color: string }> = {
  low: { label: 'Low', color: 'gray' },
  normal: { label: 'Normal', color: 'blue' },
  high: { label: 'High', color: 'orange' },
  critical: { label: 'Critical', color: 'red' }
}

/**
 * Helper to check if operation is in a terminal state
 */
export function isTerminalStatus(status: OperationStatus): boolean {
  return ['completed', 'failed', 'timeout', 'cancelled'].includes(status)
}

/**
 * Helper to check if operation can be cancelled
 */
export function canCancel(operation: Operation): boolean {
  return ['pending', 'running', 'paused'].includes(operation.status)
}

/**
 * Helper to check if operation can be resumed
 */
export function canResume(operation: Operation): boolean {
  return operation.can_resume && ['failed', 'timeout', 'paused'].includes(operation.status)
}

/**
 * Format duration in human-readable form
 */
export function formatDuration(startTime: string | null, endTime: string | null): string {
  if (!startTime) return '-'

  const start = new Date(startTime).getTime()
  const end = endTime ? new Date(endTime).getTime() : Date.now()
  const durationMs = end - start

  if (durationMs < 1000) return `${durationMs}ms`
  if (durationMs < 60000) return `${Math.round(durationMs / 1000)}s`
  if (durationMs < 3600000) {
    const mins = Math.floor(durationMs / 60000)
    const secs = Math.round((durationMs % 60000) / 1000)
    return `${mins}m ${secs}s`
  }

  const hours = Math.floor(durationMs / 3600000)
  const mins = Math.floor((durationMs % 3600000) / 60000)
  return `${hours}h ${mins}m`
}

/**
 * Format timestamp to relative time
 */
export function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return '-'

  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  if (diffMs < 60000) return 'Just now'
  if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)} min ago`
  if (diffMs < 86400000) return `${Math.floor(diffMs / 3600000)} hours ago`
  if (diffMs < 604800000) return `${Math.floor(diffMs / 86400000)} days ago`

  return date.toLocaleDateString()
}
