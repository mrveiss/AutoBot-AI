/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export interface RateLimiter {
  current_requests?: number
  max_requests?: number
}

export interface CacheStats {
  cache_size?: number
  rate_limiter?: RateLimiter
}

export interface ResearchStatus {
  enabled: boolean
  preferred_method: string
  cache_stats: CacheStats | null
  circuit_breakers: any
}

export interface WebResearchSettings {
  enabled: boolean
  require_user_confirmation: boolean
  preferred_method: 'basic' | 'advanced' | 'api_based'
  max_results: number
  timeout_seconds: number
  auto_research_threshold: number
  rate_limit_requests: number
  rate_limit_window: number
  store_results_in_kb: boolean
  anonymize_requests: boolean
  filter_adult_content: boolean
}

export const useWebResearchStore = defineStore('webResearch', () => {
  // State
  const settings = ref<WebResearchSettings>({
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
  function updateSettings(newSettings: Partial<WebResearchSettings>) {
    settings.value = { ...settings.value, ...newSettings }
  }

  function updateStatus(newStatus: Partial<ResearchStatus>) {
    status.value = { ...status.value, ...newStatus }
  }

  function toggleWebResearch() {
    settings.value.enabled = !settings.value.enabled
    // Issue #821: Clear stale error when toggling
    error.value = null
  }

  function setEnabled(enabled: boolean) {
    settings.value.enabled = enabled
  }

  function setLoading(loading: boolean) {
    isLoading.value = loading
  }

  function setError(error: string | null) {
    lastError.value = error
  }

  function clearError() {
    lastError.value = null
  }

  function resetSettings() {
    settings.value = {
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
    }
  }

  return {
    // State
    settings,
    status,
    isLoading,
    lastError,

    // Computed
    isEnabled,
    canAutoResearch,
    cacheSize,
    rateLimiterStatus,

    // Actions
    updateSettings,
    updateStatus,
    toggleWebResearch,
    setEnabled,
    setLoading,
    setError,
    clearError,
    resetSettings
  }
}, {
  persist: {
    key: 'autobot-web-research',
    storage: localStorage,
    paths: ['settings'] // Only persist settings, not status/loading/error
  }
})
