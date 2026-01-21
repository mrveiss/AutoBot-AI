// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * LogForwardingSettings - Log Forwarding Management
 *
 * Migrated from main AutoBot frontend for Issue #729.
 * Provides management of log forwarding to external systems like Syslog, Elasticsearch, Loki.
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAutobotApi, type LogForwardingDestination } from '@/composables/useAutobotApi'

const authStore = useAuthStore()
const api = useAutobotApi()

// State
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const toggling = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

// Service status
const status = reactive({
  running: false,
  total_destinations: 0,
  enabled_destinations: 0,
  healthy_destinations: 0,
  total_sent: 0,
  total_failed: 0,
  auto_start: false,
})

// Destinations
const destinations = ref<LogForwardingDestination[]>([])

// Modal state
const showModal = ref(false)
const editingDestination = ref<LogForwardingDestination | null>(null)
const deleteTarget = ref<string | null>(null)

// Form data
const formData = reactive({
  name: '',
  type: 'syslog' as 'syslog' | 'http' | 'file' | 'elasticsearch',
  enabled: true,
  config: {
    url: '',
    host: '',
    port: 514,
    protocol: 'udp',
    file_path: '',
    api_key: '',
    username: '',
    password: '',
    index: 'autobot-logs',
    min_level: 'Information',
    batch_size: 10,
    batch_timeout: 5,
  },
})

const destinationTypes = [
  { value: 'syslog', label: 'Syslog' },
  { value: 'http', label: 'HTTP/Webhook' },
  { value: 'file', label: 'File' },
  { value: 'elasticsearch', label: 'Elasticsearch' },
]

// Known hosts for per-host targeting
const knownHosts = [
  { hostname: 'autobot-main', ip: '172.16.168.20' },
  { hostname: 'autobot-frontend', ip: '172.16.168.21' },
  { hostname: 'autobot-npu-worker', ip: '172.16.168.22' },
  { hostname: 'autobot-redis', ip: '172.16.168.23' },
  { hostname: 'autobot-ai-stack', ip: '172.16.168.24' },
  { hostname: 'autobot-browser', ip: '172.16.168.25' },
]

// Methods
async function fetchStatus(): Promise<void> {
  try {
    const response = await api.getLogForwardingStatus()
    if (response.data) {
      Object.assign(status, response.data)
    }
  } catch (e) {
    // Status endpoint may not be available
  }
}

async function fetchDestinations(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await api.getLogForwardingDestinations()
    destinations.value = response.data || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load destinations'
  } finally {
    loading.value = false
  }
}

async function toggleService(): Promise<void> {
  toggling.value = true
  error.value = null

  try {
    if (status.running) {
      await api.stopLogForwarding()
    } else {
      await api.startLogForwarding()
    }
    await fetchStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to toggle service'
  } finally {
    toggling.value = false
  }
}

async function toggleAutoStart(): Promise<void> {
  try {
    await api.setLogForwardingAutoStart(!status.auto_start)
    status.auto_start = !status.auto_start
    success.value = `Auto-start ${status.auto_start ? 'enabled' : 'disabled'}`
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update auto-start'
  }
}

function openAddModal(): void {
  editingDestination.value = null
  resetForm()
  showModal.value = true
}

function openEditModal(dest: LogForwardingDestination): void {
  editingDestination.value = dest
  formData.name = dest.name
  formData.type = dest.type
  formData.enabled = dest.enabled
  Object.assign(formData.config, dest.config)
  showModal.value = true
}

function resetForm(): void {
  formData.name = ''
  formData.type = 'syslog'
  formData.enabled = true
  formData.config = {
    url: '',
    host: '',
    port: 514,
    protocol: 'udp',
    file_path: '',
    api_key: '',
    username: '',
    password: '',
    index: 'autobot-logs',
    min_level: 'Information',
    batch_size: 10,
    batch_timeout: 5,
  }
}

function closeModal(): void {
  showModal.value = false
  editingDestination.value = null
  resetForm()
}

async function saveDestination(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    const data: LogForwardingDestination = {
      id: editingDestination.value?.id || '',
      name: formData.name,
      type: formData.type,
      enabled: formData.enabled,
      config: { ...formData.config },
    }

    if (editingDestination.value) {
      await api.updateLogForwardingDestination(editingDestination.value.id, data)
    } else {
      await api.createLogForwardingDestination(data)
    }

    success.value = `Destination ${editingDestination.value ? 'updated' : 'created'} successfully`
    closeModal()
    await fetchDestinations()
    await fetchStatus()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save destination'
  } finally {
    saving.value = false
  }
}

