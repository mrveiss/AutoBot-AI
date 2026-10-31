// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared date / time / byte / uptime / duration formatting for the SLM frontend.
 *
 * The formatters are the kit's (`@autobot/ui`, #14908); this module keeps the import path
 * the SLM's callers already use.
 * Timezone-aware date text is `useTimezone`'s `formatDateTime`, built on the kit's formatter.
 *
 * @module formatHelpers
 */

export type { DurationStyle } from '@autobot/ui'
// Byte, uptime and duration formatting live once in the kit (#14908).
export { formatDuration, formatUptime, formatFileSize, formatBytes, type FormatDurationOptions, type FormatUptimeOptions, type FormatBytesOptions } from '@autobot/ui'
export {
  formatDate,
  formatTime,
  formatDateTime,
  formatISOString,
  formatTimeAgo,
  createDateFormatter,
  DEFAULT_DATE_TIME_INTL,
  type DateInput,
  type DateFormatterOptions
} from '@autobot/ui'
