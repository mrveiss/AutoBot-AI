<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * BackendSettings - Backend configuration
 *
 * Configure backend server settings and connections.
 */

import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'

const authStore = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testingConnection = ref(false)
const connectionStatus = ref<'unknown' | 'connected' | 'failed'>('unknown')
const responseTime = ref<number | null>(null)

const settings = ref({
  api_endpoint: '',
  server_host: '0.0.0.0',
  server_port: 8001,
  heartbeat_timeout: '60',
  auto_reconcile: false,
  backup_retention: '30',
  log_level: 'INFO',
})

async function fetchSettings(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`${authStore.getApiUrl()}/api/settings`, {
      headers: authStore.getAuthHeaders(),
    })

    if (response.ok) {
      const data = await response.json()
      data.forEach((s: { key: string; value: string | null }) => {
        if (s.value !== null && s.key in settings.value) {
          const key = s.key as keyof typeof settings.value
          if (typeof settings.value[key] === 'boolean') {
            ;(settings.value as unknown as Record<string, boolean>)[key] = s.value === 'true'
          } else if (typeof settings.value[key] === 'number') {
            (settings.value as Record<string, any>)[key] = parseInt(s.value)
          } else {
            (settings.value as Record<string, any>)[key] = s.value
          }
        }
      })
    }

    // Set API endpoint from auth store if not in settings
    if (!settings.value.api_endpoint) {
      settings.value.api_endpoint = authStore.getApiUrl()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

async function testConnection(): Promise<void> {
  testingConnection.value = true
  connectionStatus.value = 'unknown'
  responseTime.value = null

  try {
    const startTime = Date.now()
    const response = await fetch(`${getBackendUrl()}/api/health`)

    responseTime.value = Date.now() - startTime

    if (response.ok) {
      connectionStatus.value = 'connected'
    } else {
      connectionStatus.value = 'failed'
    }
  } catch (e) {
    connectionStatus.value = 'failed'
  } finally {
    testingConnection.value = false
  }
}

async function saveSetting(key: string, value: string | number | boolean): Promise<void> {
  saving.value = true
  error.value = null
  success.value = null

  try {
    const response = await fetch(`${authStore.getApiUrl()}/api/settings/${key}`, {
      method: 'PUT',
      headers: {
        ...authStore.getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ value: String(value) }),
    })

    if (!response.ok) {
      throw new Error('Failed to save setting')
    }

    success.value = 'Setting saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save setting'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchSettings()
  testConnection()
})
</script>

<template>
  <div class="p-6">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <template v-else>
      <!-- Messages -->
      <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
        {{ error }}
      </div>
      <div v-if="success" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
        {{ success }}
      </div>

      <!-- Connection Status -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-4">
            <div
              :class="[
                'w-4 h-4 rounded-full',
                connectionStatus === 'connected' ? 'bg-green-500' : '',
                connectionStatus === 'failed' ? 'bg-red-500' : '',
                connectionStatus === 'unknown' ? 'bg-gray-400' : '',
              ]"
            ></div>
            <div>
              <p class="font-medium text-gray-900">
                {{ connectionStatus === 'connected' ? 'Connected to Backend' : connectionStatus === 'failed' ? 'Connection Failed' : 'Checking...' }}
              </p>
              <p v-if="responseTime !== null" class="text-sm text-gray-500">
                Response time: {{ responseTime }}ms
              </p>
            </div>
          </div>
          <button
            @click="testConnection"
            :disabled="testingConnection"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 flex items-center gap-2"
          >
            <svg
              :class="['w-4 h-4', { 'animate-spin': testingConnection }]"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Test
          </button>
        </div>
      </div>

      <!-- SLM Settings -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <h2 class="text-lg font-semibold mb-6">SLM Configuration</h2>

        <div class="space-y-6">
          <!-- Heartbeat Timeout -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Heartbeat Timeout</label>
              <p class="text-xs text-gray-500 mt-1">Time before a node is marked offline (seconds)</p>
            </div>
            <div class="flex gap-2">
              <input
                v-model="settings.heartbeat_timeout"
                type="number"
                min="10"
                max="300"
                class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              />
              <button
                @click="saveSetting('heartbeat_timeout', settings.heartbeat_timeout)"
                :disabled="saving"
                class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>

          <!-- Auto Reconcile -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Auto Reconciliation</label>
              <p class="text-xs text-gray-500 mt-1">Automatically attempt to fix degraded nodes</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                v-model="settings.auto_reconcile"
                @change="saveSetting('auto_reconcile', settings.auto_reconcile)"
                class="sr-only peer"
              />
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>

          <!-- Backup Retention -->
          <div class="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <label class="block text-sm font-medium text-gray-900">Backup Retention</label>
              <p class="text-xs text-gray-500 mt-1">How long to keep backup files (days)</p>
            </div>
            <select
              v-model="settings.backup_retention"
              @change="saveSetting('backup_retention', settings.backup_retention)"
              class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="7">7 days</option>
              <option value="14">14 days</option>
              <option value="30">30 days</option>
              <option value="60">60 days</option>
              <option value="90">90 days</option>
            </select>
          </div>

          <!-- Log Level -->
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-sm font-medium text-gray-900">Log Level</label>
              <p class="text-xs text-gray-500 mt-1">Backend logging verbosity</p>
            </div>
            <select
              v-model="settings.log_level"
              @change="saveSetting('log_level', settings.log_level)"
              class="w-40 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="DEBUG">Debug</option>
              <option value="INFO">Info</option>
              <option value="WARNING">Warning</option>
              <option value="ERROR">Error</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Server Info -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 class="text-lg font-semibold mb-6">Server Configuration</h2>
        <p class="text-sm text-gray-500 mb-4">
          These settings are read-only and configured in the backend.
        </p>

        <div class="space-y-4">
          <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
            <div>
              <p class="font-medium text-gray-900">API Endpoint</p>
              <p class="text-sm text-gray-500">Current backend API URL</p>
            </div>
            <p class="font-mono text-sm text-gray-700 bg-gray-100 px-3 py-1 rounded">
              {{ settings.api_endpoint || authStore.getApiUrl() }}
            </p>
          </div>

          <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
            <div>
              <p class="font-medium text-gray-900">Server Host</p>
              <p class="text-sm text-gray-500">Bind address</p>
            </div>
            <p class="font-mono text-sm text-gray-700 bg-gray-100 px-3 py-1 rounded">
              {{ settings.server_host }}
            </p>
          </div>

          <div class="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
            <div>
              <p class="font-medium text-gray-900">Server Port</p>
              <p class="text-sm text-gray-500">API port</p>
            </div>
            <p class="font-mono text-sm text-gray-700 bg-gray-100 px-3 py-1 rounded">
              {{ settings.server_port }}
            </p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
