<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeServicesPanel - Displays and manages systemd services on a node
 *
 * Features:
 * - Service list with status indicators (running/stopped/failed)
 * - Start/Stop/Restart buttons for each service
 * - Service log viewer modal
 * - Search and status filtering
 * - Real-time status updates via polling
 *
 * Related to Issue #728
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'
import type { NodeService, ServiceStatus } from '@/types/slm'

const logger = createLogger('NodeServicesPanel')

// Props
interface Props {
  nodeId: string
  nodeName?: string
  autoRefreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  nodeName: 'Node',
  autoRefreshInterval: 10000,
})

// Emits
const emit = defineEmits<{
  close: []
}>()

// API composable
const api = useSlmApi()

// State
const services = ref<NodeService[]>([])
const totalServices = ref(0)
const isLoading = ref(true)
const isActionInProgress = ref(false)
const actionService = ref<string | null>(null)
const lastRefresh = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

// Filter state
const statusFilter = ref<string>('all')
const searchQuery = ref('')
const autoRefresh = ref(true)

// Logs modal
const showLogsModal = ref(false)
const logsServiceName = ref<string | null>(null)
const logsContent = ref('')
const isLoadingLogs = ref(false)

// Pagination
const currentPage = ref(1)
const pageSize = 50

// Refresh interval
let refreshInterval: ReturnType<typeof setInterval> | null = null

// Status filter options
const statusOptions = [
  { value: 'all', label: 'All Status' },
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
]

// Computed
const filteredServices = computed(() => {
  let filtered = services.value

  // Apply status filter
  if (statusFilter.value !== 'all') {
    filtered = filtered.filter(s => s.status === statusFilter.value)
  }

  // Apply search filter (client-side for instant feedback)
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(s =>
      s.service_name.toLowerCase().includes(query) ||
      (s.description && s.description.toLowerCase().includes(query))
    )
  }

  return filtered
})

const statusCounts = computed(() => {
  const counts = { running: 0, stopped: 0, failed: 0, unknown: 0 }
  services.value.forEach(s => {
    if (s.status in counts) {
      counts[s.status as keyof typeof counts]++
    }
  })
  return counts
})

// Methods
function getStatusClasses(status: ServiceStatus): { bg: string; text: string; dot: string } {
  const classes: Record<ServiceStatus, { bg: string; text: string; dot: string }> = {
    running: {
      bg: 'bg-green-50',
      text: 'text-green-700',
      dot: 'bg-green-500',
    },
    stopped: {
      bg: 'bg-gray-50',
      text: 'text-gray-600',
      dot: 'bg-gray-400',
    },
    failed: {
      bg: 'bg-red-50',
      text: 'text-red-700',
      dot: 'bg-red-500',
    },
    unknown: {
      bg: 'bg-yellow-50',
      text: 'text-yellow-700',
      dot: 'bg-yellow-500',
    },
  }
  return classes[status] || classes.unknown
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return 'Never'
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  if (diffMs < 60000) return 'Just now'
  if (diffMs < 3600000) {
    const mins = Math.floor(diffMs / 60000)
    return `${mins}m ago`
  }
  if (diffMs < 86400000) {
    const hours = Math.floor(diffMs / 3600000)
    return `${hours}h ago`
  }
  const days = Math.floor(diffMs / 86400000)
  return `${days}d ago`
}

async function fetchServices(): Promise<void> {
  try {
    const response = await api.getNodeServices(props.nodeId, {
      status: statusFilter.value !== 'all' ? statusFilter.value : undefined,
      search: searchQuery.value || undefined,
      page: currentPage.value,
      per_page: pageSize,
    })

    services.value = response.services
    totalServices.value = response.total
    lastRefresh.value = new Date().toISOString()
    errorMessage.value = null
  } catch (error) {
    logger.error('Failed to fetch services:', error)
    errorMessage.value = 'Failed to load services'
  } finally {
    isLoading.value = false
  }
}

