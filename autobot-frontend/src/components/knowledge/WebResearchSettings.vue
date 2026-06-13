<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

WebResearchSettings.vue - Web research configuration panel
Issue #3850: useWebResearchStore exists but has no view
-->

<template>
  <div class="web-research-settings">
    <!-- Header -->
    <div class="panel-header">
      <div class="header-content">
        <h2>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          Web Research Settings
        </h2>
        <p class="header-subtitle">
          Configure automated web research behaviour, rate limiting, and cache management.
        </p>
      </div>
      <div class="header-actions">
        <button
          class="btn btn-secondary"
          :disabled="isLoading"
          @click="fetchStatus"
        >
          <svg v-if="!isLoading" class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <svg v-else class="btn-icon spin" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="store.lastError" class="error-banner" role="alert">
      <svg class="error-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <span>{{ store.lastError }}</span>
      <button class="error-dismiss" @click="store.clearError()" aria-label="Dismiss error">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" class="dismiss-icon">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Status Cards -->
    <div class="status-grid">
      <div class="status-card" :class="store.isEnabled ? 'status-enabled' : 'status-disabled'">
        <div class="status-card-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div class="status-card-body">
          <span class="status-label">Research Status</span>
          <span class="status-value">{{ store.isEnabled ? 'Enabled' : 'Disabled' }}</span>
        </div>
      </div>

      <div class="status-card">
        <div class="status-card-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
          </svg>
        </div>
        <div class="status-card-body">
          <span class="status-label">Cache Size</span>
          <span class="status-value">{{ store.cacheSize }}</span>
        </div>
      </div>

      <div class="status-card">
        <div class="status-card-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div class="status-card-body">
          <span class="status-label">Rate Limiter</span>
          <span class="status-value">
            {{ store.rateLimiterStatus
              ? `${store.rateLimiterStatus.current_requests ?? 0} / ${store.rateLimiterStatus.max_requests ?? store.settings.rate_limit_requests}`
              : 'N/A' }}
          </span>
        </div>
      </div>

      <div class="status-card">
        <div class="status-card-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div class="status-card-body">
          <span class="status-label">Preferred Method</span>
          <span class="status-value capitalize">{{ store.status.preferred_method || store.settings.preferred_method }}</span>
        </div>
      </div>
    </div>

    <!-- Settings Form -->
    <form class="settings-form" @submit.prevent="saveSettings">

      <!-- Enable / Disable toggle -->
      <section class="settings-section">
        <h3 class="section-heading">General</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-enabled">Enable Web Research</label>
            <p class="field-hint">Allow AutoBot agents to perform automated internet searches.</p>
          </div>
          <div class="field-control">
            <button
              type="button"
              class="toggle"
              :class="store.settings.enabled ? 'toggle-on' : 'toggle-off'"
              role="switch"
              :aria-checked="store.settings.enabled"
              id="wr-enabled"
              :disabled="isToggling"
              @click="handleToggle"
            >
              <span class="toggle-thumb" />
            </button>
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-confirmation">Require User Confirmation</label>
            <p class="field-hint">Ask for confirmation before each research request.</p>
          </div>
          <div class="field-control">
            <button
              type="button"
              class="toggle"
              :class="store.settings.require_user_confirmation ? 'toggle-on' : 'toggle-off'"
              role="switch"
              :aria-checked="store.settings.require_user_confirmation"
              id="wr-confirmation"
              @click="store.updateSettings({ require_user_confirmation: !store.settings.require_user_confirmation })"
            >
              <span class="toggle-thumb" />
            </button>
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-method">Preferred Method</label>
            <p class="field-hint">Search strategy used by the research agent.</p>
          </div>
          <div class="field-control">
            <select
              id="wr-method"
              class="field-select"
              :value="store.settings.preferred_method"
              @change="store.updateSettings({ preferred_method: ($event.target as HTMLSelectElement).value as 'basic' | 'advanced' | 'api_based' })"
            >
              <option value="basic">Basic</option>
              <option value="advanced">Advanced</option>
              <option value="api_based">API Based</option>
            </select>
          </div>
        </div>
      </section>

      <!-- Limits -->
      <section class="settings-section">
        <h3 class="section-heading">Limits</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-max-results">Max Results</label>
            <p class="field-hint">Maximum number of results returned per research query.</p>
          </div>
          <div class="field-control">
            <input
              id="wr-max-results"
              type="number"
              class="field-input"
              min="1"
              max="50"
              :value="store.settings.max_results"
              @input="store.updateSettings({ max_results: parseInt(($event.target as HTMLInputElement).value, 10) || 5 })"
            />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-timeout">Timeout (seconds)</label>
            <p class="field-hint">Maximum time to wait for a research response.</p>
          </div>
          <div class="field-control">
            <input
              id="wr-timeout"
              type="number"
              class="field-input"
              min="5"
              max="300"
              :value="store.settings.timeout_seconds"
              @input="store.updateSettings({ timeout_seconds: parseInt(($event.target as HTMLInputElement).value, 10) || 30 })"
            />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-threshold">Auto Research Threshold</label>
            <p class="field-hint">Confidence score (0–1) above which research triggers automatically.</p>
          </div>
          <div class="field-control">
            <input
              id="wr-threshold"
              type="number"
              class="field-input"
              min="0"
              max="1"
              step="0.05"
              :value="store.settings.auto_research_threshold"
              @input="store.updateSettings({ auto_research_threshold: parseFloat(($event.target as HTMLInputElement).value) || 0.3 })"
            />
          </div>
        </div>
      </section>

      <!-- Rate Limiting -->
      <section class="settings-section">
        <h3 class="section-heading">Rate Limiting</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-rate-requests">Max Requests per Window</label>
            <p class="field-hint">Number of research requests allowed within the rate limit window.</p>
          </div>
          <div class="field-control">
            <input
              id="wr-rate-requests"
              type="number"
              class="field-input"
              min="1"
              max="1000"
              :value="store.settings.rate_limit_requests"
              @input="store.updateSettings({ rate_limit_requests: parseInt(($event.target as HTMLInputElement).value, 10) || 5 })"
            />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-rate-window">Rate Limit Window (seconds)</label>
            <p class="field-hint">Time window in seconds for the rate limit counter.</p>
          </div>
          <div class="field-control">
            <input
              id="wr-rate-window"
              type="number"
              class="field-input"
              min="10"
              max="3600"
              :value="store.settings.rate_limit_window"
              @input="store.updateSettings({ rate_limit_window: parseInt(($event.target as HTMLInputElement).value, 10) || 60 })"
            />
          </div>
        </div>
      </section>

      <!-- Privacy & Storage -->
      <section class="settings-section">
        <h3 class="section-heading">Privacy and Storage</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-store-kb">Store Results in Knowledge Base</label>
            <p class="field-hint">Save research results to the knowledge base for future use.</p>
          </div>
          <div class="field-control">
            <button
              type="button"
              class="toggle"
              :class="store.settings.store_results_in_kb ? 'toggle-on' : 'toggle-off'"
              role="switch"
              :aria-checked="store.settings.store_results_in_kb"
              id="wr-store-kb"
              @click="store.updateSettings({ store_results_in_kb: !store.settings.store_results_in_kb })"
            >
              <span class="toggle-thumb" />
            </button>
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-anonymize">Anonymize Requests</label>
            <p class="field-hint">Strip identifying information from outbound research requests.</p>
          </div>
          <div class="field-control">
            <button
              type="button"
              class="toggle"
              :class="store.settings.anonymize_requests ? 'toggle-on' : 'toggle-off'"
              role="switch"
              :aria-checked="store.settings.anonymize_requests"
              id="wr-anonymize"
              @click="store.updateSettings({ anonymize_requests: !store.settings.anonymize_requests })"
            >
              <span class="toggle-thumb" />
            </button>
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-filter-adult">Filter Adult Content</label>
            <p class="field-hint">Exclude adult or explicit content from research results.</p>
          </div>
          <div class="field-control">
            <button
              type="button"
              class="toggle"
              :class="store.settings.filter_adult_content ? 'toggle-on' : 'toggle-off'"
              role="switch"
              :aria-checked="store.settings.filter_adult_content"
              id="wr-filter-adult"
              @click="store.updateSettings({ filter_adult_content: !store.settings.filter_adult_content })"
            >
              <span class="toggle-thumb" />
            </button>
          </div>
        </div>
      </section>

      <!-- Circuit Breakers -->
      <section v-if="circuitBreakerEntries.length" class="settings-section">
        <h3 class="section-heading">Circuit Breakers</h3>
        <div class="cb-grid">
          <div
            v-for="[name, state] in circuitBreakerEntries"
            :key="name"
            class="cb-card"
            :class="`cb-${String(state).toLowerCase()}`"
          >
            <span class="cb-name">{{ name }}</span>
            <span class="cb-state">{{ state }}</span>
          </div>
        </div>
      </section>

      <!-- Form Actions -->
      <div class="form-actions">
        <button
          type="button"
          class="btn btn-danger"
          :disabled="isClearingCache"
          @click="clearCache"
        >
          <svg class="btn-icon" :class="{ spin: isClearingCache }" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          Clear Cache
        </button>

        <button
          v-if="circuitBreakerEntries.length"
          type="button"
          class="btn btn-secondary"
          :disabled="isResettingBreakers"
          @click="resetCircuitBreakers"
        >
          <svg class="btn-icon" :class="{ spin: isResettingBreakers }" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Reset Circuit Breakers
        </button>

        <div class="form-actions-right">
          <button
            type="button"
            class="btn btn-secondary"
            @click="store.resetSettings()"
          >
            Reset Defaults
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="isSaving"
          >
            <svg v-if="isSaving" class="btn-icon spin" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {{ isSaving ? 'Saving...' : 'Save Settings' }}
          </button>
        </div>
      </div>

      <!-- Save feedback -->
      <div v-if="saveSuccess" class="save-success" role="status">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" class="success-icon">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Settings saved successfully.
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
/**
 * WebResearchSettings — Issue #3850
 *
 * Settings panel for useWebResearchStore. Fetches live status from the backend
 * on mount, exposes all WebResearchSettings fields, and POSTs changes via
 * PUT /web-research/settings. Toggle enable/disable uses the dedicated
 * /web-research/enable|disable endpoints.
 */
