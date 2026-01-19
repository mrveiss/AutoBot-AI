<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ServicesView - Fleet-wide service management dashboard
 *
 * Provides a centralized view of all systemd services across the fleet
 * with the ability to start/stop services across multiple nodes.
 *
 * Related to Issue #728
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type { FleetServiceStatus, ServiceStatus } from '@/types/slm'

const logger = createLogger('ServicesView')
const api = useSlmApi()
const fleetStore = useFleetStore()

// State
const services = ref<FleetServiceStatus[]>([])
const totalServices = ref(0)
const isLoading = ref(true)
const errorMessage = ref<string | null>(null)
const lastRefresh = ref<string | null>(null)

// Filters
const searchQuery = ref('')
const statusFilter = ref<string>('all')
const autoRefresh = ref(true)
const autoRefreshInterval = 15000

// Action state
const isActionInProgress = ref(false)
const actionService = ref<string | null>(null)
const actionType = ref<string | null>(null)

// Refresh interval
let refreshInterval: ReturnType<typeof setInterval> | null = null

// Status filter options
const statusOptions = [
  { value: 'all', label: 'All Services' },
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
  { value: 'mixed', label: 'Mixed Status' },
]

// Computed
const filteredServices = computed(() => {
  let filtered = services.value

  // Apply status filter
  if (statusFilter.value !== 'all') {
    if (statusFilter.value === 'mixed') {
      filtered = filtered.filter(s =>
        s.running_count > 0 && s.running_count < s.total_nodes
      )
    } else if (statusFilter.value === 'running') {
      filtered = filtered.filter(s => s.running_count === s.total_nodes)
    } else if (statusFilter.value === 'stopped') {
      filtered = filtered.filter(s => s.stopped_count === s.total_nodes)
    } else if (statusFilter.value === 'failed') {
      filtered = filtered.filter(s => s.failed_count > 0)
    }
  }

  // Apply search filter
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(s =>
      s.service_name.toLowerCase().includes(query)
    )
  }

  return filtered
})

const summaryStats = computed(() => {
  const total = services.value.length
  const allRunning = services.value.filter(s => s.running_count === s.total_nodes).length
  const allStopped = services.value.filter(s => s.stopped_count === s.total_nodes).length
  const hasFailed = services.value.filter(s => s.failed_count > 0).length
  const mixed = total - allRunning - allStopped

  return { total, allRunning, allStopped, hasFailed, mixed }
})

// Methods
function getServiceStatusClass(service: FleetServiceStatus): string {
  if (service.failed_count > 0) return 'bg-red-100 text-red-700 border-red-200'
  if (service.running_count === service.total_nodes) return 'bg-green-100 text-green-700 border-green-200'
  if (service.stopped_count === service.total_nodes) return 'bg-gray-100 text-gray-600 border-gray-200'
  return 'bg-yellow-100 text-yellow-700 border-yellow-200'
}

function getServiceStatusText(service: FleetServiceStatus): string {
  if (service.failed_count > 0) return `${service.failed_count} failed`
  if (service.running_count === service.total_nodes) return 'All running'
  if (service.stopped_count === service.total_nodes) return 'All stopped'
  return `${service.running_count}/${service.total_nodes} running`
}

function getNodeStatusDot(status: ServiceStatus): string {
  switch (status) {
    case 'running': return 'bg-green-500'
    case 'stopped': return 'bg-gray-400'
    case 'failed': return 'bg-red-500'
    default: return 'bg-yellow-500'
  }
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
    const response = await api.getFleetServices()
    services.value = response.services
    totalServices.value = response.total_services
    lastRefresh.value = new Date().toISOString()
    errorMessage.value = null
  } catch (error) {
    logger.error('Failed to fetch fleet services:', error)
    errorMessage.value = 'Failed to load services'
  } finally {
    isLoading.value = false
  }
}

async function handleFleetAction(
  serviceName: string,
  action: 'start' | 'stop'
): Promise<void> {
  if (isActionInProgress.value) return

  isActionInProgress.value = true
  actionService.value = serviceName
  actionType.value = action

  try {
    let result
    if (action === 'start') {
      result = await api.startFleetService(serviceName)
    } else {
      result = await api.stopFleetService(serviceName)
    }

    if (result.success) {
      // Refresh services list
      await fetchServices()
    } else {
      errorMessage.value = result.message
    }
  } catch (error) {
    logger.error(`Failed to ${action} fleet service:`, error)
    errorMessage.value = `Failed to ${action} ${serviceName} across fleet`
  } finally {
    isActionInProgress.value = false
    actionService.value = null
    actionType.value = null
  }
}

// Watch auto-refresh changes
function toggleAutoRefresh(): void {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchServices, autoRefreshInterval)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

