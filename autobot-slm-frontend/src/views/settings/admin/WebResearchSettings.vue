// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025-2026 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * WebResearchSettings - the one editor for the platform-wide web research settings (#19217).
 *
 * Reads and writes the main backend's /web-research routes. Every write is admin-only and
 * global, so the main app shows a read-only status that links here. A save sends only the
 * fields that changed; a `saved_not_applied` answer means saved but not yet taken by the
 * running researcher, and is shown as a warning, never as plain success.
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { BaseAlert, BaseSwitch } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import { autobotApiErrorMessage } from '@/composables/useAutobotApi'
import {
  useWebResearchAdminApi,
  isSavedNotApplied,
  isWebResearcherUnavailable,
  type WebResearchSettings,
  type WebResearchSettingsUpdate,
  type WebResearchStatusData,
} from '@/composables/useWebResearchAdminApi'

const { t } = useI18n()
const api = useWebResearchAdminApi()
const NS = 'settings.admin.webResearchSettings'

type NumericKey =
  | 'max_results' | 'timeout_seconds' | 'auto_research_threshold' | 'rate_limit_requests'
  | 'rate_limit_window' | 'daily_limit' | 'quality_threshold'
type BooleanKey = 'require_user_confirmation' | 'store_results_in_kb' | 'filter_adult_content' | 'anonymize_requests'
type EditableKey = NumericKey | BooleanKey | 'preferred_method'

// Ranges match WebResearchSettingsUpdate in autobot-backend/api/schemas_web_research.py.
const NUMERIC: { key: NumericKey; min: number; max?: number; step: number }[] = [
  { key: 'max_results', min: 1, max: 50, step: 1 },
  { key: 'timeout_seconds', min: 5, max: 120, step: 1 },
  { key: 'auto_research_threshold', min: 0, max: 1, step: 0.05 },
  { key: 'rate_limit_requests', min: 1, max: 100, step: 1 },
  { key: 'rate_limit_window', min: 10, max: 3600, step: 1 },
  { key: 'daily_limit', min: 1, step: 1 },
  { key: 'quality_threshold', min: 0, max: 1, step: 0.05 },
]
const BOOLEANS: BooleanKey[] = ['require_user_confirmation', 'store_results_in_kb', 'filter_adult_content', 'anonymize_requests']
const METHODS = ['basic', 'advanced', 'api_based'] as const
const EDITABLE: EditableKey[] = [...NUMERIC.map((n) => n.key), ...BOOLEANS, 'preferred_method']
// Saved by the backend but not yet read by the researcher.
const NOT_ENFORCED = new Set<EditableKey>([
  'anonymize_requests', 'filter_adult_content', 'store_results_in_kb', 'auto_research_threshold',
  'daily_limit', 'quality_threshold', 'require_user_confirmation',
])

const loading = ref(false)
const saving = ref(false)
const toggling = ref(false)
const working = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const warning = ref<string | null>(null)

const saved = ref<WebResearchSettings | null>(null)
const form = reactive<Record<string, unknown>>({})
// 'unavailable' is the 503: the researcher failed to start, which is not a page error.
const statusState = ref<'unknown' | 'ok' | 'unavailable' | 'degraded' | 'error'>('unknown')
const status = ref<WebResearchStatusData | null>(null)

function syncForm(settings: WebResearchSettings): void {
  saved.value = settings
  for (const key of EDITABLE) form[key] = settings[key]
}

const changes = computed<WebResearchSettingsUpdate>(() => {
  const out: Record<string, unknown> = {}
  if (!saved.value) return out
  for (const key of EDITABLE) if (form[key] !== saved.value[key]) out[key] = form[key]
  return out as WebResearchSettingsUpdate
})
const hasChanges = computed(() => Object.keys(changes.value).length > 0)

function isInvalid(field: { key: NumericKey; min: number; max?: number; step: number }): boolean {
  const v = form[field.key]
  if (typeof v !== 'number' || Number.isNaN(v) || v < field.min) return true
  if (field.max !== undefined && v > field.max) return true
  return field.step === 1 && !Number.isInteger(v)
}
const anyInvalid = computed(() => NUMERIC.some(isInvalid))