import { ref, computed, onMounted } from 'vue'
import { useWebResearchStore } from '@/stores/useWebResearchStore'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('WebResearchSettings')
const store = useWebResearchStore()

const isSaving = ref(false)
const isToggling = ref(false)
const isClearingCache = ref(false)
const isResettingBreakers = ref(false)
const saveSuccess = ref(false)

const isLoading = computed(() => store.isLoading)

const circuitBreakerEntries = computed<[string, unknown][]>(() => {
  const cb = store.status.circuit_breakers
  if (!cb || typeof cb !== 'object') return []
  return Object.entries(cb as Record<string, unknown>)
})

async function fetchStatus(): Promise<void> {
  store.setLoading(true)
  store.clearError()
  try {
    const data = await ApiClient.get<any>(`${getApiBase()}/web-research/status`) as Record<string, unknown>
    store.updateStatus({
      enabled: Boolean(data.enabled),
      preferred_method: String(data.preferred_method ?? store.status.preferred_method),
      cache_stats: (data.cache_stats as typeof store.status.cache_stats) ?? null,
      circuit_breakers: (data.circuit_breakers as Record<string, unknown> | null) ?? null
    })
    store.updateSettings({ enabled: Boolean(data.enabled) })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.warn('Failed to fetch web research status:', msg)
    store.setError('Failed to load status from backend. Displaying cached settings.')
  } finally {
    store.setLoading(false)
  }
}

