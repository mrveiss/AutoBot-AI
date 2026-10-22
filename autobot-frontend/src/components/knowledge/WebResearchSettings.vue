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
      <div v-if="!embedded" class="header-content">
        <h2>
          <svg class="header-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {{ $t('settings.webResearch.title') }}
        </h2>
        <p class="header-subtitle">{{ $t('settings.webResearch.desc') }}</p>
      </div>
      <div class="header-actions">
        <button
          class="btn btn-secondary"
          :disabled="isLoading"
          @click="store.loadFromBackend()"
        >
          <svg v-if="!isLoading" class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <svg v-else class="btn-icon spin" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ $t('settings.webResearch.refresh') }}
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
      <button class="error-dismiss" @click="store.clearError()" :aria-label="$t('settings.webResearch.dismissError')">
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
          <span class="status-label">{{ $t('settings.webResearch.statusLabel') }}</span>
          <span class="status-value">{{ $t(store.isEnabled ? 'settings.webResearch.statusEnabled' : 'settings.webResearch.statusDisabled') }}</span>
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
          <span class="status-label">{{ $t('settings.webResearch.cacheSizeLabel') }}</span>
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
          <span class="status-label">{{ $t('settings.webResearch.rateLimiterLabel') }}</span>
          <span class="status-value">
            {{ store.rateLimiterStatus
              ? `${store.rateLimiterStatus.current_requests ?? 0} / ${store.rateLimiterStatus.max_requests ?? store.settings.rate_limit_requests}`
              : $t('settings.webResearch.notAvailable') }}
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
          <span class="status-label">{{ $t('settings.webResearch.methodLabel') }}</span>
          <span class="status-value">{{ methodName(store.status.preferred_method || store.settings.preferred_method) }}</span>
        </div>
      </div>
    </div>

    <!-- Settings Form -->
    <form class="settings-form" @submit.prevent="saveSettings">

      <!-- Enable / Disable toggle -->
      <section class="settings-section">
        <h3 class="section-heading">{{ $t('settings.webResearch.generalLabel') }}</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-enabled">{{ $t('settings.webResearch.enabledLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.enabledHint') }}</p>
          </div>
          <div class="field-control">
            <BaseSwitch id="wr-enabled" :model-value="store.settings.enabled" :label="$t('settings.webResearch.enabledLabel')" :disabled="isToggling" @change="handleToggle($event)" />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-confirmation">{{ $t('settings.webResearch.confirmationLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.confirmationHint') }}</p>
          </div>
          <div class="field-control">
            <BaseSwitch id="wr-confirmation" :model-value="store.settings.require_user_confirmation" :label="$t('settings.webResearch.confirmationLabel')" @change="store.updateSettings({ require_user_confirmation: $event })" />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-method">{{ $t('settings.webResearch.methodLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.methodHint') }}</p>
          </div>
          <div class="field-control">
            <select
              id="wr-method"
              class="field-select"
              :value="store.settings.preferred_method"
              @change="store.updateSettings({ preferred_method: ($event.target as HTMLSelectElement).value as 'basic' | 'advanced' | 'api_based' })"
            >
              <option value="basic">{{ $t('settings.webResearch.methodBasic') }}</option>
              <option value="advanced">{{ $t('settings.webResearch.methodAdvanced') }}</option>
              <option value="api_based">{{ $t('settings.webResearch.methodApiBased') }}</option>
            </select>
          </div>
        </div>
      </section>

      <!-- Limits -->
      <section class="settings-section">
        <h3 class="section-heading">{{ $t('settings.webResearch.limitsLabel') }}</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-max-results">{{ $t('settings.webResearch.maxResultsLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.maxResultsHint') }}</p>
          </div>
          <div class="field-control">
            <input
              id="wr-max-results"
              type="number"
              class="field-input"
              min="1"
              max="50"
              :value="store.settings.max_results"
              @change="setNumber('max_results', $event, 1, 50)"
            />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-timeout">{{ $t('settings.webResearch.timeoutLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.timeoutHint') }}</p>
          </div>
          <div class="field-control">
            <input
              id="wr-timeout"
              type="number"
              class="field-input"
              min="5"
              max="120"
              :value="store.settings.timeout_seconds"
              @change="setNumber('timeout_seconds', $event, 5, 120)"
            />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-threshold">{{ $t('settings.webResearch.thresholdLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.thresholdHint') }}</p>
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
              @change="setNumber('auto_research_threshold', $event, 0, 1)"
            />
          </div>
        </div>
      </section>

      <!-- Rate Limiting -->
      <section class="settings-section">
        <h3 class="section-heading">{{ $t('settings.webResearch.rateLimitLabel') }}</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-rate-requests">{{ $t('settings.webResearch.rateLimitRequests') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.rateRequestsHint') }}</p>
          </div>
          <div class="field-control">
            <input
              id="wr-rate-requests"
              type="number"
              class="field-input"
              min="1"
              max="100"
              :value="store.settings.rate_limit_requests"
              @change="setNumber('rate_limit_requests', $event, 1, 100)"
            />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-rate-window">{{ $t('settings.webResearch.rateLimitWindow') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.rateWindowHint') }}</p>
          </div>
          <div class="field-control">
            <input
              id="wr-rate-window"
              type="number"
              class="field-input"
              min="10"
              max="3600"
              :value="store.settings.rate_limit_window"
              @change="setNumber('rate_limit_window', $event, 10, 3600)"
            />
          </div>
        </div>
      </section>

      <!-- Privacy & Storage -->
      <section class="settings-section">
        <h3 class="section-heading">{{ $t('settings.webResearch.privacyLabel') }}</h3>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-store-kb">{{ $t('settings.webResearch.storeInKbLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.storeInKbHint') }}</p>
          </div>
          <div class="field-control">
            <BaseSwitch id="wr-store-kb" :model-value="store.settings.store_results_in_kb" :label="$t('settings.webResearch.storeInKbLabel')" @change="store.updateSettings({ store_results_in_kb: $event })" />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-anonymize">{{ $t('settings.webResearch.anonymizeLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.anonymizeHint') }}</p>
          </div>
          <div class="field-control">
            <BaseSwitch id="wr-anonymize" :model-value="store.settings.anonymize_requests" :label="$t('settings.webResearch.anonymizeLabel')" @change="store.updateSettings({ anonymize_requests: $event })" />
          </div>
        </div>

        <div class="field-row">
          <div class="field-label-block">
            <label class="field-label" for="wr-filter-adult">{{ $t('settings.webResearch.filterAdultLabel') }}</label>
            <p class="field-hint">{{ $t('settings.webResearch.filterAdultHint') }}</p>
          </div>
          <div class="field-control">
            <BaseSwitch id="wr-filter-adult" :model-value="store.settings.filter_adult_content" :label="$t('settings.webResearch.filterAdultLabel')" @change="store.updateSettings({ filter_adult_content: $event })" />
          </div>
        </div>
      </section>

      <!-- Circuit Breakers -->
      <section v-if="circuitBreakerEntries.length" class="settings-section">
        <h3 class="section-heading">{{ $t('settings.webResearch.circuitBreakersLabel') }}</h3>
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
          {{ $t('settings.webResearch.clearCache') }}
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
          {{ $t('settings.webResearch.resetCircuitBreakers') }}
        </button>

        <div class="form-actions-right">
          <button
            type="button"
            class="btn btn-secondary"
            @click="store.resetSettings()"
          >
            {{ $t('settings.reset') }}
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
            {{ $t(isSaving ? 'settings.webResearch.saving' : 'settings.webResearch.save') }}
          </button>
        </div>
      </div>

      <!-- Save feedback -->
      <div v-if="saveSuccess" class="save-success" role="status">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" class="success-icon">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {{ $t('settings.webResearch.saved') }}
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
/**
 * WebResearchSettings — Issue #3850, #19217
 *
 * The one web research settings component: Knowledge → Research → Settings and
 * Settings → Web research both mount it. Hydrates settings + status from the backend
 * on mount (store.loadFromBackend, #11665). Every write goes through a store action
 * (#19217), so no surface can keep a setting in the browser only.
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseSwitch } from '@autobot/ui'
import { useWebResearchStore, type WebResearchSettings } from '@/stores/useWebResearchStore'
import { createLogger } from '@/utils/debugUtils'

withDefaults(defineProps<{
  embedded?: boolean // in a frame that shows the title: hide this one's own (#16744)
}>(), { embedded: false })

const { t } = useI18n()
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

const METHOD_KEYS: Record<string, string> = {
  basic: 'settings.webResearch.methodBasic',
  advanced: 'settings.webResearch.methodAdvanced',
  api_based: 'settings.webResearch.methodApiBased',
}

function methodName(method: string): string {
  return METHOD_KEYS[method] ? t(METHOD_KEYS[method]) : method
}

type NumericSetting = 'max_results' | 'timeout_seconds' | 'auto_research_threshold' | 'rate_limit_requests' | 'rate_limit_window'

/** A typed number, clamped to the range its hint states; an empty or invalid entry keeps the current value. */
function setNumber(field: NumericSetting, event: Event, min: number, max: number): void {
  const input = event.target as HTMLInputElement
  const value = Number(input.value)
  if (input.value === '' || Number.isNaN(value)) {
    input.value = String(store.settings[field])
    return
  }
  store.updateSettings({ [field]: Math.min(Math.max(value, min), max) } as Partial<WebResearchSettings>)
}

