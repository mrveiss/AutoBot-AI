<script setup lang="ts">
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
import { useAuthStore } from '@/stores/auth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ConfigDefaultsSettings')
const authStore = useAuthStore()

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

// API helper
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${authStore.getApiUrl()}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...authStore.getAuthHeaders(), ...options?.headers },
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${response.status}`)
    }
    return await response.json()
  } catch (err) {
    errorMessage.value = `Request failed: ${err instanceof Error ? err.message : 'Unknown error'}`
    logger.error('API error:', err)
    return null
  }
}

// Actions
async function fetchDefaults(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  const result = await apiFetch<{ configs: ConfigEntry[]; total: number }>('/api/config/defaults')
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

  const result = await apiFetch<ConfigEntry>(
    `/api/config/defaults/${encodeURIComponent(key)}`,
    { method: 'PUT', body: JSON.stringify({ value: newValue.value, value_type: newValueType.value }) }
  )
  if (result) {
    successMessage.value = `Config "${key}" saved`
    showAddForm.value = false
    await fetchDefaults()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

async function deleteConfig(key: string): Promise<void> {
  if (!confirm(`Delete global config "${key}"?`)) return
  const result = await apiFetch<{ message: string }>(
    `/api/config/defaults/${encodeURIComponent(key)}`,
    { method: 'DELETE' }
  )
  if (result) {
    successMessage.value = result.message
    await fetchDefaults()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
}

function formatDate(d: string): string {
  return new Date(d).toLocaleString()
}

// Lifecycle
onMounted(() => { fetchDefaults() })
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Config Defaults</h2>
        <p class="text-sm text-gray-500">Global default configurations applied to all nodes</p>
      </div>
      <div class="flex gap-2">
        <button @click="fetchDefaults" :disabled="isLoading"
          class="px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm disabled:opacity-50">
          {{ isLoading ? 'Loading...' : 'Refresh' }}
        </button>
        <button @click="openAddForm"
          class="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
          Add Default
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <div v-if="errorMessage" class="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
      {{ errorMessage }}
      <button @click="errorMessage = null" class="ml-2 underline">Dismiss</button>
    </div>
    <div v-if="successMessage" class="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
      {{ successMessage }}
    </div>

    <!-- Add/Edit Form -->
    <div v-if="showAddForm" class="bg-white rounded-lg border">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h3 class="font-medium text-gray-900">{{ editingKey ? `Edit: ${editingKey}` : 'Add Config Default' }}</h3>
        <button @click="showAddForm = false" class="text-gray-400 hover:text-gray-600">&times;</button>
      </div>
      <form @submit.prevent="saveConfig" class="p-4 space-y-4">
        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Key *</label>
            <input v-model="newKey" :disabled="!!editingKey" required
              class="w-full px-3 py-2 border rounded-lg text-sm disabled:bg-gray-100"
              placeholder="e.g. monitoring.interval" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Value *</label>
            <input v-model="newValue" required
              class="w-full px-3 py-2 border rounded-lg text-sm" placeholder="e.g. 30" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Type</label>
            <select v-model="newValueType" class="w-full px-3 py-2 border rounded-lg text-sm">
              <option value="string">String</option>
              <option value="int">Integer</option>
              <option value="bool">Boolean</option>
              <option value="json">JSON</option>
            </select>
          </div>
        </div>
        <div class="flex gap-2">
          <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
            {{ editingKey ? 'Update' : 'Create' }}
          </button>
          <button type="button" @click="showAddForm = false"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm">Cancel</button>
        </div>
      </form>
    </div>

    <!-- Filter -->
    <div class="flex items-center gap-4">
      <input v-model="prefixFilter" placeholder="Filter by key..."
        class="px-3 py-2 border rounded-lg text-sm w-64" />
      <span class="text-sm text-gray-500">{{ filteredConfigs.length }} of {{ configs.length }} configs</span>
    </div>

    <!-- Config Table -->
    <div class="bg-white rounded-lg border">
      <table class="w-full">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Key</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Value</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Updated</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr v-for="cfg in filteredConfigs" :key="cfg.config_key" class="hover:bg-gray-50">
            <td class="px-4 py-3 text-sm font-mono text-gray-900">{{ cfg.config_key }}</td>
            <td class="px-4 py-3 text-sm text-gray-600 max-w-xs truncate" :title="cfg.config_value">
              {{ cfg.config_value }}
            </td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 text-xs rounded-full bg-gray-100 text-gray-700">{{ cfg.value_type }}</span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-500">{{ formatDate(cfg.updated_at) }}</td>
            <td class="px-4 py-3 text-right">
              <button @click="openEditForm(cfg)"
                class="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 mr-1">Edit</button>
              <button @click="deleteConfig(cfg.config_key)"
                class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredConfigs.length && !isLoading" class="p-8 text-center text-gray-500">
        No config defaults found. Click "Add Default" to create one.
      </div>
      <div v-if="isLoading" class="p-8 text-center text-gray-500">Loading configs...</div>
    </div>
  </div>
</template>
