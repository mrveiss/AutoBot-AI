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

import { formatRelativeTime, type DateInput } from '@autobot/ui'
import i18n from '@/i18n'

// The kit's formatter is the one home of relative time (#19606); this is its public name here.
export { formatRelativeTime }

/**
 * The compact relative time the SLM tables show (`5s ago`, `3m ago`, `2h ago`, `4d ago`),
 * localised by `Intl.RelativeTimeFormat` in the app's current locale.
 *
 * @param ts - ISO 8601 timestamp (or a Date / epoch ms), or null/undefined if unknown.
 * @returns The relative text, or `'—'` when the value is absent or unparseable.
 */
export const formatCompactRelativeTime = (ts: DateInput): string =>
  formatRelativeTime(ts, { locale: i18n.global.locale, style: 'narrow', maxUnit: 'day' })
