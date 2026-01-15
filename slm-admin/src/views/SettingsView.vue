<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

interface Setting {
  key: string
  value: string | null
  value_type: string
  description: string | null
}

const authStore = useAuthStore()
const activeTab = ref('general')
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const settings = ref<Record<string, string>>({
  monitoring_location: 'local',
  prometheus_url: 'http://localhost:9090',
  grafana_url: 'http://localhost:3000',
  heartbeat_timeout: '60',
  auto_reconcile: 'false',
})

const tabs = [
  { id: 'general', name: 'General', icon: 'cog' },
  { id: 'monitoring', name: 'Monitoring', icon: 'chart' },
  { id: 'slm', name: 'SLM Configuration', icon: 'server' },
  { id: 'notifications', name: 'Notifications', icon: 'bell' },
  { id: 'api', name: 'API Settings', icon: 'code' },
]

async function fetchSettings(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`${authStore.getApiUrl()}/api/settings`, {
      headers: authStore.getAuthHeaders(),
    })

    if (!response.ok) {
      throw new Error('Failed to fetch settings')
    }

    const data: Setting[] = await response.json()
    data.forEach((s) => {
      if (s.value !== null) {
        settings.value[s.key] = s.value
      }
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load settings'
  } finally {
    loading.value = false
  }
}

async function saveSetting(key: string, value: string): Promise<void> {
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
      body: JSON.stringify({ value }),
    })

    if (!response.ok) {
      throw new Error('Failed to save setting')
    }

    settings.value[key] = value
    success.value = 'Setting saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save setting'
  } finally {
    saving.value = false
  }
}

async function saveAllSettings(): Promise<void> {
  saving.value = true
  error.value = null
  success.value = null

  try {
    for (const [key, value] of Object.entries(settings.value)) {
      await fetch(`${authStore.getApiUrl()}/api/settings/${key}`, {
        method: 'PUT',
        headers: {
          ...authStore.getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value }),
      })
    }
    success.value = 'All settings saved successfully'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save settings'
  } finally {
    saving.value = false
  }
}

async function deployMonitoringRole(): Promise<void> {
  // Placeholder for Ansible deployment trigger
  alert('Monitoring role deployment will be triggered via Ansible')
}