// Lifecycle
onMounted(() => {
  fetchServices()
  fleetStore.fetchNodes()

  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchServices, autoRefreshInterval)
  }
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Fleet Services</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage systemd services across all fleet nodes
        </p>
      </div>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            :checked="autoRefresh"
            @change="toggleAutoRefresh"
            class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
          />
          Auto-refresh
        </label>
        <button
          @click="fetchServices"
          :disabled="isLoading"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', isLoading ? 'animate-spin' : '']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
      <div class="card p-4">
        <div class="text-sm text-gray-500">Total Services</div>
        <div class="text-2xl font-bold text-gray-900">{{ summaryStats.total }}</div>
      </div>
      <div class="card p-4 border-l-4 border-green-500">
        <div class="text-sm text-gray-500">All Running</div>
        <div class="text-2xl font-bold text-green-600">{{ summaryStats.allRunning }}</div>
      </div>
      <div class="card p-4 border-l-4 border-gray-400">
        <div class="text-sm text-gray-500">All Stopped</div>
        <div class="text-2xl font-bold text-gray-600">{{ summaryStats.allStopped }}</div>
      </div>
      <div class="card p-4 border-l-4 border-yellow-500">
        <div class="text-sm text-gray-500">Mixed Status</div>
        <div class="text-2xl font-bold text-yellow-600">{{ summaryStats.mixed }}</div>
      </div>
      <div class="card p-4 border-l-4 border-red-500">
        <div class="text-sm text-gray-500">Has Failures</div>
        <div class="text-2xl font-bold text-red-600">{{ summaryStats.hasFailed }}</div>
      </div>
    </div>

    <!-- Error Banner -->
    <div
      v-if="errorMessage"
      class="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center justify-between"
    >
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = null" class="text-red-500 hover:text-red-700">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Filter Bar -->
    <div class="card mb-6">
      <div class="flex items-center gap-4 p-4">
        <!-- Search -->
        <div class="flex-1 relative">
          <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search services..."
            class="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Status Filter -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600">Status:</label>
          <select
            v-model="statusFilter"
            class="border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500"
          >
            <option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && services.length === 0" class="card p-12 text-center">
      <svg class="w-8 h-8 animate-spin mx-auto mb-3 text-gray-400" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      <p class="text-gray-500">Loading fleet services...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="services.length === 0" class="card p-12 text-center">
      <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">No services discovered</h3>
      <p class="text-gray-500">
        Services will appear here once agents report their discovered systemd services.
      </p>
    </div>

    <!-- No Results -->
    <div v-else-if="filteredServices.length === 0" class="card p-12 text-center">
      <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">No matching services</h3>
      <p class="text-gray-500">
        Try adjusting your search or filter criteria.
      </p>
    </div>

    <!-- Services Grid -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        v-for="service in filteredServices"
        :key="service.service_name"
        class="card p-4"
      >
        <!-- Service Header -->
        <div class="flex items-start justify-between mb-3">
          <div>
            <h3 class="font-semibold text-gray-900">{{ service.service_name }}</h3>
            <span
              :class="[
                'inline-flex items-center px-2 py-0.5 mt-1 text-xs font-medium rounded border',
                getServiceStatusClass(service)
              ]"
            >
              {{ getServiceStatusText(service) }}
            </span>
          </div>
          <div class="flex items-center gap-1">
            <!-- Start All -->
            <button
              v-if="service.stopped_count > 0"
              @click="handleFleetAction(service.service_name, 'start')"
              :disabled="isActionInProgress"
              class="p-1.5 text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
              title="Start on all nodes"
            >
              <svg
                v-if="actionService === service.service_name && actionType === 'start'"
                class="w-5 h-5 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              <svg v-else class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </button>

            <!-- Stop All -->
            <button
              v-if="service.running_count > 0"
              @click="handleFleetAction(service.service_name, 'stop')"
              :disabled="isActionInProgress"
              class="p-1.5 text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
              title="Stop on all nodes"
            >
              <svg
                v-if="actionService === service.service_name && actionType === 'stop'"
                class="w-5 h-5 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
              </svg>
              <svg v-else class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Node Status Grid -->
        <div class="border-t border-gray-100 pt-3">
          <div class="text-xs text-gray-500 mb-2">Status per node:</div>
          <div class="flex flex-wrap gap-2">
            <div
              v-for="node in service.nodes"
              :key="node.node_id"
              class="flex items-center gap-1.5 px-2 py-1 bg-gray-50 rounded text-xs"
              :title="`${node.hostname}: ${node.status}`"
            >
              <span :class="['w-2 h-2 rounded-full', getNodeStatusDot(node.status)]"></span>
              <span class="text-gray-700 truncate max-w-[100px]">{{ node.hostname }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="mt-6 text-center text-sm text-gray-500">
      <span class="font-medium text-gray-700">{{ filteredServices.length }}</span>
      of {{ totalServices }} services
      <span v-if="lastRefresh"> &bull; Last updated {{ formatRelativeTime(lastRefresh) }}</span>
    </div>
  </div>
</template>
