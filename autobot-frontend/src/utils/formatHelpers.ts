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

// ==================== FILE SIZE FORMATTING ====================

/**
 * Format bytes to human-readable file size
 *
 * Consolidates 10 different implementations across the codebase.
 *
 * @param bytes - File size in bytes
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted file size string (e.g., "1.5 MB")
 *
 * @example
 * ```typescript
 * formatFileSize(0) // "0 Bytes"
 * formatFileSize(1024) // "1 KB"
 * formatFileSize(1536) // "1.5 KB"
 * formatFileSize(1048576) // "1 MB"
 * ```
 */
export function formatFileSize(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return '0 Bytes'
  if (bytes < 0) return 'Invalid'

  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB']

  const i = Math.floor(Math.log(bytes) / Math.log(k))

  // Prevent array overflow for extremely large numbers
  const sizeIndex = Math.min(i, sizes.length - 1)

  return parseFloat((bytes / Math.pow(k, sizeIndex)).toFixed(dm)) + ' ' + sizes[sizeIndex]
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

  return category
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
