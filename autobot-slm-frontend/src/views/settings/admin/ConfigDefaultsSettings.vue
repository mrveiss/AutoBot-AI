<script setup lang="ts">
import { BaseAlert, createLogger } from '@autobot/ui'
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ConfigDefaultsSettings - Global Config Defaults Management (Issue #839)
 *
 * CRUD interface for global default configurations.
 * Wires 4 endpoints: GET /config/defaults, GET /config/defaults/{key},
 * PUT /config/defaults/{key}, DELETE /config/defaults/{key}
 */

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import slmApiClient from '@/utils/ApiClient'
import { formatFleetDateTime } from '@/composables/useTimezone'

const logger = createLogger('ConfigDefaultsSettings')
const { t } = useI18n()

// Types
interface ConfigEntry {
  id: number
  node_id: string | null
  config_key: string
  config_value: string
  value_type: string
  is_global: boolean
  created_at: string
  updated_at: string
}

// State
const configs = ref<ConfigEntry[]>([])
const isLoading = ref(false)
const prefixFilter = ref('')
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const showAddForm = ref(false)
const editingKey = ref<string | null>(null)

const newKey = ref('')
const newValue = ref('')
const newValueType = ref('string')

// Computed
const filteredConfigs = computed(() => {
  if (!prefixFilter.value) return configs.value
  const p = prefixFilter.value.toLowerCase()
  return configs.value.filter(c => c.config_key.toLowerCase().includes(p))
})

// API helper — migrated onto slmApiClient (#12420 Phase 2). The client resolves
// the base URL via getSlmApiBase(), injects the SLM bearer token, and centrally
// handles 401 for these non-auth endpoints (clear session + redirect to /login).
// It returns parsed JSON directly and throws `Error('HTTP <status>: <detail>')`
// on failure, so the null-on-error contract to callers is preserved.
async function apiRequest<T>(
  method: 'GET' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown
): Promise<T | null> {
  try {
    if (method === 'GET') return await slmApiClient.get<T>(path)
    if (method === 'PUT') return await slmApiClient.put<T>(path, body)
    return await slmApiClient.delete<T>(path)
  } catch (err) {
    errorMessage.value = t('settings.admin.configDefaultsSettings.requestFailed', { detail: err instanceof Error ? err.message : t('settings.admin.configDefaultsSettings.unknownError') })
    logger.error('API error:', err)
    return null
  }
}

// Actions
async function fetchDefaults(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  const result = await apiRequest<{ configs: ConfigEntry[]; total: number }>('GET', '/config/defaults')
  if (result) configs.value = result.configs
  isLoading.value = false
}

function openAddForm(): void {
  editingKey.value = null
  newKey.value = ''
  newValue.value = ''
  newValueType.value = 'string'
  showAddForm.value = true
}

function openEditForm(entry: ConfigEntry): void {
  editingKey.value = entry.config_key
  newKey.value = entry.config_key
  newValue.value = entry.config_value
  newValueType.value = entry.value_type
  showAddForm.value = true
}

async function saveConfig(): Promise<void> {
  errorMessage.value = null
  const key = editingKey.value || newKey.value
  if (!key) { errorMessage.value = 'Key is required'; return }

  const result = await apiRequest<ConfigEntry>(
    'PUT',
    `/config/defaults/${encodeURIComponent(key)}`,
    { value: newValue.value, value_type: newValueType.value }
  )
  if (result) {
    successMessage.value = t('settings.admin.configDefaultsSettings.configSaved', { key })
    showAddForm.value = false
    await fetchDefaults()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

async function deleteConfig(key: string): Promise<void> {
  if (!confirm(t('settings.admin.configDefaultsSettings.deleteGlobalConfig', { key }))) return
  const result = await apiRequest<{ message: string }>(
    'DELETE',
    `/config/defaults/${encodeURIComponent(key)}`
  )
  if (result) {
    successMessage.value = result.message
    await fetchDefaults()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

// Lifecycle
onMounted(() => { fetchDefaults() })
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('settings.admin.configDefaultsSettings.configDefaults') }}</h2>
        <p class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.configDefaultsSettings.globalDefaultConfigurationsApplied') }}</p>
      </div>
      <div class="flex gap-2">
        <button @click="fetchDefaults" :disabled="isLoading"
          class="px-3 py-2 border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover text-sm disabled:opacity-50">
          {{ isLoading ? $t('settings.admin.configDefaultsSettings.loading') : $t('settings.admin.configDefaultsSettings.refresh') }}
        </button>
        <button @click="openAddForm"
          class="px-3 py-2 bg-autobot-primary text-autobot-text-on-primary rounded-lg hover:bg-autobot-primary-hover text-sm">
          {{ $t('settings.admin.configDefaultsSettings.addDefault') }}
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <BaseAlert v-if="errorMessage" variant="error" :message="errorMessage" dismissible :dismiss-label="$t('settings.admin.configDefaultsSettings.dismiss')" @dismiss="errorMessage = null" />
    <BaseAlert v-if="successMessage" variant="success" size="compact" :message="successMessage" />

    <!-- Add/Edit Form -->
    <div v-if="showAddForm" class="bg-white rounded-lg border">
      <div class="px-4 py-3 bg-autobot-bg-secondary border-b flex items-center justify-between">
        <h3 class="font-medium text-autobot-text-primary">{{ editingKey ? $t('settings.admin.configDefaultsSettings.editKey', { key: editingKey }) : $t('settings.admin.configDefaultsSettings.addConfigDefault') }}</h3>
        <button @click="showAddForm = false" class="text-autobot-text-tertiary hover:text-autobot-text-secondary">{{ $t('settings.admin.configDefaultsSettings.times') }}</button>
      </div>
      <form @submit.prevent="saveConfig" class="p-4 space-y-4">
        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.configDefaultsSettings.key') }}</label>
            <input v-model="newKey" :disabled="!!editingKey" required
              class="w-full px-3 py-2 border rounded-lg text-sm disabled:bg-autobot-bg-tertiary"
              :placeholder="$t('settings.admin.configDefaultsSettings.eGMonitoringInterval')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.configDefaultsSettings.value') }}</label>
            <input v-model="newValue" required
              class="w-full px-3 py-2 border rounded-lg text-sm" :placeholder="$t('settings.admin.configDefaultsSettings.egThirty')" />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('settings.admin.configDefaultsSettings.type') }}</label>
            <select v-model="newValueType" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="string">{{ $t('settings.admin.configDefaultsSettings.string') }}</option>
              <option value="int">{{ $t('settings.admin.configDefaultsSettings.integer') }}</option>
              <option value="bool">{{ $t('settings.admin.configDefaultsSettings.boolean') }}</option>
              <option value="json">{{ $t('settings.admin.configDefaultsSettings.jSON') }}</option>
            </select>
          </div>
        </div>
        <div class="flex gap-2">
          <button type="submit" class="px-4 py-2 bg-autobot-primary text-autobot-text-on-primary rounded-lg hover:bg-autobot-primary-hover text-sm">
            {{ editingKey ? $t('settings.admin.configDefaultsSettings.update') : $t('settings.admin.configDefaultsSettings.create') }}
          </button>
          <button type="button" @click="showAddForm = false"
            class="px-4 py-2 border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover text-sm">{{ $t('settings.admin.configDefaultsSettings.cancel') }}</button>
        </div>
      </form>
    </div>

    <!-- Filter -->
    <div class="flex items-center gap-4">
      <input v-model="prefixFilter" :placeholder="$t('settings.admin.configDefaultsSettings.filterByKey')"
        class="px-3 py-2 border rounded-lg text-sm w-64" />
      <span class="text-sm text-autobot-text-tertiary">{{ $t('settings.admin.configDefaultsSettings.countOfCount2Configs', { count: filteredConfigs.length, count2: configs.length }) }}</span>
    </div>

    <!-- Config Table -->
    <div class="bg-white rounded-lg border">
      <table class="w-full">
        <thead class="bg-autobot-bg-secondary">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('settings.admin.configDefaultsSettings.key1') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('settings.admin.configDefaultsSettings.value1') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('settings.admin.configDefaultsSettings.type') }}</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('settings.admin.configDefaultsSettings.updated') }}</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('settings.admin.configDefaultsSettings.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-autobot-border">
          <tr v-for="cfg in filteredConfigs" :key="cfg.config_key" class="hover:bg-autobot-bg-hover">
            <td class="px-4 py-3 text-sm font-mono text-autobot-text-primary">{{ cfg.config_key }}</td>
            <td class="px-4 py-3 text-sm text-autobot-text-secondary max-w-xs truncate" :title="cfg.config_value">
              {{ cfg.config_value }}
            </td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 text-xs rounded-full bg-autobot-bg-tertiary text-autobot-text-secondary">{{ cfg.value_type }}</span>
            </td>
            <td class="px-4 py-3 text-sm text-autobot-text-tertiary">{{ formatFleetDateTime(cfg.updated_at) }}</td>
            <td class="px-4 py-3 text-right">
              <button @click="openEditForm(cfg)"
                class="px-2 py-1 text-xs bg-autobot-bg-tertiary text-autobot-text-secondary rounded-sm hover:bg-autobot-bg-active mr-1">{{ $t('settings.admin.configDefaultsSettings.edit') }}</button>
              <button @click="deleteConfig(cfg.config_key)"
                class="px-2 py-1 text-xs bg-autobot-pill-bad-bg text-autobot-pill-bad-fg rounded-sm hover:bg-autobot-pill-bad-bg">{{ $t('settings.admin.configDefaultsSettings.delete') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredConfigs.length && !isLoading" class="p-8 text-center text-autobot-text-tertiary">
        {{ $t('settings.admin.configDefaultsSettings.noConfigDefaultsFound') }}
      </div>
      <div v-if="isLoading" class="p-8 text-center text-autobot-text-tertiary">{{ $t('settings.admin.configDefaultsSettings.loadingConfigs') }}</div>
    </div>
  </div>
</template>
