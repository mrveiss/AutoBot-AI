// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Format Helper Utilities
 *
 * Centralized formatting functions for dates, times, file sizes, and other common display formats.
 * This module eliminates duplicate implementations across 33+ components.
 *
 * Migration Status: Phase 1 - Created shared utility
 * Replaces: 23 formatDate/Time + 10 formatFileSize duplicate implementations
 *
 * @module formatHelpers
 */

// ==================== DATE & TIME FORMATTING ====================

/**
 * Format date to localized date string
 *
 * Handles multiple input types and provides safe fallback behavior.
 * Consolidates 23 different implementations across the codebase.
 *
 * @param dateInput - Date, ISO string, or undefined
 * @param options - Optional Intl.DateTimeFormat options
 * @returns Formatted date string or empty string if invalid
 *
 * @example
 * ```typescript
 * formatDate('2025-10-30T18:05:00Z') // "10/30/2025"
 * formatDate(new Date()) // "10/30/2025"
 * formatDate(undefined) // ""
 * ```
 */
export function formatDate(
  dateInput: string | Date | undefined | null,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!dateInput) return ''

  try {
    const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput

    // Validate date
    if (!(date instanceof Date) || isNaN(date.getTime())) {
      return ''
    }

    return date.toLocaleDateString(undefined, options)
  } catch {
    return ''
  }
}

/**
 * Format time to localized time string (HH:MM format)
 *
 * @param timestamp - Date, ISO string, or undefined
 * @param use24Hour - Use 24-hour format (default: false)
 * @returns Formatted time string (e.g., "2:30 PM" or "14:30")
 *
 * @example
 * ```typescript
 * formatTime('2025-10-30T14:30:00Z') // "2:30 PM"
 * formatTime(new Date(), true) // "14:30"
 * ```
 */
export function formatTime(
  timestamp: Date | string | undefined | null,
  use24Hour: boolean = false
): string {
  if (!timestamp) return ''

  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp

    // Validate date
    if (!(date instanceof Date) || isNaN(date.getTime())) {
      // Fallback to current time
      return new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        hour12: !use24Hour
      })
    }

    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: !use24Hour
    })
  } catch {
    return ''
  }
}

/**
 * Format date and time together
 *
 * @param timestamp - Date or ISO string
 * @param options - Optional Intl.DateTimeFormat options
 * @returns Formatted date and time string
 *
 * @example
 * ```typescript
 * formatDateTime('2025-10-30T14:30:00Z') // "10/30/2025, 2:30 PM"
 * ```
 */
export function formatDateTime(
  timestamp: Date | string | undefined | null,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!timestamp) return ''

  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp

    // Validate date
    if (!(date instanceof Date) || isNaN(date.getTime())) {
      return ''
    }

    const defaultOptions: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      ...options
    }

    return date.toLocaleString(undefined, defaultOptions)
  } catch {
    return ''
  }
}

/**
 * Format ISO string to locale string (backward compatibility helper)
 *
 * @param isoString - ISO 8601 date string
 * @returns Formatted locale string
 *
 * @example
 * ```typescript
 * formatISOString('2025-10-30T14:30:00Z') // "10/30/2025, 2:30:00 PM"
 * ```
 */
export function formatISOString(isoString: string | undefined | null): string {
  if (!isoString) return ''

  try {
    const date = new Date(isoString)
    if (isNaN(date.getTime())) return isoString
    return date.toLocaleString()
  } catch {
    return isoString || ''
  }
}

/**
 * Format relative time (e.g., "2 hours ago")
 *
 * @param timestamp - Date or ISO string
 * @returns Relative time string
 *
 * @example
 * ```typescript
 * formatTimeAgo(Date.now() - 3600000) // "1 hour ago"
 * formatTimeAgo(Date.now() - 86400000) // "1 day ago"
 * ```
 */
