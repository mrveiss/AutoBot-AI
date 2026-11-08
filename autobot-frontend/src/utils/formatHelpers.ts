// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Format Helper Utilities
 *
 * Display formatters for both apps. The date, time, duration, uptime and file-size formatters are
 * the kit's (`@autobot/ui`); this module keeps the import path callers already use.
 *
 * Migration Status: Phase 1 - Created shared utility
 * Replaces: 23 formatDate/Time + 10 formatFileSize duplicate implementations
 *
 * @module formatHelpers
 */

// The duration, uptime and byte formatters are the kit's (#14908); see below.
export type { DurationStyle } from '@autobot/ui'

// ==================== DATE & TIME FORMATTING ====================

// The date and time formatters live once in the kit (#19905).
import {
  formatDate,
  formatTime,
  formatDateTime,
  formatISOString,
  createDateFormatter,
  formatLocalTime,
  DEFAULT_DATE_TIME_INTL
} from '@autobot/ui'
export {
  formatDate,
  formatTime,
  formatDateTime,
  formatISOString,
  createDateFormatter,
  formatLocalTime,
  DEFAULT_DATE_TIME_INTL
}
export type { DateInput, DateFormatterOptions } from '@autobot/ui'

// ==================== DURATION, UPTIME AND FILE SIZE FORMATTING ====================

// Byte, uptime and duration formatting live once in the kit (#14908).
import { formatDuration, formatUptime, formatFileSize, formatBytes } from '@autobot/ui'
export { formatDuration, formatUptime, formatFileSize, formatBytes }

/**
 * File-browser size options: `1.5 KB` up to GB. `zeroText` is the text for a missing size; the
 * caller passes it from an i18n key (#19885), so the formatter holds no display literal.
 */
export function fileBrowserSizeOptions(zeroText: string) {
  return {
    decimals: 1,
    units: ['B', 'KB', 'MB', 'GB'],
    nullText: zeroText,
  } as const
}
export type { FormatDurationOptions, FormatUptimeOptions, FormatBytesOptions } from '@autobot/ui'

// ==================== NUMBER FORMATTING ====================

/**
 * Format number with thousands separators
 *
 * @param num - Number to format
 * @param decimals - Number of decimal places
 * @returns Formatted number string
 *
 * @example
 * ```typescript
 * formatNumber(1234567) // "1,234,567"
 * formatNumber(1234.5678, 2) // "1,234.57"
 * ```
 */
export function formatNumber(num: number, decimals?: number): string {
  if (typeof num !== 'number' || isNaN(num)) return '0'

  const options: Intl.NumberFormatOptions = {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }

  return num.toLocaleString(undefined, options)
}

/**
 * Format percentage
 *
 * @param value - Decimal value (0-1) or percentage (0-100)
 * @param decimals - Number of decimal places (default: 1)
 * @param isDecimal - If true, expects 0-1 range, otherwise 0-100
 * @returns Formatted percentage string
 *
 * @example
 * ```typescript
 * formatPercentage(0.75, 1, true) // "75.0%"
 * formatPercentage(75, 1, false) // "75.0%"
 * ```
 */
export function formatPercentage(
  value: number,
  decimals: number = 1,
  isDecimal: boolean = true
): string {
  const percent = isDecimal ? value * 100 : value
  return `${percent.toFixed(decimals)}%`
}

// ==================== STRING FORMATTING ====================

/**
 * Format category name (snake_case to Title Case)
 *
 * @param category - Category string (e.g., "system_commands")
 * @returns Formatted category name (e.g., "System Commands")
 *
 * @example
 * ```typescript
 * formatCategoryName('system_commands') // "System Commands"
 * formatCategoryName('auto_bot_docs') // "Auto Bot Docs"
 * ```
 */
export function formatCategoryName(category: string): string {
  if (!category) return ''

  // #10208: this shared formatter is called across knowledge/analytics views
  // with backend-sourced category values that aren't guaranteed strings at
  // runtime (a non-string would throw "e.split is not a function" and crash
  // the component into its ErrorBoundary). Coerce so .split() is always safe.
  return String(category)
    .split(/[_-]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Truncate string with ellipsis
 *
 * @param str - String to truncate
 * @param maxLength - Maximum length before truncation
 * @param suffix - Suffix to add (default: "...")
 * @returns Truncated string
 *
 * @example
 * ```typescript
 * truncateString('Hello World', 5) // "Hello..."
 * truncateString('Short', 10) // "Short"
 * ```
 */
export function truncateString(str: string, maxLength: number, suffix: string = '...'): string {
  if (!str || str.length <= maxLength) return str
  return str.substring(0, maxLength) + suffix
}

// ==================== EXPORTS ====================

/**
 * Export all formatting functions
 */
export default {
  // Date & Time
  formatDate,
  formatTime,
  formatDateTime,
  formatISOString,
  formatDuration,
  formatUptime,

  // File Size
  formatFileSize,
  formatBytes,

  // Numbers
  formatNumber,
  formatPercentage,

  // Strings
  formatCategoryName,
  truncateString
}

// ---------------------------------------------------------------------------
// Knowledge-base fact titles (#21037). DISPLAY ONLY: the stored title and the
// idempotency key never change; sorting and searching keep using the raw title.
// A man-page fact is stored as `gettext(1)` / `man gettext(1)`; users read the
// `(1)` as a duplicate counter, so it is shown as "gettext, section 1: user commands".
// ---------------------------------------------------------------------------

type TranslateFn = (key: string, params?: Record<string, unknown>) => string

/** Fact `type` values the backend writes for man-page facts (`man_page_parser` / `knowledge_population`). */
const MAN_PAGE_TYPES = new Set(['man_page', 'manual_page'])

/** `name(N)` with an optional leading `man `; N may carry a letter suffix (3p). */
const MAN_TITLE_PATTERN = /^(?:man\s+)?(\S+?)\((\d+[a-z]*)\)$/i

/** Standard man sections that have an i18n name (`knowledge.manSection.<N>`). */
const KNOWN_SECTIONS = new Set(['1', '2', '3', '4', '5', '6', '7', '8', '9'])

/**
 * Return the display title for a fact. `kind` is the fact's `type`
 * (`metadata.type` / `document.type`); a title is only reinterpreted when the
 * fact is identified as a man page, never from the `name(N)` shape alone.
 */
export function formatManPageTitle(
  title: string | null | undefined,
  kind: unknown,
  t: TranslateFn,
): string {
  const raw = title ?? ''
  if (typeof kind !== 'string' || !MAN_PAGE_TYPES.has(kind)) return raw
  const match = MAN_TITLE_PATTERN.exec(raw.trim())
  if (!match) return raw
  const [, name, section] = match
  if (!KNOWN_SECTIONS.has(section)) {
    return t('knowledge.manSection.formatUnnamed', { name, section })
  }
  return t('knowledge.manSection.format', {
    name,
    section,
    sectionName: t(`knowledge.manSection.${section}`),
  })
}

/**
 * The fact `type` of a knowledge-browser tree node. A node built from
 * `GET /facts/by_category` carries the fact's metadata flat (`metadata.type`);
 * a node lazy-loaded from `POST /search` carries the whole search hit, whose
 * metadata is nested (`metadata.metadata.type`).
 */
export function knowledgeNodeFactType(metadata: { type?: unknown; metadata?: unknown } | undefined): unknown {
  const hit = metadata?.metadata
  if (hit && typeof hit === 'object') return (hit as { type?: unknown }).type
  return metadata?.type
}