async function handleToggle(): Promise<void> {
  isToggling.value = true
  store.clearError()
  const endpoint = store.settings.enabled ? '/web-research/disable' : '/web-research/enable'
  try {
    await ApiClient.post<any>(`${getApiBase()}${endpoint}`, {})
    store.toggleWebResearch()
    store.updateStatus({ enabled: store.settings.enabled })
    logger.info('Web research toggled:', store.settings.enabled ? 'enabled' : 'disabled')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Toggle web research failed:', msg)
    store.setError(`Failed to ${store.settings.enabled ? 'disable' : 'enable'} web research: ${msg}`)
  } finally {
    isToggling.value = false
  }
}

async function saveSettings(): Promise<void> {
  isSaving.value = true
  saveSuccess.value = false
  store.clearError()
  try {
    await ApiClient.put<any>(`${getApiBase()}/web-research/settings`, {
      enabled: store.settings.enabled,
      require_user_confirmation: store.settings.require_user_confirmation,
      preferred_method: store.settings.preferred_method,
      max_results: store.settings.max_results,
      timeout_seconds: store.settings.timeout_seconds,
      auto_research_threshold: store.settings.auto_research_threshold,
      rate_limit_requests: store.settings.rate_limit_requests,
      rate_limit_window: store.settings.rate_limit_window,
      store_results_in_kb: store.settings.store_results_in_kb,
      anonymize_requests: store.settings.anonymize_requests,
      filter_adult_content: store.settings.filter_adult_content
    })
    saveSuccess.value = true
    logger.info('Web research settings saved')
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to save web research settings:', msg)
    store.setError(`Failed to save settings: ${msg}`)
  } finally {
    isSaving.value = false
  }
}