/** Runs one backend write, reporting a failure in the banner under `failedKey`. */
async function runWrite(busy: { value: boolean }, failedKey: string, write: () => Promise<void>): Promise<boolean> {
  busy.value = true
  store.clearError()
  try {
    await write()
    return true
  } catch (err: unknown) {
    const error = err instanceof Error ? err.message : String(err)
    logger.error(`${failedKey}:`, error)
    store.setError(t(failedKey, { error }))
    return false
  } finally {
    busy.value = false
  }
}

async function handleToggle(enabled: boolean): Promise<void> {
  const failedKey = enabled ? 'settings.webResearch.enableFailed' : 'settings.webResearch.disableFailed'
  await runWrite(isToggling, failedKey, () => store.setEnabledOnBackend(enabled))
}

async function saveSettings(): Promise<void> {
  saveSuccess.value = false
  if (await runWrite(isSaving, 'settings.webResearch.saveFailed', store.saveSettings)) {
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  }
}

async function clearCache(): Promise<void> {
  await runWrite(isClearingCache, 'settings.webResearch.clearCacheFailed', store.clearCache)
}

async function resetCircuitBreakers(): Promise<void> {
  await runWrite(isResettingBreakers, 'settings.webResearch.resetBreakersFailed', store.resetCircuitBreakers)
}

