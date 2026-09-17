<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  Admin model-pricing panel (#16825) — the live pricing refresh backend
  (GH#6480, #16228, #16231) had no reachable GUI. Surfaces per-provider
  refresh freshness, a manual refresh trigger, and price override.
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseBadge from '@/components/base/BaseBadge.vue'
import Icon from '@/components/ui/Icon.vue'
import {
  useAdminPricingApi,
  type PricingStatusResponse,
  type RefreshSummary,
} from '@/composables/useAdminPricingApi'

const { t } = useI18n()
const { fetchStatus, refreshNow, setOverride, deleteOverride } = useAdminPricingApi()

const loading = ref(false)
const refreshing = ref(false)
const error = ref<string | null>(null)
const status = ref<PricingStatusResponse>({})
const lastSummary = ref<RefreshSummary | null>(null)

const providers = computed(() => Object.entries(status.value))
const hasData = computed(() => providers.value.length > 0)

function formatTime(iso: string | null): string {
  if (!iso) return t('admin.pricing.never')
  return new Date(iso).toLocaleString()
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    status.value = await fetchStatus()
  } finally {
    loading.value = false
  }
}

async function doRefresh(): Promise<void> {
  refreshing.value = true
  error.value = null
  try {
    lastSummary.value = await refreshNow()
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('admin.pricing.refreshFailed')
  } finally {
    refreshing.value = false
  }
}

// Manual override form
const showOverrideForm = ref(false)
const overrideSaving = ref(false)
const overrideError = ref<string | null>(null)
const overrideForm = ref({
  provider: '',
  model: '',
  input_per_1m: 0,
  output_per_1m: 0,
  cache_read_per_1m: null as number | null,
  cache_write_per_1m: null as number | null,
})

function resetOverrideForm(): void {
  overrideForm.value = {
    provider: '',
    model: '',
    input_per_1m: 0,
    output_per_1m: 0,
    cache_read_per_1m: null,
    cache_write_per_1m: null,
  }
  overrideError.value = null
}

async function submitOverride(): Promise<void> {
  const { provider, model, ...prices } = overrideForm.value
  if (!provider.trim() || !model.trim()) {
    overrideError.value = t('admin.pricing.overrideRequired')
    return
  }
  overrideSaving.value = true
  overrideError.value = null
  try {
    await setOverride(provider.trim(), model.trim(), prices)
    showOverrideForm.value = false
    resetOverrideForm()
  } catch (err) {
    overrideError.value = err instanceof Error ? err.message : t('admin.pricing.overrideFailed')
  } finally {
    overrideSaving.value = false
  }
}

const removeProvider = ref('')
const removeModel = ref('')
const removing = ref(false)
const removeError = ref<string | null>(null)

async function submitRemoveOverride(): Promise<void> {
  if (!removeProvider.value.trim() || !removeModel.value.trim()) {
    removeError.value = t('admin.pricing.overrideRequired')
    return
  }
  removing.value = true
  removeError.value = null
  try {
    await deleteOverride(removeProvider.value.trim(), removeModel.value.trim())
    removeProvider.value = ''
    removeModel.value = ''
  } catch (err) {
    removeError.value = err instanceof Error ? err.message : t('admin.pricing.overrideFailed')
  } finally {
    removing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="admin-pricing view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h1 class="page-title">{{ t('admin.pricing.title') }}</h1>
        <p class="page-subtitle">{{ t('admin.pricing.subtitle') }}</p>
      </div>
      <button class="btn-action-primary" :disabled="refreshing" @click="doRefresh">
        <Icon name="sync-alt" :spin="refreshing" />
        {{ t('admin.pricing.refreshNow') }}
      </button>
    </div>

    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
    </div>

    <div v-if="lastSummary" class="summary-banner">
      {{ t('admin.pricing.refreshSummary', { written: lastSummary.written ?? 0, indexed: lastSummary.indexed ?? 0 }) }}
    </div>

    <div v-if="loading" class="loading-state">
      <Icon name="sync-alt" :spin="true" /> {{ t('admin.pricing.loading') }}
    </div>
    <div v-else-if="!hasData" class="empty-state">
      <Icon name="dollar-sign" class="empty-icon" />
      <p>{{ t('admin.pricing.empty') }}</p>
    </div>

    <div v-else class="provider-cards">
      <div v-for="[provider, s] in providers" :key="provider" class="provider-card">
        <div class="provider-card-head">
          <span class="provider-name">{{ provider }}</span>
          <BaseBadge :variant="s.success ? 'success' : 'danger'" size="sm">
            {{ s.success ? t('admin.pricing.statusOk') : t('admin.pricing.statusFailed') }}
          </BaseBadge>
        </div>
        <dl class="provider-meta">
          <div class="meta-row">
            <dt>{{ t('admin.pricing.lastRefresh') }}</dt>
            <dd>{{ formatTime(s.last_refresh_at) }}</dd>
          </div>
          <div class="meta-row">
            <dt>{{ t('admin.pricing.lastAttempt') }}</dt>
            <dd>{{ formatTime(s.last_attempt_at) }}</dd>
          </div>
          <div class="meta-row">
            <dt>{{ t('admin.pricing.modelCount') }}</dt>
            <dd>{{ s.model_count }}</dd>
          </div>
        </dl>
      </div>
    </div>

    <!-- Manual override -->
    <div class="section-card mt-6">
      <div class="section-head">
        <h2 class="section-title">{{ t('admin.pricing.overrideTitle') }}</h2>
        <button class="btn-action-secondary" @click="showOverrideForm = !showOverrideForm">
          {{ showOverrideForm ? t('common.cancel') : t('admin.pricing.overrideAdd') }}
        </button>
      </div>
      <p class="section-subtitle">{{ t('admin.pricing.overrideSubtitle') }}</p>

      <form v-if="showOverrideForm" class="override-form" @submit.prevent="submitOverride">
        <div v-if="overrideError" class="error-banner">
          <Icon name="exclamation-circle" />
          <span>{{ overrideError }}</span>
        </div>
        <div class="form-row two-col">
          <div>
            <label class="form-label">{{ t('admin.pricing.fieldProvider') }} <span class="required">*</span></label>
            <input v-model="overrideForm.provider" type="text" class="text-input" required />
          </div>
          <div>
            <label class="form-label">{{ t('admin.pricing.fieldModel') }} <span class="required">*</span></label>
            <input v-model="overrideForm.model" type="text" class="text-input" required />
          </div>
        </div>
        <div class="form-row two-col">
          <div>
            <label class="form-label">{{ t('admin.pricing.fieldInputPrice') }} <span class="required">*</span></label>
            <input v-model.number="overrideForm.input_per_1m" type="number" min="0" step="0.01" class="text-input" required />
          </div>
          <div>
            <label class="form-label">{{ t('admin.pricing.fieldOutputPrice') }} <span class="required">*</span></label>
            <input v-model.number="overrideForm.output_per_1m" type="number" min="0" step="0.01" class="text-input" required />
          </div>
        </div>
        <div class="form-row two-col">
          <div>
            <label class="form-label">{{ t('admin.pricing.fieldCacheReadPrice') }}</label>
            <input v-model.number="overrideForm.cache_read_per_1m" type="number" min="0" step="0.01" class="text-input" />
          </div>
          <div>
            <label class="form-label">{{ t('admin.pricing.fieldCacheWritePrice') }}</label>
            <input v-model.number="overrideForm.cache_write_per_1m" type="number" min="0" step="0.01" class="text-input" />
          </div>
        </div>
        <button type="submit" class="btn-action-primary" :disabled="overrideSaving">
          <Icon v-if="overrideSaving" name="sync-alt" :spin="true" />
          {{ t('admin.pricing.overrideSave') }}
        </button>
      </form>

      <form class="override-remove-form" @submit.prevent="submitRemoveOverride">
        <div v-if="removeError" class="error-banner">
          <Icon name="exclamation-circle" />
          <span>{{ removeError }}</span>
        </div>
        <label class="form-label">{{ t('admin.pricing.overrideRemove') }}</label>
        <div class="remove-row">
          <input v-model="removeProvider" type="text" class="text-input" :placeholder="t('admin.pricing.fieldProvider')" />
          <input v-model="removeModel" type="text" class="text-input" :placeholder="t('admin.pricing.fieldModel')" />
          <button type="submit" class="btn-action-danger" :disabled="removing">
            <Icon v-if="removing" name="sync-alt" :spin="true" />
            {{ t('common.delete') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.admin-pricing {
  padding: var(--spacing-6);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-6);
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  margin: 0 0 var(--spacing-1);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  margin-bottom: var(--spacing-4);
  background-color: var(--bg-danger-subtle, #fef2f2);
  color: var(--text-danger, #b91c1c);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.summary-banner {
  padding: var(--spacing-3) var(--spacing-4);
  margin-bottom: var(--spacing-4);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.loading-state,
.empty-state {
  padding: var(--spacing-12) var(--spacing-4);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.empty-icon {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-2);
}

.provider-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: var(--spacing-4);
}

.provider-card {
  padding: var(--spacing-4);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.provider-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-3);
}

.provider-name {
  font-weight: var(--font-semibold);
  text-transform: capitalize;
}

.provider-meta {
  margin: 0;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  padding: var(--spacing-1) 0;
}

.meta-row dt {
  color: var(--text-tertiary);
}

.meta-row dd {
  margin: 0;
  color: var(--text-secondary);
}

.section-card {
  padding: var(--spacing-4);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.section-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  margin: 0;
}

.section-subtitle {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin: var(--spacing-1) 0 var(--spacing-4);
}

.override-form,
.override-remove-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.form-row.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-3);
}

.form-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  margin-bottom: var(--spacing-1);
}

.required {
  color: var(--text-danger, #b91c1c);
}

.text-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.remove-row {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

.btn-action-primary,
.btn-action-secondary,
.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  border-radius: var(--radius-md);
  cursor: pointer;
  white-space: nowrap;
}

.btn-action-primary {
  color: var(--text-on-primary, #fff);
  background-color: var(--color-primary, #2563eb);
  border: 1px solid transparent;
}

.btn-action-secondary {
  color: var(--text-primary);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.btn-action-danger {
  color: var(--text-on-primary, #fff);
  background-color: var(--color-danger, #dc2626);
  border: 1px solid transparent;
}

.btn-action-primary:disabled,
.btn-action-secondary:disabled,
.btn-action-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mt-6 {
  margin-top: var(--spacing-6);
}
</style>