async function clearCache(): Promise<void> {
  isClearingCache.value = true
  store.clearError()
  try {
    await ApiClient.post<any>(`${getApiBase()}/web-research/clear-cache`, {})
    store.updateStatus({ cache_stats: { cache_size: 0, rate_limiter: store.status.cache_stats?.rate_limiter } })
    logger.info('Web research cache cleared')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to clear cache:', msg)
    store.setError(`Failed to clear cache: ${msg}`)
  } finally {
    isClearingCache.value = false
  }
}

async function resetCircuitBreakers(): Promise<void> {
  isResettingBreakers.value = true
  store.clearError()
  try {
    await ApiClient.post<any>(`${getApiBase()}/web-research/reset-circuit-breakers`, {})
    store.updateStatus({ circuit_breakers: null })
    logger.info('Web research circuit breakers reset')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to reset circuit breakers:', msg)
    store.setError(`Failed to reset circuit breakers: ${msg}`)
  } finally {
    isResettingBreakers.value = false
  }
}

onMounted(() => {
  fetchStatus()
})
</script>

<style scoped>
/* ============================================
 * WEB RESEARCH SETTINGS — Design Token Layout
 * ============================================ */

.web-research-settings {
  padding: var(--spacing-xl);
  max-width: 860px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

/* ── Header ───────────────────────────────── */

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-lg);
  padding-bottom: var(--spacing-xl);
  border-bottom: 1px solid var(--border-default);
}

.panel-header h2 {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.header-icon {
  width: 22px;
  height: 22px;
  color: var(--color-info);
  flex-shrink: 0;
}

.header-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: var(--leading-normal);
}

.header-actions {
  flex-shrink: 0;
}

/* ── Error Banner ─────────────────────────── */

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg, #fef2f2);
  border: 1px solid var(--color-error, #ef4444);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-error, #ef4444);
}

.error-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.error-dismiss {
  margin-left: auto;
  background: transparent;
  border: none;
  cursor: pointer;
  color: inherit;
  padding: var(--spacing-0);
  display: flex;
  align-items: center;
}

.dismiss-icon {
  width: 16px;
  height: 16px;
}

/* ── Status Grid ──────────────────────────── */

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--spacing-md);
}

.status-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.status-card.status-enabled {
  border-color: var(--color-success, #22c55e);
  background: var(--color-success-bg, #f0fdf4);
}

.status-card.status-disabled {
  border-color: var(--border-default);
}

.status-card-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--color-info);
}

.status-card-icon svg {
  width: 20px;
  height: 20px;
}

