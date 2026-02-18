/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * TypeScript types for Audit Logging Dashboard
 * Issue #578 - Audit Logging Dashboard GUI Integration
 */

/**
 * Audit result types matching backend AuditResult enum
 */
export type AuditResult = 'success' | 'denied' | 'failed' | 'error'

/**
 * Single audit log entry from backend
 */
export interface AuditEntry {
  id: string
  timestamp: string
  operation: string
  result: AuditResult
  user_id: string | null
  session_id: string | null
  vm_name: string | null
  vm_source: string | null
  details: Record<string, unknown>
  error_message: string | null
  ip_address: string | null
  user_agent: string | null
}

/**
 * Query parameters for audit logs
 */
export interface AuditQueryParams {
  start_time?: string
  end_time?: string
  operation?: string
  user_id?: string
  session_id?: string
  vm_name?: string
  result?: AuditResult
  limit?: number
  offset?: number
}

/**
 * Audit log query response from backend
 */
export interface AuditQueryResponse {
  success: boolean
  total_returned: number
  has_more: boolean
  entries: AuditEntry[]
  query: AuditQueryParams
}

/**
 * Audit statistics response from backend
 */
export interface AuditStatisticsResponse {
  success: boolean
  statistics: AuditStatistics
  vm_info: {
    vm_source: string
    vm_name: string
  }
}

/**
 * Audit statistics data structure
 */
export interface AuditStatistics {
  total_entries: number
  success_count: number
  denied_count: number
  failed_count: number
  error_count: number
  success_rate: number
  operations_by_type: Record<string, number>
  entries_by_hour: Record<string, number>
  top_users: Array<{ user_id: string; count: number }>
  top_operations: Array<{ operation: string; count: number }>
}

/**
 * Cleanup request payload
 */
export interface AuditCleanupRequest {
  days_to_keep: number
  confirm: boolean
}

/**
 * Cleanup response from backend
 */
export interface AuditCleanupResponse {
  success: boolean
  message: string
  days_retained: number
}

/**
 * Operation categories response from backend
 */
export interface AuditOperationsResponse {
  success: boolean
  categories: Record<string, string[]>
  total_operations: number
}

/**
 * Filter state for audit logs UI
 */
export interface AuditFilter {
  dateRange: 'today' | 'week' | 'month' | 'custom'
  startDate: string | null
  endDate: string | null
  operation: string | null
  userId: string | null
  sessionId: string | null
  vmName: string | null
  result: AuditResult | null
  limit: number
}

/**
 * Status display configuration for audit results
 */
export interface AuditResultConfig {
  label: string
  color: string
  icon: string
  bgClass: string
  textClass: string
}

/**
 * Map of audit results to display configuration
 */
export const AUDIT_RESULT_CONFIG: Record<AuditResult, AuditResultConfig> = {
  success: {
    label: 'Success',
    color: 'green',
    icon: 'fas fa-check-circle',
    bgClass: 'bg-green-100',
    textClass: 'text-green-700'
  },
  denied: {
    label: 'Denied',
    color: 'red',
    icon: 'fas fa-ban',
    bgClass: 'bg-red-100',
    textClass: 'text-red-700'
  },
  failed: {
    label: 'Failed',
    color: 'orange',
    icon: 'fas fa-times-circle',
    bgClass: 'bg-orange-100',
    textClass: 'text-orange-700'
  },
  error: {
    label: 'Error',
    color: 'yellow',
    icon: 'fas fa-exclamation-triangle',
    bgClass: 'bg-yellow-100',
    textClass: 'text-yellow-700'
  }
}

/**
 * Default filter values
 */
export const DEFAULT_AUDIT_FILTER: AuditFilter = {
  dateRange: 'today',
  startDate: null,
  endDate: null,
  operation: null,
  userId: null,
  sessionId: null,
  vmName: null,
  result: null,
  limit: 100
}

/**
 * Helper to format audit timestamp to readable string
 */
export function formatAuditTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString()
}

/**
 * Helper to format audit timestamp to relative time
 */
export function formatAuditRelativeTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  if (diffMs < 60000) return 'Just now'
  if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)} min ago`
  if (diffMs < 86400000) return `${Math.floor(diffMs / 3600000)} hours ago`
  if (diffMs < 604800000) return `${Math.floor(diffMs / 86400000)} days ago`

  return date.toLocaleDateString()
}

/**
 * Helper to calculate success rate percentage
 */
export function calculateSuccessRate(stats: AuditStatistics): number {
  if (stats.total_entries === 0) return 0
  return Math.round((stats.success_count / stats.total_entries) * 100)
}

/**
 * Helper to get date range for filter
 */
export function getDateRangeForFilter(
  range: AuditFilter['dateRange']
): { start: Date; end: Date } {
  const now = new Date()
  const end = new Date(now)
  let start: Date

  switch (range) {
    case 'today':
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      break
    case 'week':
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      break
    case 'month':
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      break
    default:
      start = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  }

  return { start, end }
}