async function handleAction(serviceName: string, action: 'start' | 'stop' | 'restart'): Promise<void> {
  if (isActionInProgress.value) return

  isActionInProgress.value = true
  actionService.value = serviceName

  try {
    let result
    switch (action) {
      case 'start':
        result = await api.startService(props.nodeId, serviceName)
        break
      case 'stop':
        result = await api.stopService(props.nodeId, serviceName)
        break
      case 'restart':
        result = await api.restartService(props.nodeId, serviceName)
        break
    }

    if (result.success) {
      // Refresh services list
      await fetchServices()
    } else {
      errorMessage.value = result.message
    }
  } catch (error) {
    logger.error(`Failed to ${action} service:`, error)
    errorMessage.value = `Failed to ${action} ${serviceName}`
  } finally {
    isActionInProgress.value = false
    actionService.value = null
  }
}

async function viewLogs(serviceName: string): Promise<void> {
  logsServiceName.value = serviceName
  logsContent.value = ''
  showLogsModal.value = true
  isLoadingLogs.value = true

  try {
    const response = await api.getServiceLogs(props.nodeId, serviceName, { lines: 100 })
    logsContent.value = response.logs
  } catch (error) {
    logger.error('Failed to fetch logs:', error)
    logsContent.value = 'Failed to load logs. The service may not have any logs yet.'
  } finally {
    isLoadingLogs.value = false
  }
}

function closeLogsModal(): void {
  showLogsModal.value = false
  logsServiceName.value = null
  logsContent.value = ''
}

// Debounced search
let searchTimeout: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    currentPage.value = 1
    fetchServices()
  }, 300)
})

// Watch filter changes
watch(statusFilter, () => {
  currentPage.value = 1
  fetchServices()
})

// Watch auto-refresh changes
watch(autoRefresh, (enabled) => {
  if (enabled) {
    refreshInterval = setInterval(fetchServices, props.autoRefreshInterval)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})

// Lifecycle
onMounted(() => {
  fetchServices()

  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchServices, props.autoRefreshInterval)
  }
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
})
</script>