async function testDestination(id: string): Promise<void> {
  testing.value = true
  error.value = null

  try {
    await api.testLogForwardingDestination(id)
    success.value = 'Connection test successful'
    await fetchDestinations()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Connection test failed'
  } finally {
    testing.value = false
  }
}

async function testAllDestinations(): Promise<void> {
  testing.value = true
  error.value = null

  try {
    const response = await api.testAllLogForwardingDestinations()
    const results = response.data
    success.value = `${results?.healthy || 0}/${results?.total || 0} destinations healthy`
    await fetchDestinations()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to test destinations'
  } finally {
    testing.value = false
  }
}

function confirmDelete(name: string): void {
  deleteTarget.value = name
}

async function deleteDestination(): Promise<void> {
  if (!deleteTarget.value) return

  saving.value = true
  error.value = null

  try {
    await api.deleteLogForwardingDestination(deleteTarget.value)
    success.value = 'Destination deleted successfully'
    deleteTarget.value = null
    await fetchDestinations()
    await fetchStatus()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete destination'
  } finally {
    saving.value = false
  }
}

function getUrlPlaceholder(): string {
  switch (formData.type) {
    case 'syslog':
      return '192.168.1.100:514'
    case 'http':
      return 'https://webhook.example.com/logs'
    case 'elasticsearch':
      return 'http://elasticsearch:9200'
    default:
      return ''
  }
}

