<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ErrorMonitor - Error tracking and analysis dashboard
 *
 * Displays error rates, error details, and trends across all services.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ErrorMonitor')

interface ErrorEntry {
  id: string
  timestamp: string
  service: string
  type: string
  message: string
  stack?: string
  count: number
  lastOccurred: string
  status: 'active' | 'resolved' | 'ignored'
}

interface ErrorStats {
  total: number
  last24h: number
  lastHour: number
  byService: Record<string, number>
  byType: Record<string, number>
}

const backendUrl = getBackendUrl()

// State
const errors = ref<ErrorEntry[]>([])
const stats = ref<ErrorStats>({
  total: 0,
  last24h: 0,
  lastHour: 0,
  byService: {},
  byType: {},
})
const isLoading = ref(false)
const selectedError = ref<ErrorEntry | null>(null)
const filterService = ref<string>('all')
const filterStatus = ref<string>('all')
const searchQuery = ref('')

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Services from errors
const services = computed(() => {
  const svcSet = new Set(errors.value.map(e => e.service))
  return ['all', ...Array.from(svcSet).sort()]
})

// Filtered errors
const filteredErrors = computed(() => {
  return errors.value.filter(error => {
    if (filterService.value !== 'all' && error.service !== filterService.value) return false
    if (filterStatus.value !== 'all' && error.status !== filterStatus.value) return false
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      return (
        error.message.toLowerCase().includes(query) ||
        error.type.toLowerCase().includes(query) ||
        error.service.toLowerCase().includes(query)
      )
    }
    return true
  })
})

// Top errors by count
const topErrors = computed(() => {
  return [...errors.value]
    .filter(e => e.status === 'active')
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)
})