<template>
  <div class="bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col max-h-[700px]">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
      <div class="flex items-center gap-3">
        <h3 class="text-lg font-semibold text-gray-900">{{ nodeName }} - Services</h3>
        <div class="flex items-center gap-2 text-sm">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-green-100 text-green-700">
            <span class="w-2 h-2 rounded-full bg-green-500"></span>
            {{ statusCounts.running }}
          </span>
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-100 text-gray-600">
            <span class="w-2 h-2 rounded-full bg-gray-400"></span>
            {{ statusCounts.stopped }}
          </span>
          <span v-if="statusCounts.failed > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-100 text-red-700">
            <span class="w-2 h-2 rounded-full bg-red-500"></span>
            {{ statusCounts.failed }}
          </span>
        </div>
      </div>
      <button
        @click="emit('close')"
        class="text-gray-400 hover:text-gray-600 transition-colors"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="px-4 py-2 bg-red-50 border-b border-red-100 text-sm text-red-700 flex items-center justify-between">
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = null" class="text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Filter Bar -->
    <div class="flex items-center gap-4 px-4 py-2 bg-gray-50 border-b border-gray-200">
      <!-- Search -->
      <div class="flex-1 relative">
        <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search services..."
          class="w-full pl-9 pr-4 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
        />
      </div>

      <!-- Status Filter -->
      <div class="flex items-center gap-2">
        <label class="text-sm text-gray-600">Status:</label>
        <select
          v-model="statusFilter"
          class="text-sm border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
        >
          <option v-for="option in statusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>

      <!-- Refresh button -->
      <button
        @click="fetchServices"
        :disabled="isLoading"
        class="p-1.5 text-gray-500 hover:text-gray-700 disabled:opacity-50"
        title="Refresh"
      >
        <svg :class="['w-5 h-5', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && services.length === 0" class="flex-1 flex flex-col items-center justify-center py-12 text-gray-400">
      <svg class="w-8 h-8 animate-spin mb-3" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <span>Loading services...</span>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="filteredServices.length === 0"
      class="flex-1 flex flex-col items-center justify-center py-12 text-gray-400"
    >
      <svg class="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
      <p v-if="services.length === 0">No services discovered yet.</p>
      <p v-else>No services match the current filters.</p>
    </div>

    <!-- Services Table -->
    <div v-else class="flex-1 overflow-y-auto">
      <table class="w-full">
        <thead class="bg-gray-50 sticky top-0">
          <tr>
            <th class="w-12 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Service</th>
            <th class="w-20 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Enabled</th>
            <th class="w-24 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Memory</th>
            <th class="w-28 px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Last Check</th>
            <th class="w-36 px-4 py-2 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr
            v-for="service in filteredServices"
            :key="service.id"
            :class="[
              'hover:bg-gray-50 transition-colors',
              service.status === 'failed' ? 'bg-red-50/30' : '',
            ]"
          >
            <!-- Status -->
            <td class="px-4 py-3">
              <div
                :class="[
                  'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium',
                  getStatusClasses(service.status).bg,
                  getStatusClasses(service.status).text,
                ]"
              >
                <span :class="['w-2 h-2 rounded-full', getStatusClasses(service.status).dot]"></span>
                {{ service.status }}
              </div>
            </td>

            <!-- Service Name & Description -->
            <td class="px-4 py-3">
              <div class="font-medium text-gray-900">{{ service.service_name }}</div>
              <div v-if="service.description" class="text-xs text-gray-500 truncate max-w-xs" :title="service.description">
                {{ service.description }}
              </div>
            </td>

            <!-- Enabled -->
            <td class="px-4 py-3">
              <span
                :class="[
                  'text-xs font-medium',
                  service.enabled ? 'text-green-600' : 'text-gray-400',
                ]"
              >
                {{ service.enabled ? 'Yes' : 'No' }}
              </span>
            </td>

            <!-- Memory -->
            <td class="px-4 py-3 text-sm text-gray-600 font-mono">
              {{ formatBytes(service.memory_bytes) }}
            </td>

            <!-- Last Check -->
            <td class="px-4 py-3 text-xs text-gray-500">
              {{ formatRelativeTime(service.last_checked) }}
            </td>

            <!-- Actions -->
            <td class="px-4 py-3">
              <div class="flex items-center justify-center gap-1">
                <!-- Start -->
                <button
                  v-if="service.status !== 'running'"
                  @click="handleAction(service.service_name, 'start')"
                  :disabled="isActionInProgress"
                  class="p-1.5 text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
                  title="Start"
                >
                  <svg v-if="actionService === service.service_name" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </button>

                <!-- Stop -->
                <button
                  v-if="service.status === 'running'"
                  @click="handleAction(service.service_name, 'stop')"
                  :disabled="isActionInProgress"
                  class="p-1.5 text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                  title="Stop"
                >
                  <svg v-if="actionService === service.service_name" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" />
                  </svg>
                </button>

                <!-- Restart -->
                <button
                  @click="handleAction(service.service_name, 'restart')"
                  :disabled="isActionInProgress"
                  class="p-1.5 text-blue-600 hover:bg-blue-50 rounded disabled:opacity-50"
                  title="Restart"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>

                <!-- Logs -->
                <button
                  @click="viewLogs(service.service_name)"
                  class="p-1.5 text-gray-500 hover:bg-gray-100 rounded"
                  title="View Logs"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between px-4 py-2 bg-gray-50 border-t border-gray-200">
      <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
        <input
          type="checkbox"
          v-model="autoRefresh"
          class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
        />
        Auto-refresh (every {{ Math.round(autoRefreshInterval / 1000) }}s)
      </label>
      <div class="text-xs text-gray-500">
        <span class="font-medium text-gray-700">{{ filteredServices.length }}</span>
        of {{ totalServices }} services
        <span v-if="lastRefresh"> &bull; Updated {{ formatRelativeTime(lastRefresh) }}</span>
      </div>
    </div>

    <!-- Logs Modal -->
    <teleport to="body">
      <div v-if="showLogsModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/50" @click="closeLogsModal"></div>

        <!-- Modal -->
        <div class="relative bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col">
          <!-- Header -->
          <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
            <h3 class="text-lg font-semibold text-gray-900">
              Logs: {{ logsServiceName }}
            </h3>
            <button
              @click="closeLogsModal"
              class="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Content -->
          <div class="flex-1 overflow-auto p-4 bg-gray-900">
            <div v-if="isLoadingLogs" class="flex items-center justify-center py-12 text-gray-400">
              <svg class="w-6 h-6 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              Loading logs...
            </div>
            <pre v-else class="text-sm text-green-400 font-mono whitespace-pre-wrap">{{ logsContent }}</pre>
          </div>

          <!-- Footer -->
          <div class="px-4 py-3 border-t border-gray-200 flex justify-end">
            <button
              @click="closeLogsModal"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>
