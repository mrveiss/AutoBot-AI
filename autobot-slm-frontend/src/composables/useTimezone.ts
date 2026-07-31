// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Timezone Composable
 *
 * Fetches the configured timezone from /api/settings/time/config and provides
 * timezone-aware date formatting. Caches the timezone in a module-level ref
 * so all components share the same value without redundant fetches.
 */

import { ref } from 'vue'
import { getTimeConfig } from '@/utils/slmSettingsApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useTimezone')

/** Module-level cache — shared across all component instances */
const cachedTimezone = ref<string | null>(null)
let fetchPromise: Promise<void> | null = null

async function loadTimezone(): Promise<void> {
  try {
    // #13140: routed through the canonical SLM client (base URL, token
    // fallback, timeout, 401 handling) instead of a hand-built fetch. The
    // "unavailable -> keep the browser locale" contract is preserved: a
    // non-OK response yields null rather than throwing.
    const data = await getTimeConfig()
    if (data) {
      cachedTimezone.value = data.timezone || 'UTC'
      logger.info('Loaded timezone:', cachedTimezone.value)
    }
  } catch (e) {
    logger.error('Failed to load timezone config:', e)
  }
}

/**
 * Ensures the timezone setting has been fetched at least once.
 * Multiple callers share the same in-flight promise.
 */
export function ensureTimezone(): Promise<void> {
  if (cachedTimezone.value) return Promise.resolve()
  if (!fetchPromise) {
    fetchPromise = loadTimezone().finally(() => {
      fetchPromise = null
    })
  }
  return fetchPromise
}

/**
 * Format an ISO date string using the fleet-configured timezone.
 * Falls back to browser locale if timezone is not yet loaded.
 *
 * Accepts `undefined` as well as `null`: the generated OpenAPI contract models
 * nullable backend timestamps as optional (`expires_at?: string | null`), so
 * call sites forward possibly-absent values here (#12420).
 */
export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  const tz = cachedTimezone.value
  if (tz) {
    return date.toLocaleString(undefined, { timeZone: tz })
  }
  return date.toLocaleString()
}

/**
 * Return the current cached timezone value (may be null if not yet loaded).
 */
export function getTimezone(): string | null {
  return cachedTimezone.value
}