onMounted(() => {
  store.loadFromBackend()
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
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-error);
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
  width: var(--spacing-4);
  height: var(--spacing-4);
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
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.status-card.status-disabled {
  border-color: var(--border-default);
}

.status-card-icon {
  width: var(--spacing-9);
  height: var(--spacing-9);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--color-info);
}

.status-card-icon svg {
  width: var(--spacing-5);
  height: var(--spacing-5);
}

.status-enabled .status-card-icon {
  color: var(--color-success);
}

.status-card-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
  min-width: 0;
}

.status-label {
  font-size: var(--text-xs);
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
  font-size: var(--text-xs);
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
  font-size: var(--text-xs);
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

.cb-closed { border-color: var(--color-success); }
.cb-closed .cb-state { color: var(--color-success); }

.cb-open { border-color: var(--color-error); }
.cb-open .cb-state { color: var(--color-error); }

.cb-half-open { border-color: var(--color-warning); }
.cb-half-open .cb-state { color: var(--color-warning); }

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
  color: var(--text-inverse);
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
  background: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error);
}

.btn-danger:hover:not(:disabled) {
  background: var(--color-error);
  color: var(--text-on-error);
}

.btn-icon {
  width: var(--spacing-4);
  height: var(--spacing-4);
  flex-shrink: 0;
}

/* ── Save Success ─────────────────────────── */

.save-success {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-success-bg);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-success);
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