function rangeHint(field: { min: number; max?: number }): string {
  return field.max === undefined
    ? t(`${NS}.atLeast`, { min: field.min })
    : t(`${NS}.range`, { min: field.min, max: field.max })
}

const cacheStats = computed(() => (status.value?.cache_stats ?? {}) as { cache_size?: number; rate_limiter?: { current_requests?: number; max_requests?: number } })
const breakers = computed(() => Object.entries(status.value?.circuit_breakers ?? {}))

async function loadSettings(): Promise<void> {
  try {
    syncForm(await api.getSettings())
  } catch (e) {
    error.value = autobotApiErrorMessage(e, t(`${NS}.loadFailed`))
  }
}

async function loadStatus(): Promise<void> {
  try {
    status.value = await api.getStatus()
    statusState.value = status.value.status === 'success' ? 'ok' : 'degraded'
  } catch (e) {
    status.value = null
    if (isWebResearcherUnavailable(e)) {
      statusState.value = 'unavailable'
    } else {
      statusState.value = 'error'
      error.value = autobotApiErrorMessage(e, t(`${NS}.statusFailed`))
    }
  }
}

function clearMessages(): void {
  error.value = null
  success.value = null
  warning.value = null
}

async function refreshAll(): Promise<void> {
  loading.value = true
  clearMessages()
  await Promise.all([loadSettings(), loadStatus()])
  loading.value = false
}

function report(result: { status: string }, okMessage: string): void {
  if (isSavedNotApplied(result)) warning.value = t(`${NS}.savedNotApplied`)
  else success.value = okMessage
}

async function save(): Promise<void> {
  if (saving.value || anyInvalid.value || !hasChanges.value) return
  saving.value = true
  clearMessages()
  try {
    const result = await api.updateSettings(changes.value)
    syncForm(result.settings)
    report(result, t(`${NS}.saved`))
    await loadStatus()
  } catch (e) {
    error.value = autobotApiErrorMessage(e, t(`${NS}.saveFailed`))
  } finally {
    saving.value = false
  }
}

function discard(): void {
  if (saved.value) syncForm(saved.value)
}

async function setEnabled(next: boolean): Promise<void> {
  if (toggling.value || !saved.value) return
  toggling.value = true
  clearMessages()
  try {
    const result = await (next ? api.enable() : api.disable())
    saved.value = { ...saved.value, enabled: result.enabled }
    report(result, t(next ? `${NS}.enabledMessage` : `${NS}.disabledMessage`))
    await loadStatus()
  } catch (e) {
    error.value = autobotApiErrorMessage(e, t(`${NS}.toggleFailed`))
  } finally {
    toggling.value = false
  }
}

async function runAction(action: () => Promise<{ message: string }>, failed: string, okMessage: string): Promise<void> {
  working.value = true
  clearMessages()
  try {
    await action()
    success.value = okMessage
    await loadStatus()
  } catch (e) {
    error.value = autobotApiErrorMessage(e, failed)
  } finally {
    working.value = false
  }
}
const clearCache = () => runAction(api.clearCache, t(`${NS}.clearCacheFailed`), t(`${NS}.cacheCleared`))
const resetBreakers = () => runAction(api.resetCircuitBreakers, t(`${NS}.resetBreakersFailed`), t(`${NS}.breakersReset`))

onMounted(refreshAll)
</script>

