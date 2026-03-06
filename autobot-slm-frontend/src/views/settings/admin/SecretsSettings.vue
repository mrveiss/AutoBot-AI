// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * SecretsSettings - System Secrets Management (#1417)
 *
 * Admin-only page for managing encrypted system tokens
 * (HF_TOKEN, API keys, service credentials).
 * Values are stored encrypted at rest and never displayed.
 */

import { ref, onMounted } from 'vue'
import {
  useSecretsApi,
  type SecretResponse,
  type SecretCreate,
} from '@/composables/useSecretsApi'

const api = useSecretsApi()

const loading = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const secrets = ref<SecretResponse[]>([])

const showAddForm = ref(false)
const saving = ref(false)
const newSecret = ref<SecretCreate>({
  key: '',
  value: '',
  category: 'system',
  description: '',
})

const editingKey = ref<string | null>(null)
const editValue = ref('')

const categories = [
  { value: 'system', label: 'System' },
  { value: 'api_token', label: 'API Token' },
  { value: 'service', label: 'Service' },
]

async function fetchSecrets(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    secrets.value = await api.listSecrets()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value =
      err.response?.data?.detail || 'Failed to load secrets'
  } finally {
    loading.value = false
  }
}

async function addSecret(): Promise<void> {
  if (!newSecret.value.key || !newSecret.value.value) return
  saving.value = true
  error.value = null
  try {
    await api.createSecret(newSecret.value)
    success.value = `Secret "${newSecret.value.key}" created`
    newSecret.value = { key: '', value: '', category: 'system', description: '' }
    showAddForm.value = false
    await fetchSecrets()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value =
      err.response?.data?.detail || 'Failed to create secret'
  } finally {
    saving.value = false
  }
}

async function updateSecretValue(key: string): Promise<void> {
  if (!editValue.value) return
  saving.value = true
  error.value = null
  try {
    await api.updateSecret(key, { value: editValue.value })
    success.value = `Secret "${key}" updated`
    editingKey.value = null
    editValue.value = ''
    await fetchSecrets()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value =
      err.response?.data?.detail || 'Failed to update secret'
  } finally {
    saving.value = false
  }
}

async function removeSecret(key: string): Promise<void> {
  if (!confirm(`Delete secret "${key}"? This cannot be undone.`)) return
  error.value = null
  try {
    await api.deleteSecret(key)
    success.value = `Secret "${key}" deleted`
    await fetchSecrets()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value =
      err.response?.data?.detail || 'Failed to delete secret'
  }
}

function startEdit(key: string): void {
  editingKey.value = key
  editValue.value = ''
}

function cancelEdit(): void {
  editingKey.value = null
  editValue.value = ''
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function categoryLabel(value: string): string {
  return categories.find((c) => c.value === value)?.label || value
}

onMounted(fetchSecrets)
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div
      v-if="error"
      class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3"
    >
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      {{ error }}
      <button class="ml-auto text-red-500 hover:text-red-700" @click="error = null">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div
      v-if="success"
      class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3"
    >
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      {{ success }}
    </div>

    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">System Secrets</h2>
        <p class="text-sm text-gray-500 mt-1">
          Encrypted tokens and credentials for AutoBot infrastructure. Values are never displayed.
        </p>
      </div>
      <button
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        @click="showAddForm = !showAddForm"
      >
        {{ showAddForm ? 'Cancel' : 'Add Secret' }}
      </button>
    </div>

    <!-- Add Secret Form -->
    <div v-if="showAddForm" class="bg-gray-50 border border-gray-200 rounded-lg p-5 space-y-4">
      <h3 class="font-medium text-gray-900">New Secret</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Key</label>
          <input
            v-model="newSecret.key"
            type="text"
            placeholder="e.g. HF_TOKEN"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Category</label>
          <select
            v-model="newSecret.category"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
          >
            <option v-for="cat in categories" :key="cat.value" :value="cat.value">
              {{ cat.label }}
            </option>
          </select>
        </div>
        <div class="md:col-span-2">
          <label class="block text-sm font-medium text-gray-700 mb-1">Value</label>
          <input
            v-model="newSecret.value"
            type="password"
            placeholder="Secret value (will be encrypted)"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm font-mono"
          />
        </div>
        <div class="md:col-span-2">
          <label class="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <input
            v-model="newSecret.description"
            type="text"
            placeholder="Optional description"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 text-sm"
          />
        </div>
      </div>
      <div class="flex justify-end">
        <button
          :disabled="!newSecret.key || !newSecret.value || saving"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          @click="addSecret"
        >
          {{ saving ? 'Saving...' : 'Create Secret' }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="secrets.length === 0"
      class="text-center py-12 bg-gray-50 rounded-lg border border-gray-200"
    >
      <svg
        class="mx-auto h-12 w-12 text-gray-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
        />
      </svg>
      <h3 class="mt-2 text-sm font-medium text-gray-900">No secrets configured</h3>
      <p class="mt-1 text-sm text-gray-500">Add system tokens like HF_TOKEN to get started.</p>
    </div>

    <!-- Secrets Table -->
    <div v-else class="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Key
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Category
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Description
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Updated
            </th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr v-for="secret in secrets" :key="secret.id">
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="text-sm font-mono font-medium text-gray-900">{{ secret.key }}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span
                class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                :class="{
                  'bg-blue-100 text-blue-800': secret.category === 'system',
                  'bg-purple-100 text-purple-800': secret.category === 'api_token',
                  'bg-green-100 text-green-800': secret.category === 'service',
                }"
              >
                {{ categoryLabel(secret.category) }}
              </span>
            </td>
            <td class="px-6 py-4 text-sm text-gray-500">
              {{ secret.description || '-' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ formatDate(secret.updated_at) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm">
              <template v-if="editingKey === secret.key">
                <div class="flex items-center gap-2 justify-end">
                  <input
                    v-model="editValue"
                    type="password"
                    placeholder="New value"
                    class="w-48 px-2 py-1 border border-gray-300 rounded text-sm font-mono"
                  />
                  <button
                    :disabled="!editValue || saving"
                    class="text-green-600 hover:text-green-800 disabled:opacity-50"
                    @click="updateSecretValue(secret.key)"
                  >
                    Save
                  </button>
                  <button class="text-gray-500 hover:text-gray-700" @click="cancelEdit">
                    Cancel
                  </button>
                </div>
              </template>
              <template v-else>
                <button
                  class="text-blue-600 hover:text-blue-800 mr-3"
                  @click="startEdit(secret.key)"
                >
                  Update
                </button>
                <button
                  class="text-red-600 hover:text-red-800"
                  @click="removeSecret(secret.key)"
                >
                  Delete
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Info Box -->
    <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
      <div class="flex gap-3">
        <svg
          class="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div class="text-sm text-blue-800">
          <p class="font-medium">About System Secrets</p>
          <p class="mt-1">
            Secrets are encrypted with AES-256-GCM before storage. Values are never displayed
            after creation. Use these for internal AutoBot infrastructure tokens
            (e.g. HuggingFace, external APIs) that fleet nodes need but end users should not see.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
