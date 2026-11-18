// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * TypeScript types for Audit Logging Dashboard
 * Issue #578 - Audit Logging Dashboard GUI Integration
 */

import type { AuditQueryResponse } from '@autobot/ui'

/**
 * Audit result types matching backend AuditResult enum
 */
import type { IconName } from '@/components/ui/Icon.vue'
import type { components } from '@/types/generated/api'

export type AuditResult = 'success' | 'denied' | 'failed' | 'error' | 'attempted'

/**
 * Whether each result is still unfinished. Typed against {@link AuditResult}, so a new member cannot be
 * added without deciding which side it is on (#20665).
 */
const UNFINISHED_RESULT: Record<AuditResult, boolean> = {
  success: false,
  denied: false,
  failed: false,
  error: false,
  attempted: true,
}

/**
 * Whether an audit row's outcome is final. An `attempted` row records that an operation began, not how
 * it ended, so it counts neither as a success nor as a failure. The wire row types `result` as a plain
 * string, hence the parameter; a value outside {@link AuditResult} is not an unfinished claim.
 */
export function isTerminalAuditResult(result: string): boolean {
  return UNFINISHED_RESULT[result as AuditResult] !== true
}

/**
 * One row as `GET /audit/logs` sends it: the generated `AuditEntryResponse`
 * (backend `api/schemas_audit.py`). `timestamp` is epoch SECONDS (a float),
 * the operation's data is in `details`, and there is no `metadata`,
 * `error_message` or `user_agent` field (#20173, #20176).
 */
export type AuditEntry = components['schemas']['AuditEntryResponse']

/** The API row under its wire-contract name; the same type as {@link AuditEntry}. */
export type AuditApiEntry = AuditEntry

/** An audit row's epoch-seconds timestamp as a Date (`new Date(seconds)` reads it as milliseconds). */
export function auditTimestampToDate(seconds: number): Date {
  return new Date(seconds * 1000)
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
 * Audit log query response from backend (envelope declared once in the kit, #20173)
 */
export type AuditDashboardResponse<E = AuditEntry> = AuditQueryResponse<E, AuditQueryParams>

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
  icon: IconName
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
    icon: 'check-circle',
    bgClass: 'bg-green-100',
    textClass: 'text-green-700'
  },
  denied: {
    label: 'Denied',
    color: 'red',
    icon: 'ban',
    bgClass: 'bg-red-100',
    textClass: 'text-red-700'
  },
  failed: {
    label: 'Failed',
    color: 'orange',
    icon: 'times-circle',
    bgClass: 'bg-orange-100',
    textClass: 'text-orange-700'
  },
  error: {
    label: 'Error',
    color: 'yellow',
    icon: 'exclamation-triangle',
    bgClass: 'bg-yellow-100',
    textClass: 'text-yellow-700'
  },
  attempted: {
    label: 'Attempted',
    color: 'blue',
    icon: 'clock',
    bgClass: 'bg-blue-100',
    textClass: 'text-blue-700'
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
 * The one definition of the success rate: successes as a whole percentage of the rows whose outcome is
 * final (see {@link isTerminalAuditResult}). With no final row there is no rate to speak of, so it is 0.
 */
export function calculateSuccessRate(successCount: number, terminalCount: number): number {
  if (terminalCount === 0) return 0
  return Math.round((successCount / terminalCount) * 100)
}

/** A server-sent figure when it is a finite number, else undefined. */
function served(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/**
 * The figures the statistics panel shows (#20665 AC3, #21513). A count or rate the server sent is used
 * as sent; one it did not send is derived from the loaded `entries`, which describes that window and
 * not the whole log. An `attempted` row is neither a success nor a failure: it is in no result count
 * and not in the rate's denominator ({@link isTerminalAuditResult}). Null when there is neither a
 * statistics object nor a row to derive from.
 */
export function resolveAuditStatistics(
  server: Partial<AuditStatistics> | null,
  entries: ReadonlyArray<{ result: string }>
): AuditStatistics | null {
  if (!server && entries.length === 0) return null
  const count = (result: AuditResult) => entries.filter((e) => e.result === result).length
  const success = served(server?.success_count) ?? count('success')
  const denied = served(server?.denied_count) ?? count('denied')
  const failed = served(server?.failed_count) ?? count('failed')
  const error = served(server?.error_count) ?? count('error')
  return {
    ...server,
    operations_by_type: server?.operations_by_type ?? {},
    entries_by_hour: server?.entries_by_hour ?? {},
    top_users: server?.top_users ?? [],
    top_operations: server?.top_operations ?? [],
    total_entries: served(server?.total_entries) ?? entries.length,
    success_count: success,
    denied_count: denied,
    failed_count: failed,
    error_count: error,
    // A rate the server did not send is derived from the SAME counts shown beside it (served or
    // loaded-window), so the panel never disagrees with itself; `attempted` is in no count.
    success_rate: served(server?.success_rate) ?? calculateSuccessRate(success, success + denied + failed + error),
  }
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