// Initialize
onMounted(async () => {
  await Promise.all([fetchStatus(), fetchDestinations()])
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Messages -->
    <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ error }}
      <button @click="error = null" class="ml-auto text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div v-if="success" class="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-3">
      <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {{ success }}
    </div>

    <!-- Service Status -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-4">
          <div
            :class="[
              'w-4 h-4 rounded-full',
              status.running ? 'bg-green-500 animate-pulse' : 'bg-red-500',
            ]"
          ></div>
          <div>
            <h2 class="text-lg font-semibold text-gray-900">
              Log Forwarding Service
            </h2>
            <p class="text-sm text-gray-500">
              {{ status.running ? 'Service Running' : 'Service Stopped' }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <button
            @click="toggleService"
            :disabled="toggling"
            :class="[
              'px-4 py-2 rounded-lg flex items-center gap-2 font-medium',
              status.running
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-green-500 text-white hover:bg-green-600',
              'disabled:opacity-50',
            ]"
          >
            <svg v-if="toggling" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path v-if="status.running" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              <path v-if="status.running" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            </svg>
            {{ status.running ? 'Stop' : 'Start' }}
          </button>

          <button
            @click="testAllDestinations"
            :disabled="testing"
            class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="testing" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Test All
          </button>

          <button
            @click="fetchStatus(); fetchDestinations()"
            class="p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Stats Grid -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="p-4 bg-gray-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-gray-900">{{ status.total_destinations }}</p>
          <p class="text-sm text-gray-500">Total</p>
        </div>
        <div class="p-4 bg-green-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-green-600">{{ status.healthy_destinations }}</p>
          <p class="text-sm text-gray-500">Healthy</p>
        </div>
        <div class="p-4 bg-blue-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-blue-600">{{ status.total_sent }}</p>
          <p class="text-sm text-gray-500">Sent</p>
        </div>
        <div class="p-4 bg-red-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-red-600">{{ status.total_failed }}</p>
          <p class="text-sm text-gray-500">Failed</p>
        </div>
      </div>

      <!-- Auto-start toggle -->
      <div class="flex items-center gap-3 pt-4 border-t border-gray-200">
        <label class="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            :checked="status.auto_start"
            @change="toggleAutoStart"
            class="sr-only peer"
          />
          <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
        </label>
        <span class="text-sm text-gray-700">Auto-start on backend startup</span>
      </div>
    </div>

    <!-- Destinations -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div class="p-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h3 class="font-semibold text-gray-900">Destinations</h3>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Add Destination
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- Empty State -->
      <div v-else-if="destinations.length === 0" class="p-8 text-center">
        <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <p class="text-gray-500 mb-4">No log forwarding destinations configured</p>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          Add Your First Destination
        </button>
      </div>

      <!-- Destinations List -->
      <div v-else class="divide-y divide-gray-100">
        <div
          v-for="dest in destinations"
          :key="dest.id"
          :class="[
            'p-4 hover:bg-gray-50 transition-colors',
            !dest.enabled && 'opacity-60',
          ]"
        >
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-3">
              <span
                :class="[
                  'px-2 py-1 rounded text-xs font-semibold uppercase',
                  dest.type === 'syslog' ? 'bg-teal-100 text-teal-700' : '',
                  dest.type === 'http' ? 'bg-pink-100 text-pink-700' : '',
                  dest.type === 'file' ? 'bg-gray-100 text-gray-700' : '',
                  dest.type === 'elasticsearch' ? 'bg-amber-100 text-amber-700' : '',
                ]"
              >
                {{ dest.type }}
              </span>
              <div>
                <h4 class="font-medium text-gray-900">{{ dest.name }}</h4>
                <p class="text-sm text-gray-500">
                  {{ dest.config.url || dest.config.host || dest.config.file_path || 'No endpoint configured' }}
                </p>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <button
                @click="testDestination(dest.id)"
                class="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded"
                title="Test Connection"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </button>
              <button
                @click="openEditModal(dest)"
                class="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded"
                title="Edit"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                @click="confirmDelete(dest.id)"
                class="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
                title="Delete"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="closeModal"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto m-4">
        <div class="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-900">
            {{ editingDestination ? 'Edit Destination' : 'Add Destination' }}
          </h3>
          <button @click="closeModal" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="p-6 space-y-4">
          <!-- Name -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name *</label>
            <input
              v-model="formData.name"
              type="text"
              :disabled="!!editingDestination"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:bg-gray-100"
              placeholder="e.g., production-syslog"
            />
          </div>

          <!-- Type -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Type *</label>
            <select
              v-model="formData.type"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option v-for="t in destinationTypes" :key="t.value" :value="t.value">
                {{ t.label }}
              </option>
            </select>
          </div>

          <!-- Syslog Config -->
          <template v-if="formData.type === 'syslog'">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Host *</label>
                <input
                  v-model="formData.config.host"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder="192.168.1.100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Port *</label>
                <input
                  v-model.number="formData.config.port"
                  type="number"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder="514"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Protocol</label>
              <select
                v-model="formData.config.protocol"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              >
                <option value="udp">UDP (unreliable, fast)</option>
                <option value="tcp">TCP (reliable)</option>
                <option value="tcp_tls">TCP + TLS (encrypted)</option>
              </select>
            </div>
          </template>

          <!-- HTTP/Webhook Config -->
          <template v-if="formData.type === 'http'">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">URL *</label>
              <input
                v-model="formData.config.url"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                :placeholder="getUrlPlaceholder()"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">API Key (optional)</label>
              <input
                v-model="formData.config.api_key"
                type="password"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </template>

          <!-- File Config -->
          <template v-if="formData.type === 'file'">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">File Path *</label>
              <input
                v-model="formData.config.file_path"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                placeholder="/var/log/autobot-forwarded.log"
              />
            </div>
          </template>

          <!-- Elasticsearch Config -->
          <template v-if="formData.type === 'elasticsearch'">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">URL *</label>
              <input
                v-model="formData.config.url"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                placeholder="http://elasticsearch:9200"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Index Name</label>
              <input
                v-model="formData.config.index"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                placeholder="autobot-logs"
              />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input
                  v-model="formData.config.username"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  v-model="formData.config.password"
                  type="password"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
          </template>

          <!-- Common Options -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Minimum Log Level</label>
            <select
              v-model="formData.config.min_level"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="Debug">Debug</option>
              <option value="Information">Information</option>
              <option value="Warning">Warning</option>
              <option value="Error">Error</option>
              <option value="Fatal">Fatal</option>
            </select>
          </div>

          <!-- Enabled Toggle -->
          <div class="flex items-center gap-3 pt-2">
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="formData.enabled" class="sr-only peer" />
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
            <span class="text-sm text-gray-700">Enabled</span>
          </div>
        </div>

        <div class="sticky bottom-0 bg-gray-50 border-t border-gray-200 p-4 flex justify-end gap-3">
          <button
            @click="closeModal"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="saveDestination"
            :disabled="saving"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ editingDestination ? 'Update' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="deleteTarget" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="deleteTarget = null"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Delete Destination</h3>
        <p class="text-gray-600 mb-6">
          Are you sure you want to delete this destination? This action cannot be undone.
        </p>
        <div class="flex justify-end gap-3">
          <button
            @click="deleteTarget = null"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="deleteDestination"
            :disabled="saving"
            class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Delete
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