<template>
  <div class="p-6 space-y-6">
    <BaseAlert v-if="error" variant="error" :message="error" dismissible :dismiss-label="$t('settings.admin.webResearchSettings.dismiss')" @dismiss="error = null" />
    <BaseAlert v-if="warning" variant="warning" data-test="saved-not-applied" :message="warning" dismissible :dismiss-label="$t('settings.admin.webResearchSettings.dismiss')" @dismiss="warning = null" />
    <BaseAlert v-if="success" variant="success" :message="success" dismissible :dismiss-label="$t('settings.admin.webResearchSettings.dismiss')" @dismiss="success = null" />

    <!-- Status -->
    <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('settings.admin.webResearchSettings.title') }}</h2>
          <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.webResearchSettings.subtitle') }}</p>
        </div>
        <div class="flex items-center gap-3">
          <BaseSwitch
            :model-value="saved?.enabled ?? false"
            :label="$t('settings.admin.webResearchSettings.enableSwitch')"
            :disabled="!saved || toggling || statusState === 'unavailable'"
            data-test="enable-switch"
            @change="setEnabled"
          />
          <span class="text-sm text-autobot-text-secondary">{{ $t('settings.admin.webResearchSettings.enableSwitch') }}</span>
          <button type="button" data-test="refresh" class="px-3 py-2 text-sm bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-hover disabled:opacity-50" :disabled="loading" @click="refreshAll">
            {{ $t('settings.admin.webResearchSettings.refresh') }}
          </button>
        </div>
      </div>

      <BaseAlert v-if="statusState === 'unavailable'" variant="warning" data-test="researcher-unavailable" :title="$t('settings.admin.webResearchSettings.unavailableTitle')" :message="$t('settings.admin.webResearchSettings.unavailableHint')" class="mb-4" />
      <BaseAlert v-else-if="statusState === 'degraded'" variant="warning" data-test="researcher-degraded" :message="status?.message || $t('settings.admin.webResearchSettings.degradedHint')" class="mb-4" />

      <dl class="grid grid-cols-2 md:grid-cols-5 gap-4" data-test="status-cards">
        <div class="bg-autobot-bg-secondary rounded-lg p-4">
          <dt class="text-xs uppercase text-autobot-text-tertiary">{{ $t('settings.admin.webResearchSettings.statusEnabled') }}</dt>
          <dd class="text-lg font-semibold text-autobot-text-primary" data-test="card-enabled">{{ saved ? (saved.enabled ? $t('settings.admin.webResearchSettings.yes') : $t('settings.admin.webResearchSettings.no')) : $t('settings.admin.webResearchSettings.unknown') }}</dd>
        </div>
        <div class="bg-autobot-bg-secondary rounded-lg p-4">
          <dt class="text-xs uppercase text-autobot-text-tertiary">{{ $t('settings.admin.webResearchSettings.statusMethod') }}</dt>
          <dd class="text-lg font-semibold text-autobot-text-primary" data-test="card-method">{{ status?.preferred_method ? $t(`settings.admin.webResearchSettings.method_${status.preferred_method}`) : $t('settings.admin.webResearchSettings.unknown') }}</dd>
        </div>
        <div class="bg-autobot-bg-secondary rounded-lg p-4">
          <dt class="text-xs uppercase text-autobot-text-tertiary">{{ $t('settings.admin.webResearchSettings.statusCache') }}</dt>
          <dd class="text-lg font-semibold text-autobot-text-primary" data-test="card-cache">{{ cacheStats.cache_size ?? $t('settings.admin.webResearchSettings.unknown') }}</dd>
        </div>
        <div class="bg-autobot-bg-secondary rounded-lg p-4">
          <dt class="text-xs uppercase text-autobot-text-tertiary">{{ $t('settings.admin.webResearchSettings.statusRateLimiter') }}</dt>
          <dd class="text-lg font-semibold text-autobot-text-primary" data-test="card-rate">{{ cacheStats.rate_limiter ? $t('settings.admin.webResearchSettings.rateLimiterValue', { current: cacheStats.rate_limiter.current_requests ?? 0, max: cacheStats.rate_limiter.max_requests ?? 0 }) : $t('settings.admin.webResearchSettings.unknown') }}</dd>
        </div>
        <div class="bg-autobot-bg-secondary rounded-lg p-4">
          <dt class="text-xs uppercase text-autobot-text-tertiary">{{ $t('settings.admin.webResearchSettings.statusResearcher') }}</dt>
          <dd class="text-lg font-semibold text-autobot-text-primary" data-test="card-researcher">{{ $t(`settings.admin.webResearchSettings.researcher_${statusState}`) }}</dd>
        </div>
      </dl>

      <div class="flex flex-wrap items-center gap-3 mt-4">
        <button type="button" data-test="clear-cache" class="px-4 py-2 text-sm bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-hover disabled:opacity-50" :disabled="working || statusState === 'unavailable'" @click="clearCache">
          {{ $t('settings.admin.webResearchSettings.clearCache') }}
        </button>
        <button v-if="breakers.length > 0" type="button" data-test="reset-breakers" class="px-4 py-2 text-sm bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-hover disabled:opacity-50" :disabled="working" @click="resetBreakers">
          {{ $t('settings.admin.webResearchSettings.resetBreakers', { count: breakers.length }) }}
        </button>
      </div>
    </div>

    <!-- Settings form -->
    <form v-if="saved" class="bg-white rounded-lg shadow-xs border border-autobot-border p-6 space-y-6" data-test="settings-form" @submit.prevent="save">
      <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('settings.admin.webResearchSettings.formTitle') }}</h2>

      <div>
        <label for="wr-preferred_method" class="block text-sm font-medium text-autobot-text-primary">{{ $t('settings.admin.webResearchSettings.field_preferred_method') }}</label>
        <select id="wr-preferred_method" v-model="form.preferred_method" class="mt-1 w-48 px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-autobot-primary">
          <option v-for="m in METHODS" :key="m" :value="m">{{ $t(`settings.admin.webResearchSettings.method_${m}`) }}</option>
        </select>
      </div>

      <div v-for="field in NUMERIC" :key="field.key">
        <label :for="`wr-${field.key}`" class="block text-sm font-medium text-autobot-text-primary">{{ $t(`settings.admin.webResearchSettings.field_${field.key}`) }}</label>
        <input
          :id="`wr-${field.key}`"
          v-model.number="form[field.key]"
          type="number"
          :min="field.min"
          :max="field.max"
          :step="field.step"
          :aria-invalid="isInvalid(field)"
          :aria-describedby="`wr-${field.key}-hint`"
          class="mt-1 w-32 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-autobot-primary"
          :class="isInvalid(field) ? 'border-autobot-error' : 'border-autobot-border-strong'"
        />
        <!-- error-hover (#dc2626, 4.8:1 on white) is the AA-safe red for small text; the plain error token is 3.8:1 -->
        <p :id="`wr-${field.key}-hint`" class="text-xs mt-1" :class="isInvalid(field) ? 'text-autobot-error-hover' : 'text-autobot-text-tertiary'">{{ rangeHint(field) }}</p>
        <p v-if="NOT_ENFORCED.has(field.key)" class="text-xs text-autobot-text-secondary mt-1" data-test="not-enforced">{{ $t('settings.admin.webResearchSettings.notEnforced') }}</p>
      </div>

      <div v-for="key in BOOLEANS" :key="key">
        <div class="flex items-center gap-3">
          <BaseSwitch :model-value="Boolean(form[key])" @update:model-value="form[key] = $event" :label="$t(`settings.admin.webResearchSettings.field_${key}`)" />
          <span class="text-sm font-medium text-autobot-text-primary">{{ $t(`settings.admin.webResearchSettings.field_${key}`) }}</span>
        </div>
        <p v-if="NOT_ENFORCED.has(key)" class="text-xs text-autobot-text-secondary mt-1" data-test="not-enforced">{{ $t('settings.admin.webResearchSettings.notEnforced') }}</p>
      </div>

      <div class="flex items-center gap-3 pt-4 border-t border-autobot-border">
        <button type="submit" data-test="save" class="px-4 py-2 bg-autobot-primary text-white rounded-lg hover:bg-autobot-primary-hover disabled:opacity-50" :disabled="saving || !hasChanges || anyInvalid">
          {{ saving ? $t('settings.admin.webResearchSettings.saving') : $t('settings.admin.webResearchSettings.save') }}
        </button>
        <button type="button" data-test="discard" class="px-4 py-2 bg-autobot-bg-tertiary text-autobot-text-secondary rounded-lg hover:bg-autobot-bg-hover disabled:opacity-50" :disabled="saving || !hasChanges" @click="discard">
          {{ $t('settings.admin.webResearchSettings.discard') }}
        </button>
      </div>
    </form>
  </div>
</template>