function getStatusClass(status: string): string {
  switch (status) {
    case 'active': return 'bg-red-100 text-red-700'
    case 'resolved': return 'bg-green-100 text-green-700'
    case 'ignored': return 'bg-gray-100 text-gray-600'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function getTypeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'exception':
    case 'error': return 'text-red-600'
    case 'timeout': return 'text-orange-600'
    case 'validation': return 'text-yellow-600'
    case 'network': return 'text-blue-600'
    default: return 'text-gray-600'
  }
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelativeTime(ts: string): string {
  const date = new Date(ts)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

async function fetchErrors() {
  isLoading.value = true
  try {
    const response = await fetch(`${backendUrl}/monitoring/errors`)
    if (response.ok) {
      const data = await response.json()
      errors.value = data.errors ?? []
      stats.value = data.stats ?? stats.value
    } else {
      // Generate mock data
      generateMockData()
    }
  } catch (err) {
    logger.error('Failed to fetch errors:', err)
    generateMockData()
  } finally {
    isLoading.value = false
  }
}

function generateMockData() {
  const errorTypes = ['Exception', 'Timeout', 'Validation', 'Network', 'Database']
  const serviceList = ['slm-backend', 'fleet-manager', 'agent-worker', 'api-gateway', 'redis-cache']
  const messages = [
    'Connection refused to database',
    'Request timeout after 30s',
    'Invalid input validation failed',
    'Memory allocation failed',
    'Authentication token expired',
    'Rate limit exceeded',
    'File not found',
    'Permission denied',
  ]

  const mockErrors: ErrorEntry[] = []
  const now = Date.now()

  for (let i = 0; i < 20; i++) {
    const timestamp = new Date(now - Math.random() * 86400000 * 7).toISOString()
    mockErrors.push({
      id: `err-${i}`,
      timestamp,
      service: serviceList[Math.floor(Math.random() * serviceList.length)],
      type: errorTypes[Math.floor(Math.random() * errorTypes.length)],
      message: messages[Math.floor(Math.random() * messages.length)],
      count: Math.floor(Math.random() * 100) + 1,
      lastOccurred: new Date(now - Math.random() * 3600000).toISOString(),
      status: Math.random() > 0.7 ? 'resolved' : Math.random() > 0.9 ? 'ignored' : 'active',
    })
  }

  errors.value = mockErrors

  // Calculate stats
  const now24h = now - 86400000
  const nowHour = now - 3600000
  stats.value = {
    total: mockErrors.length,
    last24h: mockErrors.filter(e => new Date(e.timestamp).getTime() > now24h).length,
    lastHour: mockErrors.filter(e => new Date(e.timestamp).getTime() > nowHour).length,
    byService: mockErrors.reduce((acc, e) => {
      acc[e.service] = (acc[e.service] || 0) + 1
      return acc
    }, {} as Record<string, number>),
    byType: mockErrors.reduce((acc, e) => {
      acc[e.type] = (acc[e.type] || 0) + 1
      return acc
    }, {} as Record<string, number>),
  }
}

function selectError(error: ErrorEntry) {
  selectedError.value = error
}

function closeDetail() {
  selectedError.value = null
}

function updateStatus(id: string, status: 'resolved' | 'ignored') {
  const error = errors.value.find(e => e.id === id)
  if (error) {
    error.status = status
  }
}

onMounted(() => {
  fetchErrors()
  refreshInterval = setInterval(fetchErrors, 60000)
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
      <h2 class="text-xl font-bold text-gray-900">Error Monitoring</h2>
      <button
        @click="fetchErrors"
        :disabled="isLoading"
        class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': isLoading }"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Total Errors</p>
        <p class="text-2xl font-bold text-gray-900">{{ stats.total }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-red-200 p-4">
        <p class="text-sm text-red-600">Last 24 Hours</p>
        <p class="text-2xl font-bold text-red-700">{{ stats.last24h }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-orange-200 p-4">
        <p class="text-sm text-orange-600">Last Hour</p>
        <p class="text-2xl font-bold text-orange-700">{{ stats.lastHour }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-green-200 p-4">
        <p class="text-sm text-green-600">Resolved</p>
        <p class="text-2xl font-bold text-green-700">
          {{ errors.filter(e => e.status === 'resolved').length }}
        </p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Main Error List -->
      <div class="lg:col-span-2 space-y-4">
        <!-- Filters -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div class="flex flex-wrap items-center gap-4">
            <div class="flex-1 min-w-[200px]">
              <input
                v-model="searchQuery"
                type="text"
                placeholder="Search errors..."
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <select
              v-model="filterService"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option v-for="svc in services" :key="svc" :value="svc">
                {{ svc === 'all' ? 'All Services' : svc }}
              </option>
            </select>
            <select
              v-model="filterStatus"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="resolved">Resolved</option>
              <option value="ignored">Ignored</option>
            </select>
          </div>
        </div>

        <!-- Error List -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div class="max-h-[500px] overflow-y-auto divide-y divide-gray-200">
            <div
              v-for="error in filteredErrors"
              :key="error.id"
              @click="selectError(error)"
              class="p-4 hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span :class="['px-2 py-0.5 text-xs font-medium rounded', getStatusClass(error.status)]">
                      {{ error.status }}
                    </span>
                    <span :class="['text-xs font-medium', getTypeColor(error.type)]">
                      {{ error.type }}
                    </span>
                    <span class="text-xs text-gray-400">{{ error.service }}</span>
                  </div>
                  <p class="text-sm font-medium text-gray-900 truncate">{{ error.message }}</p>
                  <p class="text-xs text-gray-500 mt-1">
                    First: {{ formatTimestamp(error.timestamp) }} · Last: {{ formatRelativeTime(error.lastOccurred) }}
                  </p>
                </div>
                <div class="ml-4 text-right">
                  <p class="text-lg font-bold text-gray-900">{{ error.count }}</p>
                  <p class="text-xs text-gray-500">occurrences</p>
                </div>
              </div>
            </div>

            <div v-if="filteredErrors.length === 0" class="p-8 text-center text-gray-500">
              <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p>No errors found</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Sidebar -->
      <div class="space-y-4">
        <!-- Top Errors -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">Top Active Errors</h3>
          <div class="space-y-3">
            <div
              v-for="error in topErrors"
              :key="error.id"
              class="flex items-center justify-between"
            >
              <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-900 truncate">{{ error.message }}</p>
                <p class="text-xs text-gray-500">{{ error.service }}</p>
              </div>
              <span class="ml-2 text-sm font-bold text-red-600">{{ error.count }}</span>
            </div>
            <div v-if="topErrors.length === 0" class="text-sm text-gray-500 text-center py-2">
              No active errors
            </div>
          </div>
        </div>

        <!-- Errors by Type -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">By Error Type</h3>
          <div class="space-y-2">
            <div
              v-for="(count, type) in stats.byType"
              :key="type"
              class="flex items-center justify-between"
            >
              <span :class="['text-sm', getTypeColor(String(type))]">{{ type }}</span>
              <span class="text-sm font-medium text-gray-900">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- Errors by Service -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">By Service</h3>
          <div class="space-y-2">
            <div
              v-for="(count, service) in stats.byService"
              :key="service"
              class="flex items-center justify-between"
            >
              <span class="text-sm text-gray-600">{{ service }}</span>
              <span class="text-sm font-medium text-gray-900">{{ count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Detail Modal -->
    <div
      v-if="selectedError"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      @click.self="closeDetail"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden">
        <div class="p-4 border-b border-gray-200 flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-900">Error Details</h3>
          <button @click="closeDetail" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="p-4 overflow-y-auto max-h-[60vh]">
          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <span :class="['px-2 py-1 text-xs font-medium rounded', getStatusClass(selectedError.status)]">
                {{ selectedError.status }}
              </span>
              <span :class="['text-sm font-medium', getTypeColor(selectedError.type)]">
                {{ selectedError.type }}
              </span>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase">Service</label>
              <p class="text-sm text-gray-900">{{ selectedError.service }}</p>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase">Message</label>
              <p class="text-sm text-gray-900">{{ selectedError.message }}</p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-xs font-medium text-gray-500 uppercase">First Occurred</label>
                <p class="text-sm text-gray-900">{{ formatTimestamp(selectedError.timestamp) }}</p>
              </div>
              <div>
                <label class="text-xs font-medium text-gray-500 uppercase">Last Occurred</label>
                <p class="text-sm text-gray-900">{{ formatTimestamp(selectedError.lastOccurred) }}</p>
              </div>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase">Occurrence Count</label>
              <p class="text-2xl font-bold text-gray-900">{{ selectedError.count }}</p>
            </div>

            <div v-if="selectedError.stack">
              <label class="text-xs font-medium text-gray-500 uppercase">Stack Trace</label>
              <pre class="mt-1 p-3 bg-gray-900 text-gray-100 text-xs rounded-lg overflow-x-auto">{{ selectedError.stack }}</pre>
            </div>
          </div>
        </div>
        <div class="p-4 border-t border-gray-200 flex justify-end gap-2">
          <button
            v-if="selectedError.status === 'active'"
            @click="updateStatus(selectedError.id, 'ignored')"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            Ignore
          </button>
          <button
            v-if="selectedError.status === 'active'"
            @click="updateStatus(selectedError.id, 'resolved')"
            class="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700"
          >
            Mark Resolved
          </button>
          <button
            @click="closeDetail"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
