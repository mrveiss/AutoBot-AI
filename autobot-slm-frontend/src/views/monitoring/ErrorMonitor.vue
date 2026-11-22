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

import { ref, computed, onMounted } from 'vue'
import { BaseModal, usePagination, BasePagination, PollingPausedAlert, createLogger, createDateFormatter } from '@autobot/ui'
import { throwUnlessLoaded, useDashboardPoller } from '@/composables/useDashboardPoller'
import { useSlmApi } from '@/composables/useSlmApi'
import type {
  RecentError,
  ErrorStatistics,
  ErrorCategoryShare,
  ComponentBreakdown,
} from '@/types/api-responses'
import { formatCompactRelativeTime } from '@/utils/dateUtils'
import { getTimezoneOption } from '@/composables/useTimezone'
import i18n from '@/i18n'

const logger = createLogger('ErrorMonitor')
const api = useSlmApi()

// State
const errors = ref<RecentError[]>([])
const stats = ref<ErrorStatistics>({
  total_errors: 0,
  errors_24h: 0,
  errors_7d: 0,
  errors_30d: 0,
  resolved_count: 0,
  unresolved_count: 0,
  error_rate_per_hour: 0,
  trend: 'stable',
})
const categories = ref<ErrorCategoryShare[]>([])
const components = ref<ComponentBreakdown[]>([])
const isLoading = ref(false)
const selectedError = ref<RecentError | null>(null)
const filterSeverity = ref<string>('all')
const filterResolved = ref<string>('all')
const searchQuery = ref('')
const totalErrors = ref(0)

// Server-side pagination via shared @autobot/ui composable (#10885).
// The API owns the page slice; the composable drives page state + navigation
// and re-fetches through onPageChange. serverTotalItems tracks the reactive
// total so page-count/next/prev stay in sync after each fetch.
const {
  currentPage,
  totalPages,
  itemsPerPage: perPage,
  goToPage,
} = usePagination<RecentError>(errors, {
  itemsPerPage: 20,
  serverTotalItems: totalErrors,
  onPageChange: async () => { await fetchData() },
})

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
  return resolved ? 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg' : 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
}

function getSeverityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'critical':
      return 'text-autobot-error'
    case 'error':
      return 'text-autobot-warning'
    case 'warning':
      return 'text-autobot-warning'
    default:
      return 'text-autobot-text-secondary'
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
      return 'text-autobot-error'
    case 'decreasing':
      return 'text-autobot-success'
    default:
      return 'text-autobot-text-secondary'
  }
}