onMounted(fetchSettings)
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Settings</h1>
      <p class="text-sm text-gray-500 mt-1">
        Configure system settings and preferences
      </p>
    </div>

    <!-- Messages -->
    <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      {{ error }}
    </div>
    <div v-if="success" class="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
      {{ success }}
    </div>

    <div class="flex gap-6">
      <!-- Sidebar -->
      <div class="w-48 shrink-0">
        <nav class="space-y-1">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors',
              activeTab === tab.id
                ? 'bg-primary-100 text-primary-700'
                : 'text-gray-600 hover:bg-gray-100'
            ]"
          >
            {{ tab.name }}
          </button>
        </nav>
      </div>

      <!-- Content -->
      <div class="flex-1 card p-6">
        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-8">
          <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>

        <template v-else>
          <!-- General Settings -->
          <div v-if="activeTab === 'general'">
            <h2 class="text-lg font-semibold mb-4">General Settings</h2>

            <div class="space-y-4">
              <div>
                <label class="label">System Name</label>
                <input type="text" class="input" value="AutoBot Production" />
              </div>

              <div>
                <label class="label">Default Timezone</label>
                <select class="input">
                  <option>UTC</option>
                  <option>America/New_York</option>
                  <option>Europe/London</option>
                  <option>Asia/Tokyo</option>
                </select>
              </div>

              <div>
                <label class="flex items-center gap-2">
                  <input type="checkbox" class="rounded border-gray-300" checked />
                  <span class="text-sm text-gray-700">Enable dark mode</span>
                </label>
              </div>
            </div>
          </div>

          <!-- Monitoring Settings -->
          <div v-else-if="activeTab === 'monitoring'">
            <h2 class="text-lg font-semibold mb-4">Monitoring Configuration</h2>
            <p class="text-sm text-gray-500 mb-6">
              Configure where Prometheus and Grafana monitoring services are hosted.
            </p>

            <div class="space-y-6">
              <!-- Monitoring Location -->
              <div>
                <label class="label">Monitoring Location</label>
                <select
                  v-model="settings.monitoring_location"
                  class="input"
                  @change="saveSetting('monitoring_location', settings.monitoring_location)"
                >
                  <option value="local">Local (on this admin machine)</option>
                  <option value="external">External (separate host)</option>
                </select>
                <p class="text-xs text-gray-500 mt-1">
                  Choose where monitoring services (Prometheus/Grafana) are running.
                </p>
              </div>

              <!-- Prometheus URL -->
              <div>
                <label class="label">Prometheus URL</label>
                <div class="flex gap-2">
                  <input
                    v-model="settings.prometheus_url"
                    type="text"
                    class="input flex-1"
                    placeholder="http://localhost:9090"
                  />
                  <button
                    @click="saveSetting('prometheus_url', settings.prometheus_url)"
                    class="btn btn-secondary"
                    :disabled="saving"
                  >
                    Save
                  </button>
                </div>
                <p class="text-xs text-gray-500 mt-1">
                  URL to access Prometheus. Use localhost if running locally.
                </p>
              </div>

              <!-- Grafana URL -->
              <div>
                <label class="label">Grafana URL</label>
                <div class="flex gap-2">
                  <input
                    v-model="settings.grafana_url"
                    type="text"
                    class="input flex-1"
                    placeholder="http://localhost:3000"
                  />
                  <button
                    @click="saveSetting('grafana_url', settings.grafana_url)"
                    class="btn btn-secondary"
                    :disabled="saving"
                  >
                    Save
                  </button>
                </div>
                <p class="text-xs text-gray-500 mt-1">
                  URL to access Grafana. Use localhost if running locally.
                </p>
              </div>

              <!-- Deploy Monitoring Role -->
              <div class="pt-4 border-t border-gray-200">
                <h3 class="font-medium mb-2">Deploy Monitoring Stack</h3>
                <p class="text-sm text-gray-500 mb-3">
                  Use Ansible to deploy or migrate the monitoring stack to a different node.
                </p>
                <button
                  @click="deployMonitoringRole"
                  class="btn btn-primary"
                >
                  <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Deploy Monitoring Role
                </button>
              </div>
            </div>
          </div>

          <!-- SLM Configuration -->
          <div v-else-if="activeTab === 'slm'">
            <h2 class="text-lg font-semibold mb-4">SLM Configuration</h2>

            <div class="space-y-4">
              <div>
                <label class="label">Heartbeat Timeout (seconds)</label>
                <div class="flex gap-2">
                  <input
                    v-model="settings.heartbeat_timeout"
                    type="number"
                    class="input flex-1"
                  />
                  <button
                    @click="saveSetting('heartbeat_timeout', settings.heartbeat_timeout)"
                    class="btn btn-secondary"
                    :disabled="saving"
                  >
                    Save
                  </button>
                </div>
                <p class="text-xs text-gray-500 mt-1">
                  Time before a node is marked offline if no heartbeat received.
                </p>
              </div>

              <div>
                <label class="flex items-center gap-2">
                  <input
                    type="checkbox"
                    class="rounded border-gray-300"
                    :checked="settings.auto_reconcile === 'true'"
                    @change="saveSetting('auto_reconcile', settings.auto_reconcile === 'true' ? 'false' : 'true')"
                  />
                  <span class="text-sm text-gray-700">Enable auto-reconciliation</span>
                </label>
                <p class="text-xs text-gray-500 mt-1 ml-6">
                  Automatically attempt to fix degraded nodes.
                </p>
              </div>

              <div>
                <label class="label">Backup Retention (days)</label>
                <input type="number" class="input" value="30" />
              </div>
            </div>
          </div>

          <!-- Notifications -->
          <div v-else-if="activeTab === 'notifications'">
            <h2 class="text-lg font-semibold mb-4">Notification Settings</h2>

            <div class="space-y-4">
              <div>
                <label class="flex items-center gap-2">
                  <input type="checkbox" class="rounded border-gray-300" checked />
                  <span class="text-sm text-gray-700">Node health alerts</span>
                </label>
              </div>

              <div>
                <label class="flex items-center gap-2">
                  <input type="checkbox" class="rounded border-gray-300" checked />
                  <span class="text-sm text-gray-700">Deployment notifications</span>
                </label>
              </div>

              <div>
                <label class="flex items-center gap-2">
                  <input type="checkbox" class="rounded border-gray-300" checked />
                  <span class="text-sm text-gray-700">Backup completion alerts</span>
                </label>
              </div>

              <div>
                <label class="flex items-center gap-2">
                  <input type="checkbox" class="rounded border-gray-300" />
                  <span class="text-sm text-gray-700">Maintenance window reminders</span>
                </label>
              </div>
            </div>
          </div>

          <!-- API Settings -->
          <div v-else-if="activeTab === 'api'">
            <h2 class="text-lg font-semibold mb-4">API Settings</h2>

            <div class="space-y-4">
              <div>
                <label class="label">Backend API URL</label>
                <input
                  type="text"
                  class="input bg-gray-50"
                  :value="authStore.getApiUrl()"
                  readonly
                />
              </div>

              <div>
                <label class="label">WebSocket URL</label>
                <input
                  type="text"
                  class="input bg-gray-50"
                  :value="authStore.getApiUrl().replace('http', 'ws') + '/ws'"
                  readonly
                />
              </div>

              <div>
                <label class="label">Request Timeout (ms)</label>
                <input type="number" class="input" value="30000" />
              </div>
            </div>
          </div>

          <!-- Save Button -->
          <div class="mt-6 pt-4 border-t border-gray-200 flex justify-end">
            <button
              @click="saveAllSettings"
              class="btn btn-primary"
              :disabled="saving"
            >
              <svg v-if="saving" class="animate-spin w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ saving ? 'Saving...' : 'Save All Changes' }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
