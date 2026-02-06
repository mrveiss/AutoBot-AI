// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUWorkersSettings - NPU Worker Management
 *
 * Migrated from main AutoBot frontend for Issue #729.
 * Provides management of distributed NPU workers for AI processing.
 */

import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAutobotApi, type NPUWorker } from '@/composables/useAutobotApi'

const authStore = useAuthStore()
const api = useAutobotApi()

// State
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testingWorker = ref<Record<string, boolean>>({})

// Workers data
const workers = ref<NPUWorker[]>([])

// Load balancing config
const loadBalancingConfig = reactive({
  strategy: 'round-robin',
  health_check_interval: 30,
  max_retries: 3,
  retry_delay: 5,
})

// Modal state
const showModal = ref(false)
const editingWorker = ref<NPUWorker | null>(null)
const deleteTarget = ref<NPUWorker | null>(null)

// Form data
const workerForm = reactive({
  name: '',
  platform: 'linux',
  ip_address: '',
  port: 8081,
  enabled: true,
  priority: 1,
  weight: 1,
  capabilities: [] as string[],
})

// Metrics modal
const showMetrics = ref(false)
const selectedWorkerMetrics = ref<NPUWorker | null>(null)

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Computed
const healthyWorkers = computed(() =>
  workers.value.filter(w => w.status === 'online').length
)

const busyWorkers = computed(() =>
  workers.value.filter(w => w.status === 'busy').length
)

const offlineWorkers = computed(() =>
  workers.value.filter(w => w.status === 'offline' || w.status === 'error').length
)

// Methods
async function fetchWorkers(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await api.getNPUWorkers()
    workers.value = response.data || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load workers'
  } finally {
    loading.value = false
  }
}

async function fetchLoadBalancingConfig(): Promise<void> {
  try {
    const response = await api.getNPULoadBalancingConfig()
    if (response.data) {
      Object.assign(loadBalancingConfig, response.data)
    }
  } catch (e) {
    // Config endpoint may not be available
  }
}

async function saveLoadBalancingConfig(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    await api.updateNPULoadBalancingConfig(loadBalancingConfig)
    success.value = 'Load balancing configuration saved'
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save configuration'
  } finally {
    saving.value = false
  }
}

function openAddModal(): void {
  editingWorker.value = null
  resetForm()
  showModal.value = true
}

function openEditModal(worker: NPUWorker): void {
  editingWorker.value = worker
  workerForm.name = worker.hostname
  workerForm.ip_address = worker.ip_address
  workerForm.platform = 'linux'
  workerForm.enabled = worker.status !== 'offline'
  workerForm.capabilities = worker.capabilities || []
  showModal.value = true
}

function resetForm(): void {
  workerForm.name = ''
  workerForm.platform = 'linux'
  workerForm.ip_address = ''
  workerForm.port = 8081
  workerForm.enabled = true
  workerForm.priority = 1
  workerForm.weight = 1
  workerForm.capabilities = []
}

function closeModal(): void {
  showModal.value = false
  editingWorker.value = null
  resetForm()
}

async function saveWorker(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    if (editingWorker.value) {
      await api.updateNPUWorker(editingWorker.value.id, {
        hostname: workerForm.name,
        ip_address: workerForm.ip_address,
        capabilities: workerForm.capabilities,
      })
    } else {
      await api.pairNPUWorker({
        name: workerForm.name,
        ip_address: workerForm.ip_address,
        port: workerForm.port,
        platform: workerForm.platform,
      })
    }

    success.value = `Worker ${editingWorker.value ? 'updated' : 'paired'} successfully`
    closeModal()
    await fetchWorkers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save worker'
  } finally {
    saving.value = false
  }
}

async function testWorker(worker: NPUWorker): Promise<void> {
  testingWorker.value[worker.id] = true
  error.value = null

  try {
    await api.testNPUWorker(worker.id)
    success.value = `Connection to ${worker.hostname} successful`
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Connection test failed'
  } finally {
    testingWorker.value[worker.id] = false
  }
}

async function restartWorker(worker: NPUWorker): Promise<void> {
  if (!confirm(`Are you sure you want to restart ${worker.hostname}?`)) return

  saving.value = true
  error.value = null

  try {
    await api.restartNPUWorker(worker.id)
    success.value = `Restart signal sent to ${worker.hostname}`
    await fetchWorkers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to restart worker'
  } finally {
    saving.value = false
  }
}

function confirmDelete(worker: NPUWorker): void {
  deleteTarget.value = worker
}

