<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ErrorMonitor - Error tracking and analysis dashboard
 *
 * Issue #563: Displays error rates, error details, and trends across all services.
 * Integrates with /api/errors/* endpoints for comprehensive error monitoring.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ErrorMonitor')
const api = useSlmApi()

interface ErrorEntry {
  event_id: string
  node_id: string
  hostname: string
  event_type: string
  severity: string
  message: string
  timestamp: string
  resolved: boolean
  resolved_at: string | null
  resolved_by: string | null
}

interface ErrorStats {
  total_errors: number
  errors_24h: number
  errors_7d: number
  resolved_count: number
  unresolved_count: number
  error_rate_per_hour: number
  trend: string
}

interface CategoryBreakdown {
  category: string
  count: number
  percentage: number
}

interface ComponentBreakdown {
  node_id: string
  hostname: string
  count: number
  percentage: number
}

// State
const errors = ref<ErrorEntry[]>([])
const stats = ref<ErrorStats>({
  total_errors: 0,
  errors_24h: 0,
  errors_7d: 0,
  resolved_count: 0,
  unresolved_count: 0,
  error_rate_per_hour: 0,
  trend: 'stable',
})
const categories = ref<CategoryBreakdown[]>([])
const components = ref<ComponentBreakdown[]>([])
const isLoading = ref(false)
const selectedError = ref<ErrorEntry | null>(null)
const filterSeverity = ref<string>('all')
const filterResolved = ref<string>('all')
const searchQuery = ref('')
const currentPage = ref(1)
const totalErrors = ref(0)
const perPage = 20

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Filtered errors (client-side search only, API handles severity/resolved)
const filteredErrors = computed(() => {
  if (!searchQuery.value) return errors.value
  const query = searchQuery.value.toLowerCase()
  return errors.value.filter(
    (error) =>
      error.message.toLowerCase().includes(query) ||
      error.event_type.toLowerCase().includes(query) ||
      error.hostname.toLowerCase().includes(query)
  )
})

// Top errors by unresolved status
const topErrors = computed(() => {
  return [...errors.value].filter((e) => !e.resolved).slice(0, 5)
})

function getStatusClass(resolved: boolean): string {
  return resolved ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
}

function getSeverityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'critical':
      return 'text-red-600'
    case 'error':
      return 'text-orange-600'
    case 'warning':
      return 'text-yellow-600'
    default:
      return 'text-gray-600'
  }
}

function getTrendIcon(trend: string): string {
  switch (trend) {
    case 'increasing':
      return '↑'
    case 'decreasing':
      return '↓'
    default:
      return '→'
  }
}

function getTrendColor(trend: string): string {
  switch (trend) {
    case 'increasing':
      return 'text-red-600'
    case 'decreasing':
      return 'text-green-600'
    default:
      return 'text-gray-600'
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

async function fetchData() {
  isLoading.value = true
  try {
    // Build filter options
    const resolvedFilter =
      filterResolved.value === 'all'
        ? undefined
        : filterResolved.value === 'resolved'
    const severityFilter =
      filterSeverity.value === 'all' ? undefined : filterSeverity.value

    // Fetch all data in parallel
    const [statsData, errorsData, categoriesData, componentsData] =
      await Promise.all([
        api.getErrorStatistics(),
        api.getRecentErrors({
          page: currentPage.value,
          per_page: perPage,
          severity: severityFilter,
          resolved: resolvedFilter,
        }),
        api.getErrorCategories(24),
        api.getErrorComponents(24),
      ])

    stats.value = statsData
    errors.value = errorsData.errors
    totalErrors.value = errorsData.total
    categories.value = categoriesData.categories
    components.value = componentsData.components
  } catch (err) {
    logger.error('Failed to fetch error data:', err)
  } finally {
    isLoading.value = false
  }
}

function selectError(error: ErrorEntry) {
  selectedError.value = error
}

function closeDetail() {
  selectedError.value = null
}

async function resolveError(eventId: string) {
  try {
    await api.resolveError(eventId)
    // Refresh data after resolving
    await fetchData()
    closeDetail()
  } catch (err) {
    logger.error('Failed to resolve error:', err)
  }
}

async function createTestError() {
  try {
    await api.createTestError('error')
    await fetchData()
  } catch (err) {
    logger.error('Failed to create test error:', err)
  }
}

async function clearOldErrors() {
  if (!confirm('Clear errors older than 7 days?')) return
  try {
    const result = await api.clearErrors({ older_than_hours: 168 })
    logger.info('Cleared errors:', result.message)
    await fetchData()
  } catch (err) {
    logger.error('Failed to clear errors:', err)
  }
}

function onFilterChange() {
  currentPage.value = 1
  fetchData()
}

function nextPage() {
  if (currentPage.value * perPage < totalErrors.value) {
    currentPage.value++
    fetchData()
  }
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    fetchData()
  }
}

onMounted(() => {
  fetchData()
  refreshInterval = setInterval(fetchData, 60000)
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
      <div class="flex items-center gap-2">
        <button
          @click="clearOldErrors"
          class="px-3 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Clear Old
        </button>
        <button
          @click="createTestError"
          class="px-3 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Test Error
        </button>
        <button
          @click="fetchData"
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

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Total Errors</p>
        <p class="text-2xl font-bold text-gray-900">{{ stats.total_errors }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-red-200 p-4">
        <p class="text-sm text-red-600">Last 24 Hours</p>
        <p class="text-2xl font-bold text-red-700">{{ stats.errors_24h }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-orange-200 p-4">
        <p class="text-sm text-orange-600">Unresolved</p>
        <p class="text-2xl font-bold text-orange-700">
          {{ stats.unresolved_count }}
        </p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-green-200 p-4">
        <p class="text-sm text-green-600">Resolved</p>
        <p class="text-2xl font-bold text-green-700">
          {{ stats.resolved_count }}
        </p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-blue-200 p-4">
        <p class="text-sm text-blue-600">Trend</p>
        <p class="text-2xl font-bold" :class="getTrendColor(stats.trend)">
          {{ getTrendIcon(stats.trend) }}
          {{ stats.error_rate_per_hour.toFixed(1) }}/hr
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
              v-model="filterSeverity"
              @change="onFilterChange"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="error">Error</option>
            </select>
            <select
              v-model="filterResolved"
              @change="onFilterChange"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All Status</option>
              <option value="unresolved">Unresolved</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>
        </div>

        <!-- Error List -->
        <div
          class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
        >
          <div class="max-h-[500px] overflow-y-auto divide-y divide-gray-200">
            <div
              v-for="error in filteredErrors"
              :key="error.event_id"
              @click="selectError(error)"
              class="p-4 hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span
                      :class="[
                        'px-2 py-0.5 text-xs font-medium rounded',
                        getStatusClass(error.resolved),
                      ]"
                    >
                      {{ error.resolved ? 'resolved' : 'active' }}
                    </span>
                    <span
                      :class="[
                        'text-xs font-medium',
                        getSeverityColor(error.severity),
                      ]"
                    >
                      {{ error.severity }}
                    </span>
                    <span class="text-xs text-gray-400">{{
                      error.hostname
                    }}</span>
                  </div>
                  <p class="text-sm font-medium text-gray-900 truncate">
                    {{ error.message }}
                  </p>
                  <p class="text-xs text-gray-500 mt-1">
                    {{ error.event_type }} ·
                    {{ formatRelativeTime(error.timestamp) }}
                  </p>
                </div>
              </div>
            </div>

            <div
              v-if="filteredErrors.length === 0"
              class="p-8 text-center text-gray-500"
            >
              <svg
                class="w-12 h-12 mx-auto mb-3 text-gray-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <p>No errors found</p>
            </div>
          </div>

          <!-- Pagination -->
          <div
            v-if="totalErrors > perPage"
            class="px-4 py-3 border-t border-gray-200 flex items-center justify-between"
          >
            <span class="text-sm text-gray-500">
              Page {{ currentPage }} of {{ Math.ceil(totalErrors / perPage) }}
            </span>
            <div class="flex gap-2">
              <button
                @click="prevPage"
                :disabled="currentPage === 1"
                class="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                @click="nextPage"
                :disabled="currentPage * perPage >= totalErrors"
                class="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Sidebar -->
      <div class="space-y-4">
        <!-- Top Errors -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">
            Recent Unresolved
          </h3>
          <div class="space-y-3">
            <div
              v-for="error in topErrors"
              :key="error.event_id"
              class="flex items-center justify-between"
            >
              <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-900 truncate">
                  {{ error.message }}
                </p>
                <p class="text-xs text-gray-500">{{ error.hostname }}</p>
              </div>
              <span
                :class="[
                  'ml-2 text-xs font-medium',
                  getSeverityColor(error.severity),
                ]"
              >
                {{ error.severity }}
              </span>
            </div>
            <div
              v-if="topErrors.length === 0"
              class="text-sm text-gray-500 text-center py-2"
            >
              No unresolved errors
            </div>
          </div>
        </div>

        <!-- Errors by Category -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">By Category</h3>
          <div class="space-y-2">
            <div
              v-for="cat in categories"
              :key="cat.category"
              class="flex items-center justify-between"
            >
              <span class="text-sm text-gray-600">{{ cat.category }}</span>
              <span class="text-sm font-medium text-gray-900"
                >{{ cat.count }} ({{ cat.percentage }}%)</span
              >
            </div>
            <div
              v-if="categories.length === 0"
              class="text-sm text-gray-500 text-center py-2"
            >
              No categories
            </div>
          </div>
        </div>

        <!-- Errors by Component -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">By Node</h3>
          <div class="space-y-2">
            <div
              v-for="comp in components"
              :key="comp.node_id"
              class="flex items-center justify-between"
            >
              <span class="text-sm text-gray-600">{{ comp.hostname }}</span>
              <span class="text-sm font-medium text-gray-900"
                >{{ comp.count }} ({{ comp.percentage }}%)</span
              >
            </div>
            <div
              v-if="components.length === 0"
              class="text-sm text-gray-500 text-center py-2"
            >
              No components
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
      <div
        class="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden"
      >
        <div
          class="p-4 border-b border-gray-200 flex items-center justify-between"
        >
          <h3 class="text-lg font-semibold text-gray-900">Error Details</h3>
          <button @click="closeDetail" class="text-gray-400 hover:text-gray-600">
            <svg
              class="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div class="p-4 overflow-y-auto max-h-[60vh]">
          <div class="space-y-4">
            <div class="flex items-center gap-2">
              <span
                :class="[
                  'px-2 py-1 text-xs font-medium rounded',
                  getStatusClass(selectedError.resolved),
                ]"
              >
                {{ selectedError.resolved ? 'resolved' : 'active' }}
              </span>
              <span
                :class="[
                  'text-sm font-medium',
                  getSeverityColor(selectedError.severity),
                ]"
              >
                {{ selectedError.severity }}
              </span>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase"
                >Event ID</label
              >
              <p class="text-sm text-gray-900 font-mono">
                {{ selectedError.event_id }}
              </p>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase"
                >Node</label
              >
              <p class="text-sm text-gray-900">
                {{ selectedError.hostname }} ({{ selectedError.node_id }})
              </p>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase"
                >Type</label
              >
              <p class="text-sm text-gray-900">{{ selectedError.event_type }}</p>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase"
                >Message</label
              >
              <p class="text-sm text-gray-900">{{ selectedError.message }}</p>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500 uppercase"
                >Timestamp</label
              >
              <p class="text-sm text-gray-900">
                {{ formatTimestamp(selectedError.timestamp) }}
              </p>
            </div>

            <div v-if="selectedError.resolved">
              <label class="text-xs font-medium text-gray-500 uppercase"
                >Resolved</label
              >
              <p class="text-sm text-gray-900">
                By {{ selectedError.resolved_by }} at
                {{ formatTimestamp(selectedError.resolved_at || '') }}
              </p>
            </div>
          </div>
        </div>
        <div class="p-4 border-t border-gray-200 flex justify-end gap-2">
          <button
            v-if="!selectedError.resolved"
            @click="resolveError(selectedError.event_id)"
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