.status-enabled .status-card-icon {
  color: var(--color-success, #22c55e);
}

.status-card-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
  min-width: 0;
}

.status-label {
  font-size: var(--text-xs, 11px);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
}

.status-value {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}

.capitalize {
  text-transform: capitalize;
}

/* ── Settings Form ────────────────────────── */

.settings-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.settings-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.section-heading {
  font-size: var(--text-sm);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: var(--spacing-0);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-lg);
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--border-default);
}

.field-row:last-child {
  border-bottom: none;
}

.field-label-block {
  flex: 1;
  min-width: 0;
}

.field-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-0-5);
  cursor: pointer;
}

.field-hint {
  font-size: var(--text-xs, 12px);
  color: var(--text-tertiary);
  margin: var(--spacing-0);
  line-height: var(--leading-normal);
}

.field-control {
  flex-shrink: 0;
}

.field-select,
.field-input {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
  min-width: 120px;
  outline: none;
  transition: border-color var(--duration-150);
}

.field-select:focus,
.field-input:focus {
  border-color: var(--color-info);
}

.field-input[type="number"] {
  width: 100px;
  text-align: right;
}

/* ── Toggle ───────────────────────────────── */

.toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 44px;
  height: 24px;
  border-radius: var(--radius-xl);
  border: none;
  cursor: pointer;
  transition: background-color var(--duration-200);
  outline: none;
}

.toggle:focus-visible {
  box-shadow: 0 0 0 2px var(--color-info);
}

.toggle:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-on {
  background: var(--color-success, #22c55e);
}

.toggle-off {
  background: var(--border-default);
}

.toggle-thumb {
  position: absolute;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ffffff;
  transition: transform var(--duration-200);
  box-shadow: var(--shadow-sm);
}

.toggle-on .toggle-thumb {
  transform: translateX(20px);
}

/* ── Circuit Breakers ─────────────────────── */

.cb-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
}

.cb-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  min-width: 100px;
  background: var(--bg-primary);
}

.cb-name {
  font-size: var(--text-xs, 11px);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}

.cb-state {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}

.cb-closed { border-color: var(--color-success, #22c55e); }
.cb-closed .cb-state { color: var(--color-success, #22c55e); }

.cb-open { border-color: var(--color-error, #ef4444); }
.cb-open .cb-state { color: var(--color-error, #ef4444); }

.cb-half-open { border-color: var(--color-warning, #f59e0b); }
.cb-half-open .cb-state { color: var(--color-warning, #f59e0b); }

/* ── Form Actions ─────────────────────────── */

.form-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.form-actions-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-left: auto;
}

/* ── Buttons ──────────────────────────────── */

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: opacity var(--duration-150), background-color var(--duration-150);
  outline: none;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn:focus-visible {
  box-shadow: 0 0 0 2px var(--color-info);
}

.btn-primary {
  background: var(--color-info);
  color: #ffffff;
  border-color: var(--color-info);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.88;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-tertiary);
}

.btn-danger {
  background: var(--color-error-bg, #fef2f2);
  color: var(--color-error, #ef4444);
  border-color: var(--color-error, #ef4444);
}

.btn-danger:hover:not(:disabled) {
  background: var(--color-error, #ef4444);
  color: #ffffff;
}

.btn-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* ── Save Success ─────────────────────────── */

.save-success {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-success-bg, #f0fdf4);
  border: 1px solid var(--color-success, #22c55e);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-success, #22c55e);
  font-weight: 500;
}

.success-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* ── Spinner animation ────────────────────── */

@keyframes spin {
  to { transform: rotate(360deg); }
}

.spin {
  animation: spin 0.8s linear infinite;
}

/* ── Responsive ───────────────────────────── */

@media (max-width: 640px) {
  .web-research-settings {
    padding: var(--spacing-md);
  }

  .panel-header {
    flex-direction: column;
    gap: var(--spacing-md);
  }

  .field-row {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .form-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .form-actions-right {
    margin-left: var(--spacing-0);
    flex-direction: column;
  }
}
</style>