async function deleteWorker(): Promise<void> {
  if (!deleteTarget.value) return

  saving.value = true
  error.value = null

  try {
    await api.removeNPUWorker(deleteTarget.value.id)
    success.value = 'Worker removed successfully'
    deleteTarget.value = null
    await fetchWorkers()
    setTimeout(() => { success.value = null }, 3000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to remove worker'
  } finally {
    saving.value = false
  }
}

function viewMetrics(worker: NPUWorker): void {
  selectedWorkerMetrics.value = worker
  showMetrics.value = true
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'online': return 'bg-green-100 text-green-700'
    case 'busy': return 'bg-amber-100 text-amber-700'
    case 'offline': return 'bg-gray-100 text-gray-700'
    case 'error': return 'bg-red-100 text-red-700'
    default: return 'bg-gray-100 text-gray-700'
  }
}

function getStatusDot(status: string): string {
  switch (status) {
    case 'online': return 'bg-green-500'
    case 'busy': return 'bg-amber-500'
    case 'offline': return 'bg-gray-400'
    case 'error': return 'bg-red-500'
    default: return 'bg-gray-400'
  }
}

function getLoadColor(load: number): string {
  if (load < 50) return 'bg-green-500'
  if (load < 80) return 'bg-amber-500'
  return 'bg-red-500'
}

