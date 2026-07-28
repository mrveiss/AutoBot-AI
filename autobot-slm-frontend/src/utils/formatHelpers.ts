// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared byte / uptime / duration formatting utilities for the SLM frontend.
 *
 * Mirrors the canonical `autobot-frontend/src/utils/formatHelpers.ts` helpers so
 * both frontends share identical, parameterized formatting behavior (#12737).
 * Date/time formatting lives in `dateUtils.ts` / `useTimezone`.
 *
 * @module formatHelpers
 */

// ==================== DURATION FORMATTING ====================

/**
 * Numeric duration formatting style (see canonical formatHelpers for details).
 * - `msSeconds2dp`  (ms): `<1000` → "{n}ms" (0 decimals), else "{n/1000}s" (2 decimals)
 * - `secondsCompact` (s): `<1` → "{n*1000}ms", `<60` → "{n}s" (1 decimal),
 *                          else "{floor(n/60)}m {round(n%60)}s"
 * - `clock`          (s): "M:SS"
 * - `msMinutes`     (ms): `<1000` → "{n}ms" (raw), `<60000` → "{n/1000}s" (1 decimal),
 *                          else "{n/60000}m"
 */
export type DurationStyle = 'msSeconds2dp' | 'secondsCompact' | 'clock' | 'msMinutes'

/** Options for the numeric form of {@link formatDuration}. */
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
 * Range form: `formatDuration(startTime, endTime)` (ISO strings).
 * Numeric form: `formatDuration(value, { style, ... })` (see {@link DurationStyle}).
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
  if (b !== null && typeof b === 'object') {
    return formatDurationValue(a as number | null | undefined, b)
  }

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

/** Options for {@link formatUptime}. */
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

/** Options for {@link formatFileSize} / {@link formatBytes}. */
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

/** Alias for formatFileSize (backward compatibility). */
export const formatBytes = formatFileSize
