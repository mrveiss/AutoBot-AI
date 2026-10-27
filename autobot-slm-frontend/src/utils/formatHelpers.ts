// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Shared byte / uptime / duration formatting utilities for the SLM frontend.
 *
 * The formatters are the kit's (`@autobot/ui`, #14908); this module keeps the import path
 * the SLM's callers already use.
 * Date/time formatting lives in `dateUtils.ts` / `useTimezone`.
 *
 * @module formatHelpers
 */

export type { DurationStyle } from '@autobot/ui'
// Byte, uptime and duration formatting live once in the kit (#14908).
export { formatDuration, formatUptime, formatFileSize, formatBytes, type FormatDurationOptions, type FormatUptimeOptions, type FormatBytesOptions } from '@autobot/ui'
