// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Timezone Composable
 *
 * Fetches the configured timezone from /api/settings/time/config and provides
 * timezone-aware date formatting. Caches the timezone in a module-level ref
 * so all components share the same value without redundant fetches.
 */

import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useTimezone')

/** Module-level cache — shared across all component instances */
const cachedTimezone = ref<string | null>(null)
let fetchPromise: Promise<void> | null = null

async function loadTimezone(): Promise<void> {
  const authStore = useAuthStore()
  try {
    const res = await fetch(
      `${authStore.getApiUrl()}/api/settings/time/config`,
      { headers: authStore.getAuthHeaders() },
    )
    if (res.ok) {
      const data: { timezone: string } = await res.json()
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
 */
export function formatDateTime(dateStr: string | null): string {
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
