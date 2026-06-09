// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared date/time formatting utilities.
 *
 * Extracted from FleetOverview, NodeLifecyclePanel, NodeServicesPanel,
 * ErrorMonitor, and SecurityView to eliminate duplication (Issue #3314).
 */

/**
 * Formats a timestamp as a human-readable relative time string.
 *
 * @param ts - ISO 8601 timestamp, or null/undefined if unknown.
 * @returns A relative string such as `5s ago`, `3m ago`, `2h ago`, `4d ago`,
 *          or `'—'` when the value is absent or unparseable.
 */
export function formatRelativeTime(ts: string | null | undefined): string {
  if (!ts) return '—'
  const date = new Date(ts)
  if (isNaN(date.getTime())) return '—'

  const diffMs = Date.now() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}
