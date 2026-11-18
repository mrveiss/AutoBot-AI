// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { isHttpError } from '@autobot/ui'
import ApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('WebResearchStore')

/**
 * Web-research READ paths (#11665). The backend registers
 * api/web_research_settings.py with an empty registry prefix, so the live paths
 * are /api/web-research/*. Every write (enable, disable, settings PUT, clear
 * cache, reset circuit breakers) is admin-only and global, so the one editor
 * lives in the SLM admin console (#19217) and this app only reads.
 */
export const WEB_RESEARCH_API = {
  settings: '/web-research/settings',
  status: '/web-research/status'
} as const

export interface RateLimiter {
  current_requests?: number
  max_requests?: number
}

export interface ResearchCacheStats {
  cache_size?: number
  rate_limiter?: RateLimiter
}

export interface ResearchStatus {
  enabled: boolean
  preferred_method: string
  cache_stats: ResearchCacheStats | null
  circuit_breakers: Record<string, unknown> | null
}

/**
 * The settings this app reads, taken from the backend's generated `WebResearchSettings`
 * (the SLM editor writes the full set, including the daily limit and quality threshold);
 * `preferred_method` is narrowed to the values the backend accepts.
 */
type ServedSettings = components['schemas']['WebResearchSettings']
export type WebResearchStoreSettings = Pick<
  ServedSettings,
  | 'enabled'
  | 'require_user_confirmation'
  | 'max_results'
  | 'timeout_seconds'
  | 'auto_research_threshold'
  | 'rate_limit_requests'
  | 'rate_limit_window'
  | 'store_results_in_kb'
  | 'anonymize_requests'
  | 'filter_adult_content'
> & { preferred_method: 'basic' | 'advanced' | 'api_based' }

export const useWebResearchStore = defineStore('webResearch', () => {
  // State
  const settings = ref<WebResearchStoreSettings>({
    enabled: false,
    require_user_confirmation: true,
    preferred_method: 'basic',
    max_results: 5,
    timeout_seconds: 30,
    auto_research_threshold: 0.3,
    rate_limit_requests: 5,
    rate_limit_window: 60,
    store_results_in_kb: true,
    anonymize_requests: true,
    filter_adult_content: true
  })

  const status = ref<ResearchStatus>({
    enabled: false,
    preferred_method: 'basic',
    cache_stats: null,
    circuit_breakers: null
  })

  const isLoading = ref(false)
  const lastError = ref<string | null>(null)
  // #11665: false when the backend reports 503 — WebResearcher (browser/
  // Playwright) failed to initialize at startup.
  const researcherAvailable = ref(true)

  // Computed
  const isEnabled = computed(() => settings.value.enabled)

  const canAutoResearch = computed(() =>
    settings.value.enabled &&
    !settings.value.require_user_confirmation
  )

  const cacheSize = computed(() =>
    status.value.cache_stats?.cache_size || 0
  )

  const rateLimiterStatus = computed(() =>
    status.value.cache_stats?.rate_limiter
  )

  // Actions
  // Internal: hydrates the state from the backend read in loadFromBackend.
  function updateSettings(newSettings: Partial<WebResearchStoreSettings>) {
    settings.value = { ...settings.value, ...newSettings }
  }

  /**
   * Hydrate settings + status from the backend (#11665).
   *
   * The store was localStorage-only before, so `enabled` could silently
   * disagree with the backend. A 503 from /web-research/status means the
   * WebResearcher failed browser/Playwright init at startup — recorded in
   * `researcherAvailable` for pre-flight banners.
   */
  async function loadFromBackend(): Promise<void> {
    isLoading.value = true
    lastError.value = null
    const base = getApiBase()
    try {
      const data = await ApiClient.get<Record<string, unknown>>(
        `${base}${WEB_RESEARCH_API.settings}`
      )
      const backendSettings = data.settings as Partial<WebResearchStoreSettings> | undefined
      if (backendSettings) updateSettings(backendSettings)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.warn('Failed to load web research settings from backend:', msg)
      lastError.value = msg
    }
    try {
      const data = await ApiClient.get<Record<string, unknown>>(
        `${base}${WEB_RESEARCH_API.status}`,
        { maxRetries: 1, suppressErrorLog: true }
      )
      updateStatus({
        enabled: Boolean(data.enabled),
        preferred_method: String(data.preferred_method ?? status.value.preferred_method),
        cache_stats: (data.cache_stats as ResearchCacheStats | null) ?? null,
        circuit_breakers: (data.circuit_breakers as Record<string, unknown> | null) ?? null
      })
      researcherAvailable.value = true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      if (isHttpError(err) && err.status === 503) {
        researcherAvailable.value = false
      } else {
        logger.warn('Failed to load web research status from backend:', msg)
        lastError.value = msg
      }
    } finally {
      isLoading.value = false
    }
  }

  function updateStatus(newStatus: Partial<ResearchStatus>) {
    status.value = { ...status.value, ...newStatus }
  }

  return {
    // State
    settings,
    status,
    isLoading,
    lastError,
    researcherAvailable,

    // Computed
    isEnabled,
    canAutoResearch,
    cacheSize,
    rateLimiterStatus,

    // Actions (reads only: the writes live in the SLM admin console, #19217)
    updateStatus,
    loadFromBackend
  }
}, {
  persist: {
    key: 'autobot-web-research',
    storage: localStorage,
    pick: ['settings'] // Only persist settings, not status/loading/error
  }
})