const formatTimestamp = createDateFormatter({
  locale: () => String(i18n.global.locale),
  intl: () => ({ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', ...getTimezoneOption() }),
})



async function fetchData(): Promise<boolean> {
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
          per_page: perPage.value,
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
    return true
  } catch (err) {
    logger.error('Failed to fetch error data:', err)
    return false
  } finally {
    isLoading.value = false
  }
}

function selectError(error: RecentError) {
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

// #19482: shared dashboard policy; fetchData() is false on a failed read, which the poller counts
const dataPoller = useDashboardPoller(async () => {
  throwUnlessLoaded(await fetchData())
}, 60000)

onMounted(() => dataPoller.start(''))
</script>

<template>
  <div class="p-6">
    <PollingPausedAlert :poller="dataPoller" :message="$t('common.polling.paused')" :retry-label="$t('common.polling.retry')" class="mb-6" @retry="dataPoller.start('')" />
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-autobot-text-primary">{{ $t('monitoring.errorMonitor.errorMonitoring') }}</h2>
      <div class="flex items-center gap-2">
        <button
          @click="clearOldErrors"
          class="px-3 py-2 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover"
        >
          {{ $t('monitoring.errorMonitor.clearOld') }}
        </button>
        <button
          @click="createTestError"
          class="px-3 py-2 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover"
        >
          {{ $t('monitoring.errorMonitor.testError') }}
        </button>
        <button
          @click="dataPoller.start('')"
          :disabled="isLoading"
          class="px-4 py-2 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover disabled:opacity-50 flex items-center gap-2"
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
          {{ $t('monitoring.errorMonitor.refresh') }}
        </button>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
        <p class="text-sm text-autobot-text-tertiary">{{ $t('monitoring.errorMonitor.totalErrors') }}</p>
        <p class="text-2xl font-bold text-autobot-text-primary">{{ stats.total_errors }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-xs border border-autobot-error-light p-4">
        <p class="text-sm text-autobot-error">{{ $t('monitoring.errorMonitor.last24Hours') }}</p>
        <p class="bg-autobot-pill-bad-bg px-2 rounded-sm w-fit text-2xl font-bold text-autobot-pill-bad-fg">{{ stats.errors_24h }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-xs border border-autobot-warning-light p-4">
        <p class="text-sm text-autobot-warning">{{ $t('monitoring.errorMonitor.unresolved') }}</p>
        <p class="bg-autobot-pill-warn-bg px-2 rounded-sm w-fit text-2xl font-bold text-autobot-pill-warn-fg">
          {{ stats.unresolved_count }}
        </p>
      </div>
      <div class="bg-white rounded-lg shadow-xs border border-autobot-success-light p-4">
        <p class="text-sm text-autobot-success">{{ $t('monitoring.errorMonitor.resolved') }}</p>
        <p class="bg-autobot-pill-ok-bg px-2 rounded-sm w-fit text-2xl font-bold text-autobot-pill-ok-fg">
          {{ stats.resolved_count }}
        </p>
      </div>
      <div class="bg-white rounded-lg shadow-xs border border-autobot-primary-light p-4">
        <p class="text-sm text-autobot-text-link">{{ $t('monitoring.errorMonitor.trend') }}</p>
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
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <div class="flex flex-wrap items-center gap-4">
            <div class="flex-1 min-w-[200px]">
              <input
                v-model="searchQuery"
                type="text"
                :placeholder="$t('monitoring.errorMonitor.searchErrors')"
                class="w-full px-3 py-2 text-sm border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <select
              v-model="filterSeverity"
              @change="onFilterChange"
              class="px-3 py-2 text-sm border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">{{ $t('monitoring.errorMonitor.allSeverities') }}</option>
              <option value="critical">{{ $t('monitoring.errorMonitor.critical') }}</option>
              <option value="error">{{ $t('monitoring.errorMonitor.error') }}</option>
            </select>
            <select
              v-model="filterResolved"
              @change="onFilterChange"
              class="px-3 py-2 text-sm border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">{{ $t('monitoring.errorMonitor.allStatus') }}</option>
              <option value="unresolved">{{ $t('monitoring.errorMonitor.unresolved') }}</option>
              <option value="resolved">{{ $t('monitoring.errorMonitor.resolved') }}</option>
            </select>
          </div>
        </div>

        <!-- Error List -->
        <div
          class="bg-white rounded-lg shadow-xs border border-autobot-border overflow-hidden"
        >
          <div class="max-h-[500px] overflow-y-auto divide-y divide-autobot-border">
            <div
              v-for="error in filteredErrors"
              :key="error.event_id"
              @click="selectError(error)"
              class="p-4 hover:bg-autobot-bg-hover cursor-pointer transition-colors"
            >
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span
                      :class="[
                        'px-2 py-0.5 text-xs font-medium rounded-sm',
                        getStatusClass(error.resolved),
                      ]"
                    >
                      {{ error.resolved ? $t('monitoring.errorMonitor.resolved2') : $t('monitoring.errorMonitor.active') }}
                    </span>
                    <span
                      :class="[
                        'text-xs font-medium',
                        getSeverityColor(error.severity),
                      ]"
                    >
                      {{ error.severity }}
                    </span>
                    <span class="text-xs text-autobot-text-tertiary">{{
                      error.hostname
                    }}</span>
                  </div>
                  <p class="text-sm font-medium text-autobot-text-primary truncate">
                    {{ error.message }}
                  </p>
                  <p class="text-xs text-autobot-text-tertiary mt-1">
                    {{ error.event_type }} ·
                    {{ formatCompactRelativeTime(error.timestamp) }}
                  </p>
                </div>
              </div>
            </div>

            <div
              v-if="filteredErrors.length === 0"
              class="p-8 text-center text-autobot-text-tertiary"
            >
              <svg
                class="w-12 h-12 mx-auto mb-3 text-autobot-text-tertiary"
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
              <p>{{ $t('monitoring.errorMonitor.noErrorsFound') }}</p>
            </div>
          </div>

          <!-- Pagination -->
          <div
            v-if="totalErrors > perPage"
            class="px-4 py-3 border-t border-autobot-border flex items-center justify-between"
          >
            <BasePagination
              class="flex-1"
              :page="currentPage"
              :total-pages="totalPages"
              :labels="{ previous: $t('monitoring.errorMonitor.previous'), next: $t('monitoring.errorMonitor.next') }"
              :label="$t('monitoring.errorMonitor.paginationAria')"
              @update:page="goToPage"
            >
              <template #summary>{{ $t('monitoring.errorMonitor.pageValue0OfValue1', { value0: currentPage, value1: totalPages }) }}</template>
            </BasePagination>
          </div>
        </div>
      </div>

      <!-- Sidebar -->
      <div class="space-y-4">
        <!-- Top Errors -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <h3 class="text-sm font-semibold text-autobot-text-primary mb-3">
            {{ $t('monitoring.errorMonitor.recentUnresolved') }}
          </h3>
          <div class="space-y-3">
            <div
              v-for="error in topErrors"
              :key="error.event_id"
              class="flex items-center justify-between"
            >
              <div class="flex-1 min-w-0">
                <p class="text-sm text-autobot-text-primary truncate">
                  {{ error.message }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ error.hostname }}</p>
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
              class="text-sm text-autobot-text-tertiary text-center py-2"
            >
              {{ $t('monitoring.errorMonitor.noUnresolvedErrors') }}
            </div>
          </div>
        </div>

        <!-- Errors by Category -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <h3 class="text-sm font-semibold text-autobot-text-primary mb-3">{{ $t('monitoring.errorMonitor.byCategory') }}</h3>
          <div class="space-y-2">
            <div
              v-for="cat in categories"
              :key="cat.category"
              class="flex items-center justify-between"
            >
              <span class="text-sm text-autobot-text-secondary">{{ cat.category }}</span>
              <span class="text-sm font-medium text-autobot-text-primary"
                >{{ cat.count }} ({{ cat.percentage }}%)</span
              >
            </div>
            <div
              v-if="categories.length === 0"
              class="text-sm text-autobot-text-tertiary text-center py-2"
            >
              {{ $t('monitoring.errorMonitor.noCategories') }}
            </div>
          </div>
        </div>

        <!-- Errors by Component -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <h3 class="text-sm font-semibold text-autobot-text-primary mb-3">{{ $t('monitoring.errorMonitor.byNode') }}</h3>
          <div class="space-y-2">
            <div
              v-for="comp in components"
              :key="comp.node_id"
              class="flex items-center justify-between"
            >
              <span class="text-sm text-autobot-text-secondary">{{ comp.hostname }}</span>
              <span class="text-sm font-medium text-autobot-text-primary"
                >{{ comp.count }} ({{ comp.percentage }}%)</span
              >
            </div>
            <div
              v-if="components.length === 0"
              class="text-sm text-autobot-text-tertiary text-center py-2"
            >
              {{ $t('monitoring.errorMonitor.noComponents') }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Detail Modal -->
    <BaseModal
      v-if="selectedError"
      :model-value="true"
      :title="$t('monitoring.errorMonitor.errorDetails')"
      width="42rem"
      :close-label="$t('monitoring.errorMonitor.close')"
      @close="closeDetail"
    >
      <div class="space-y-4">
        <div class="flex items-center gap-2">
          <span
            :class="[
              'px-2 py-1 text-xs font-medium rounded-sm',
              getStatusClass(selectedError.resolved),
            ]"
          >
            {{ selectedError.resolved ? $t('monitoring.errorMonitor.resolved2') : $t('monitoring.errorMonitor.active') }}
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
          <label class="text-xs font-medium text-autobot-text-tertiary uppercase"
            >{{ $t('monitoring.errorMonitor.eventID') }}</label
          >
          <p class="text-sm text-autobot-text-primary font-mono">
            {{ selectedError.event_id }}
          </p>
        </div>

        <div>
          <label class="text-xs font-medium text-autobot-text-tertiary uppercase"
            >{{ $t('monitoring.errorMonitor.node') }}</label
          >
          <p class="text-sm text-autobot-text-primary">
            {{ selectedError.hostname }} ({{ selectedError.node_id }})
          </p>
        </div>

        <div>
          <label class="text-xs font-medium text-autobot-text-tertiary uppercase"
            >{{ $t('monitoring.errorMonitor.type') }}</label
          >
          <p class="text-sm text-autobot-text-primary">{{ selectedError.event_type }}</p>
        </div>

        <div>
          <label class="text-xs font-medium text-autobot-text-tertiary uppercase"
            >{{ $t('monitoring.errorMonitor.message') }}</label
          >
          <p class="text-sm text-autobot-text-primary">{{ selectedError.message }}</p>
        </div>

        <div>
          <label class="text-xs font-medium text-autobot-text-tertiary uppercase"
            >{{ $t('monitoring.errorMonitor.timestamp') }}</label
          >
          <p class="text-sm text-autobot-text-primary">
            {{ formatTimestamp(selectedError.timestamp) }}
          </p>
        </div>

        <div v-if="selectedError.resolved">
          <label class="text-xs font-medium text-autobot-text-tertiary uppercase"
            >{{ $t('monitoring.errorMonitor.resolved') }}</label
          >
          <p class="text-sm text-autobot-text-primary">
            {{
              $t('monitoring.errorMonitor.resolvedByAt', {
                by: selectedError.resolved_by,
                at: formatTimestamp(selectedError.resolved_at || ''),
              })
            }}
          </p>
        </div>
      </div>
      <template #actions>
        <button
          v-if="!selectedError.resolved"
          @click="resolveError(selectedError.event_id)"
          class="px-4 py-2 text-sm font-medium text-autobot-text-on-primary bg-autobot-primary rounded-lg hover:bg-autobot-primary-hover"
        >
          {{ $t('monitoring.errorMonitor.markResolved') }}
        </button>
        <button
          @click="closeDetail"
          class="px-4 py-2 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover"
        >
          {{ $t('monitoring.errorMonitor.close') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>