export function formatTimeAgo(timestamp: Date | string | number): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) :
                 typeof timestamp === 'number' ? new Date(timestamp) : timestamp

    if (!(date instanceof Date) || isNaN(date.getTime())) {
      return 'unknown'
    }

    const seconds = Math.floor((Date.now() - date.getTime()) / 1000)

    if (seconds < 60) return 'just now'
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`
    if (seconds < 604800) return `${Math.floor(seconds / 86400)} days ago`
    if (seconds < 2592000) return `${Math.floor(seconds / 604800)} weeks ago`
    if (seconds < 31536000) return `${Math.floor(seconds / 2592000)} months ago`
    return `${Math.floor(seconds / 31536000)} years ago`
  } catch {
    return 'unknown'
  }
}

// ==================== DURATION FORMATTING ====================

/**
 * Numeric duration formatting style.
 *
 * Each style reproduces the exact rendered output of a group of former local
 * `formatDuration` copies (see #12737 fork-convergence). Input unit is implied
 * by the style:
 * - `msSeconds2dp`  (ms): `<1000` → "{n}ms" (0 decimals), else "{n/1000}s" (2 decimals)
 * - `secondsCompact` (s): `<1` → "{n*1000}ms", `<60` → "{n}s" (1 decimal),
 *                          else "{floor(n/60)}m {round(n%60)}s"
 * - `clock`          (s): "M:SS" (minutes:zero-padded-seconds)
 * - `msMinutes`     (ms): `<1000` → "{n}ms" (raw), `<60000` → "{n/1000}s" (1 decimal),
 *                          else "{n/60000}m"
 */
export type DurationStyle = 'msSeconds2dp' | 'secondsCompact' | 'clock' | 'msMinutes'

/**
 * Options for the numeric ({@link DurationStyle}) form of {@link formatDuration}.
 */
export interface FormatDurationOptions {
  /** Selects the numeric formatting style / input unit. */
  style: DurationStyle
  /** Text for null / undefined / NaN input (default `'—'`). */
  nullText?: string
  /** Text for an exact zero value; when omitted, zero follows the normal ladder. */
  zeroText?: string
  /** Rounding for the top tier of `clock` / `msMinutes` styles (default `'round'`). */
  rounding?: 'round' | 'floor'
}

/**
 * Format a numeric duration in the given {@link DurationStyle}.
 * Internal helper backing the numeric overload of {@link formatDuration}.
 */
function formatDurationValue(
  value: number | null | undefined,
  options: FormatDurationOptions
): string {
  const nullText = options.nullText ?? '—'
  if (value === null || value === undefined || Number.isNaN(value)) return nullText
  if (value === 0 && options.zeroText !== undefined) return options.zeroText

  const roundFn = options.rounding === 'floor' ? Math.floor : Math.round

  switch (options.style) {
    case 'msSeconds2dp':
      if (value < 1000) return `${value.toFixed(0)}ms`
      return `${(value / 1000).toFixed(2)}s`
    case 'secondsCompact':
      if (value < 1) return `${Math.round(value * 1000)}ms`
      if (value < 60) return `${value.toFixed(1)}s`
      return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`
    case 'clock': {
      const total = roundFn(value)
      const mins = Math.floor(total / 60)
      const secs = total % 60
      return `${mins}:${secs.toString().padStart(2, '0')}`
    }
    case 'msMinutes':
      if (value < 1000) return `${value}ms`
      if (value < 60000) return `${(value / 1000).toFixed(1)}s`
      return `${roundFn(value / 60000)}m`
    default:
      return nullText
  }
}

/**
 * Format a duration in human-readable form.
 *
 * Two forms:
 * 1. **Range** (ISO timestamps): `formatDuration(startTime, endTime)` — renders
 *    "{ms}ms" / "{s}s" / "{m}m {s}s" / "{h}h {m}m", or `'-'` when no start.
 * 2. **Numeric** ({@link DurationStyle}): `formatDuration(value, { style, ... })` —
 *    formats a single ms/seconds value, reproducing each converged call site's
 *    exact output (see {@link DurationStyle}).
 *
 * @example
 * ```typescript
 * formatDuration('2025-01-01T00:00:00Z', '2025-01-01T00:01:30Z') // "1m 30s"
 * formatDuration(null, null) // "-"
 * formatDuration(1500, { style: 'msSeconds2dp' }) // "1.50s"
 * formatDuration(90, { style: 'clock' }) // "1:30"
 * ```
 */
