// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — byte, uptime, duration and date/time formatting for both apps (#14908, #19905).
 *
 * Each app had its own copy; the SLM one was an exact subset of the user app's, so the
 * shared part lives here once and each app's `utils/formatHelpers.ts` re-exports it.
 * A timezone is passed per call (`intl: { timeZone }`), so an app that stores one keeps that
 * state itself and the formatting still lives here.
 *
 * The default texts ('—', 'Invalid', the unit names) are English fallbacks. A caller that
 * shows them to a user passes translated `nullText` / `invalidText` / `zeroText` / `units`.
 */
import type { DurationStyle } from './duration'

/** Options for the numeric form of {@link formatDuration}. */
export interface FormatDurationOptions {
  /** Selects the numeric formatting style / input unit. */
  style: DurationStyle
  /** Text for null / undefined / NaN input (default `'—'`). */
  nullText?: string
  /** Text for an exact zero value; when omitted, zero follows the normal ladder. */
  zeroText?: string
  /** Rounding for the top tier of `clock` / `msMinutes` styles and the seconds of `msMinutesSeconds` (default `'round'`). */
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
    case 'msSeconds1dp':
      if (value < 1000) return `${Math.round(value)}ms`
      return `${(value / 1000).toFixed(1)}s`
    case 'msSecondsMinutes': {
      if (value < 1000) return `${Math.round(value)}ms`
      if (value < 60000) return `${(value / 1000).toFixed(1)}s`
      return `${Math.floor(value / 60000)}m ${Math.floor((value % 60000) / 1000)}s`
    }
    case 'msMinutesSeconds': {
      const secs = Math.max(0, roundFn(value / 1000))
      return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`
    }
    case 'msCompound': {
      const secs = Math.max(0, Math.floor(value / 1000))
      if (secs < 60) return `${secs}s`
      const mins = Math.floor(secs / 60)
      if (mins < 60) return `${mins}m ${secs % 60}s`
      return `${Math.floor(mins / 60)}h ${mins % 60}m`
    }
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
  startTime: string | null | undefined,
  endTime: string | null | undefined,
  options: FormatDurationOptions
): string
export function formatDuration(
  value: number | null | undefined,
  options: FormatDurationOptions
): string
export function formatDuration(
  a: string | number | null | undefined,
  b?: string | null | undefined | FormatDurationOptions,
  c?: FormatDurationOptions
): string {
  if (c) {
    // Range form in a numeric style: a missing start reads as the null text, a negative
    // span (clock skew) as zero.
    if (!a) return c.nullText ?? '-'
    const to = b ? new Date(b as string).getTime() : Date.now()
    return formatDurationValue(Math.max(0, to - new Date(a as string).getTime()), c)
  }
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
  /** Decimal places for scaled units, or one per unit tier (default `2`). */
  decimals?: number | readonly number[]
  /** Unit ladder (default `['Bytes','KB','MB','GB','TB','PB']`). */
  units?: readonly string[]
  /** Text for a zero-byte value (default `'0 ' + units[0]`). */
  zeroText?: string
  /** Text for negative values (default `'Invalid'`). */
  invalidText?: string
  /** Text for null / undefined input (default same as `invalidText`). */
  nullText?: string
  /** Separator between the number and the unit (default `' '`). */
  separator?: string
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
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const sizeIndex = Math.min(i, units.length - 1)
  const decimals = Array.isArray(opts.decimals)
    ? (opts.decimals[sizeIndex] ?? 2)
    : ((opts.decimals as number | undefined) ?? 2)
  const dm = decimals < 0 ? 0 : decimals
  const value = bytes / Math.pow(k, sizeIndex)

  let text: string
  if (opts.integerBase && sizeIndex === 0) {
    text = String(bytes)
  } else if (opts.keepTrailingZeros) {
    text = value.toFixed(dm)
  } else {
    text = String(parseFloat(value.toFixed(dm)))
  }

  return `${text}${opts.separator ?? ' '}${units[sizeIndex]}`
}

/** Alias for formatFileSize (backward compatibility). */
export const formatBytes = formatFileSize

// ==================== DATE & TIME FORMATTING ====================

/** Anything the date formatters accept. A number is milliseconds unless `unit: 'seconds'`. */
export type DateInput = Date | string | number | null | undefined

/** `Intl` fields of {@link formatDateTime} when the caller passes none. */
export const DEFAULT_DATE_TIME_INTL: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit'
}

function toValidDate(input: DateInput): Date | null {
  if (input === null || input === undefined || input === '') return null
  const date = input instanceof Date ? input : new Date(input)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Format a date as a localized date string; empty string when missing or invalid. */
export function formatDate(
  dateInput: string | Date | undefined | null,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = toValidDate(dateInput)
  return date ? date.toLocaleDateString(undefined, options) : ''
}

/** Format a time as `HH:MM` (12-hour unless `use24Hour`); an invalid value reads as now. */
export function formatTime(
  timestamp: Date | string | undefined | null,
  use24Hour: boolean = false
): string {
  if (!timestamp) return ''
  const date = toValidDate(timestamp) ?? new Date()
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: !use24Hour })
}

/** Format date and time together; `options` override {@link DEFAULT_DATE_TIME_INTL}. */
export function formatDateTime(
  timestamp: Date | string | undefined | null,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = toValidDate(timestamp)
  return date ? date.toLocaleString(undefined, { ...DEFAULT_DATE_TIME_INTL, ...options }) : ''
}

/** Format an ISO string with the browser's default locale string; an invalid one is returned as-is. */
export function formatISOString(isoString: string | undefined | null): string {
  if (!isoString) return ''
  return toValidDate(isoString)?.toLocaleString() ?? isoString
}

/** Unit sizes in seconds, largest first, for {@link formatTimeAgo}. */
const AGO_UNITS: ReadonlyArray<readonly [number, string]> = [
  [31536000, 'years'],
  [2592000, 'months'],
  [604800, 'weeks'],
  [86400, 'days'],
  [3600, 'hours'],
  [60, 'minutes']
]

/** Format a moment as English relative time (`2 hours ago`); `'unknown'` when invalid. */
export function formatTimeAgo(timestamp: Date | string | number): string {
  const date = toValidDate(timestamp)
  if (!date) return 'unknown'
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  const unit = AGO_UNITS.find(([size]) => seconds >= size)
  return unit ? `${Math.floor(seconds / unit[0])} ${unit[1]} ago` : 'just now'
}

/** Options for {@link createDateFormatter}. */
export interface DateFormatterOptions {
  /** Which part to show (default `'dateTime'`). */
  kind?: 'date' | 'time' | 'dateTime'
  /** BCP 47 locale; default is the browser's. */
  locale?: string
  /** `Intl` fields, or a function returning them (for a timezone that can change). */
  intl?: Intl.DateTimeFormatOptions | (() => Intl.DateTimeFormatOptions)
  /** Unit of a numeric input (default `'ms'`). */
  unit?: 'ms' | 'seconds'
  /** Text for null / undefined / empty input (default `''`); a function is read per call. */
  emptyText?: string | (() => string)
  /** Text for an unparseable input (default: the input as a string). */
  invalidText?: string
}

function toLocaleText(date: Date, options: DateFormatterOptions): string {
  const intl = typeof options.intl === 'function' ? options.intl() : options.intl
  if (options.kind === 'date') return date.toLocaleDateString(options.locale, intl)
  if (options.kind === 'time') return date.toLocaleTimeString(options.locale, intl)
  return date.toLocaleString(options.locale, intl)
}

/**
 * Build a date formatter with fixed fields. It replaces a component's own
 * `new Date(x).toLocale…String(…)` helper without changing the fields it showed.
 */
export function createDateFormatter(
  options: DateFormatterOptions = {}
): (input: DateInput) => string {
  return (input) => {
    if (input === null || input === undefined || input === '') {
      const empty = options.emptyText
      return typeof empty === 'function' ? empty() : (empty ?? '')
    }
    const ms = typeof input === 'number' && options.unit === 'seconds' ? input * 1000 : input
    const date = toValidDate(ms)
    return date ? toLocaleText(date, options) : (options.invalidText ?? String(input))
  }
}