// Initialize
onMounted(async () => {
  await Promise.all([fetchWorkers(), fetchLoadBalancingConfig()])
  refreshInterval = setInterval(fetchWorkers, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
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

    <!-- Header -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">NPU Worker Management</h2>
          <p class="text-sm text-gray-500 mt-1">Manage distributed NPU workers for AI processing</p>
        </div>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          Pair Worker
        </button>
      </div>

      <!-- Stats Grid -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="p-4 bg-gray-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-gray-900">{{ workers.length }}</p>
          <p class="text-sm text-gray-500">Total Workers</p>
        </div>
        <div class="p-4 bg-green-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-green-600">{{ healthyWorkers }}</p>
          <p class="text-sm text-gray-500">Online</p>
        </div>
        <div class="p-4 bg-amber-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-amber-600">{{ busyWorkers }}</p>
          <p class="text-sm text-gray-500">Busy</p>
        </div>
        <div class="p-4 bg-red-50 rounded-lg text-center">
          <p class="text-2xl font-bold text-red-600">{{ offlineWorkers }}</p>
          <p class="text-sm text-gray-500">Offline</p>
        </div>
      </div>
    </div>

    <!-- Load Balancing Configuration -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 class="font-semibold text-gray-900 mb-4 flex items-center gap-2">
        <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
        </svg>
        Load Balancing Configuration
      </h3>

      <div class="grid md:grid-cols-2 gap-6">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Strategy</label>
          <select
            v-model="loadBalancingConfig.strategy"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="round-robin">Round Robin</option>
            <option value="least-loaded">Least Loaded</option>
            <option value="weighted">Weighted</option>
            <option value="priority">Priority Based</option>
          </select>
          <p class="text-xs text-gray-500 mt-1">Distribution strategy for task allocation</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Health Check Interval (seconds)</label>
          <input
            v-model.number="loadBalancingConfig.health_check_interval"
            type="number"
            min="5"
            max="300"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
          <p class="text-xs text-gray-500 mt-1">Seconds between health checks</p>
        </div>
      </div>

      <div class="mt-4 flex justify-end">
        <button
          @click="saveLoadBalancingConfig"
          :disabled="saving"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
        >
          <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          Save Configuration
        </button>
      </div>
    </div>

    <!-- Workers List -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div class="p-4 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h3 class="font-semibold text-gray-900">Registered Workers ({{ workers.length }})</h3>
        <button
          @click="fetchWorkers"
          :disabled="loading"
          class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded"
        >
          <svg :class="['w-5 h-5', loading && 'animate-spin']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading && workers.length === 0" class="flex items-center justify-center py-12">
        <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- Empty State -->
      <div v-else-if="workers.length === 0" class="p-8 text-center">
        <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <p class="text-gray-500 mb-4">No NPU workers registered</p>
        <button
          @click="openAddModal"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          Pair Your First Worker
        </button>
      </div>

      <!-- Workers Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200 bg-gray-50">
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Worker</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Load</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Capabilities</th>
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-500">Last Heartbeat</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="worker in workers" :key="worker.id" class="border-b border-gray-100 hover:bg-gray-50">
              <!-- Worker Info -->
              <td class="py-3 px-4">
                <div>
                  <p class="font-medium text-gray-900">{{ worker.hostname }}</p>
                  <p class="text-sm text-gray-500">{{ worker.ip_address }}</p>
                </div>
              </td>

              <!-- Status -->
              <td class="py-3 px-4">
                <span
                  :class="[
                    'inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium',
                    getStatusColor(worker.status),
                  ]"
                >
                  <span :class="['w-2 h-2 rounded-full', getStatusDot(worker.status)]"></span>
                  {{ worker.status }}
                </span>
              </td>

              <!-- Load -->
              <td class="py-3 px-4">
                <div class="w-24">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 bg-gray-200 rounded-full h-2">
                      <div
                        :class="['h-2 rounded-full', getLoadColor(worker.current_load)]"
                        :style="{ width: worker.current_load + '%' }"
                      ></div>
                    </div>
                    <span class="text-sm text-gray-600">{{ worker.current_load }}%</span>
                  </div>
                </div>
              </td>

              <!-- Capabilities -->
              <td class="py-3 px-4">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="cap in worker.capabilities?.slice(0, 3)"
                    :key="cap"
                    class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs"
                  >
                    {{ cap }}
                  </span>
                  <span
                    v-if="(worker.capabilities?.length || 0) > 3"
                    class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs"
                  >
                    +{{ (worker.capabilities?.length || 0) - 3 }}
                  </span>
                </div>
              </td>

              <!-- Last Heartbeat -->
              <td class="py-3 px-4 text-sm text-gray-600">
                {{ worker.last_heartbeat || 'Never' }}
              </td>

              <!-- Actions -->
              <td class="py-3 px-4">
                <div class="flex items-center justify-end gap-1">
                  <button
                    @click="testWorker(worker)"
                    :disabled="testingWorker[worker.id]"
                    class="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded disabled:opacity-50"
                    title="Test connection"
                  >
                    <svg v-if="testingWorker[worker.id]" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </button>
                  <button
                    @click="viewMetrics(worker)"
                    class="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded"
                    title="View metrics"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </button>
                  <button
                    @click="restartWorker(worker)"
                    class="p-2 text-gray-400 hover:text-amber-500 hover:bg-amber-50 rounded"
                    title="Restart"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                  <button
                    @click="openEditModal(worker)"
                    class="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded"
                    title="Edit"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    @click="confirmDelete(worker)"
                    class="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
                    title="Remove"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Add/Edit Worker Modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="closeModal"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          {{ editingWorker ? 'Edit Worker' : 'Pair New Worker' }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Worker Name *</label>
            <input
              v-model="workerForm.name"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="e.g., NPU-Worker-VM2"
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Platform *</label>
              <select
                v-model="workerForm.platform"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              >
                <option value="linux">Linux</option>
                <option value="windows">Windows</option>
                <option value="macos">macOS</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Port *</label>
              <input
                v-model.number="workerForm.port"
                type="number"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                placeholder="8081"
              />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">IP Address *</label>
            <input
              v-model="workerForm.ip_address"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              placeholder="172.16.168.22"
            />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="closeModal"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="saveWorker"
            :disabled="saving"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ editingWorker ? 'Update' : 'Pair Worker' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="deleteTarget" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="deleteTarget = null"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Remove Worker</h3>
        <p class="text-gray-600 mb-6">
          Are you sure you want to remove <strong>{{ deleteTarget.hostname }}</strong>? This action cannot be undone.
        </p>
        <div class="flex justify-end gap-3">
          <button
            @click="deleteTarget = null"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="deleteWorker"
            :disabled="saving"
            class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="saving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Remove
          </button>
        </div>
      </div>
    </div>

    <!-- Metrics Modal -->
    <div v-if="showMetrics && selectedWorkerMetrics" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="showMetrics = false"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-900">{{ selectedWorkerMetrics.hostname }} Metrics</h3>
          <button @click="showMetrics = false" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div class="p-4 bg-gray-50 rounded-lg">
              <p class="text-sm text-gray-500">Current Load</p>
              <p class="text-xl font-semibold text-gray-900">{{ selectedWorkerMetrics.current_load }}%</p>
            </div>
            <div class="p-4 bg-gray-50 rounded-lg">
              <p class="text-sm text-gray-500">Status</p>
              <p class="text-xl font-semibold" :class="selectedWorkerMetrics.status === 'online' ? 'text-green-600' : 'text-gray-600'">
                {{ selectedWorkerMetrics.status }}
              </p>
            </div>
          </div>

          <div class="p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-500 mb-2">Capabilities</p>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="cap in selectedWorkerMetrics.capabilities"
                :key="cap"
                class="px-2 py-1 bg-white border border-gray-200 rounded text-sm"
              >
                {{ cap }}
              </span>
            </div>
          </div>

          <div class="p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-500">Last Heartbeat</p>
            <p class="font-medium text-gray-900">{{ selectedWorkerMetrics.last_heartbeat || 'Never' }}</p>
          </div>
        </div>

        <div class="mt-6 flex justify-end">
          <button
            @click="showMetrics = false"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