export function formatDuration(
  startTime: string | null | undefined,
  endTime: string | null | undefined
): string
export function formatDuration(
  value: number | null | undefined,
  options: FormatDurationOptions
): string
export function formatDuration(
  a: string | number | null | undefined,
  b?: string | null | undefined | FormatDurationOptions
): string {
  // Numeric form: second argument is an options object.
  if (b !== null && typeof b === 'object') {
    return formatDurationValue(a as number | null | undefined, b)
  }

  // Range form (unchanged legacy behavior).
  const startTime = a as string | null | undefined
  const endTime = b as string | null | undefined
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

// ==================== UPTIME FORMATTING ====================

/**
 * Options for {@link formatUptime}.
 */
export interface FormatUptimeOptions {
  /** Text for null / undefined / NaN / negative input (default `'—'`). */
  nullText?: string
  /** Text for an exact zero value; when omitted, zero renders as `'0m'`. */
  zeroText?: string
  /** Include minutes on the days line (`'Xd Yh Zm'` vs `'Xd Yh'`) (default `false`). */
  daysIncludeMinutes?: boolean
}

/**
 * Format an uptime given in seconds as a coarse `d`/`h`/`m` string.
 *
 * Renders `'Xd Yh'` when days > 0 (or `'Xd Yh Zm'` with `daysIncludeMinutes`),
 * `'Yh Zm'` when hours > 0, otherwise `'Zm'`.
 *
 * @example
 * ```typescript
 * formatUptime(0)      // "0m"
 * formatUptime(3661)   // "1h 1m"
 * formatUptime(90061)  // "1d 1h"
 * ```
 */
export function formatUptime(
  seconds: number | null | undefined,
  options: FormatUptimeOptions = {}
): string {
  const nullText = options.nullText ?? '—'
  if (seconds === null || seconds === undefined || Number.isNaN(seconds) || seconds < 0) {
    return nullText
  }
  if (seconds === 0 && options.zeroText !== undefined) return options.zeroText

  const total = Math.floor(seconds)
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const mins = Math.floor((total % 3600) / 60)

  if (days > 0) {
    return options.daysIncludeMinutes ? `${days}d ${hours}h ${mins}m` : `${days}d ${hours}h`
  }
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

// ==================== FILE SIZE FORMATTING ====================

/**
 * Options for {@link formatFileSize} / {@link formatBytes}.
 *
 * Defaults reproduce the canonical output exactly: trimmed decimals (via
 * `parseFloat`), a `'Bytes'`-based ladder, `'0 Bytes'` for zero and `'Invalid'`
 * for negatives. Options let each converged call site reproduce its own output.
 */
export interface FormatBytesOptions {
  /** Decimal places for scaled units (default `2`). */
  decimals?: number
  /** Unit ladder (default `['Bytes','KB','MB','GB','TB','PB']`). */
  units?: readonly string[]
  /** Text for a zero-byte value (default `'0 ' + units[0]`). */
  zeroText?: string
  /** Text for negative values (default `'Invalid'`). */
  invalidText?: string
  /** Text for null / undefined input (default same as `invalidText`). */
  nullText?: string
  /** Keep trailing zeros instead of trimming via `parseFloat` (default `false`). */
  keepTrailingZeros?: boolean
  /** Render the base unit (`units[0]`) as an integer with no decimals (default `false`). */
  integerBase?: boolean
}

const DEFAULT_BYTE_UNITS = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB'] as const

/**
 * Format bytes to a human-readable file size.
 *
 * Consolidates many local implementations across both frontends (#12737).
 *
 * @param bytes - File size in bytes
 * @param decimalsOrOptions - Decimal places (number) or {@link FormatBytesOptions}
 * @returns Formatted file size string (e.g., "1.5 MB")
 *
 * @example
 * ```typescript
 * formatFileSize(0) // "0 Bytes"
 * formatFileSize(1024) // "1 KB"
 * formatFileSize(1536) // "1.5 KB"
 * formatFileSize(1048576) // "1 MB"
 * formatFileSize(1024, { units: ['B','KB','MB'], zeroText: '0 B' }) // "1 KB"
 * ```
 */
export function formatFileSize(
  bytes: number | null | undefined,
  decimalsOrOptions: number | FormatBytesOptions = 2
): string {
  const opts: FormatBytesOptions =
    typeof decimalsOrOptions === 'number' ? { decimals: decimalsOrOptions } : decimalsOrOptions

  const units = opts.units ?? DEFAULT_BYTE_UNITS
  const invalidText = opts.invalidText ?? 'Invalid'
  const zeroText = opts.zeroText ?? `0 ${units[0]}`

  if (bytes === null || bytes === undefined) return opts.nullText ?? invalidText
  if (bytes === 0) return zeroText
  if (bytes < 0) return invalidText

  const k = 1024
  const decimals = opts.decimals ?? 2
  const dm = decimals < 0 ? 0 : decimals

  const i = Math.floor(Math.log(bytes) / Math.log(k))
  // Prevent array overflow for extremely large numbers
  const sizeIndex = Math.min(i, units.length - 1)
  const value = bytes / Math.pow(k, sizeIndex)

  let text: string
  if (opts.integerBase && sizeIndex === 0) {
    text = String(bytes)
  } else if (opts.keepTrailingZeros) {
    text = value.toFixed(dm)
  } else {
    text = String(parseFloat(value.toFixed(dm)))
  }

  return `${text} ${units[sizeIndex]}`
}

/**
 * Alias for formatFileSize (backward compatibility)
 */
export const formatBytes = formatFileSize

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
  formatTimeAgo,
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
