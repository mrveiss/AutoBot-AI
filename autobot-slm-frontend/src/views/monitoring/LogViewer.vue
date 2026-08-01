<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LogViewer - Centralized log viewing and filtering
 *
 * Displays logs from all services with real-time updates and filtering.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSlmApi } from '@/composables/useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import { getTimezone } from '@/composables/useTimezone'
import type { AppLogEntry } from '@/types/api-responses'

const logger = createLogger('LogViewer')
const { t } = useI18n()

/**
 * Row rendered by this viewer — a client-side VIEW-MODEL, not a wire shape.
 *
 * Renamed from `LogEntry` in #13138: it collided with the generated
 * `components['schemas']['LogEntry']` (api/monitoring.py:128) while
 * deliberately remapping it — `severityToLevel` below turns `severity` into
 * `level` and `hostname`/`event_type` into `source`. Deriving it would have
 * replaced a working local shape with an unrelated wire shape.
 */
interface LogRow {
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  source: string
  message: string
  event_id?: string
  node_id?: string
}

const { getMonitoringLogs, getAppLogs } = useSlmApi()
const fleetStore = useFleetStore()

// Sub-tab: fleet events (existing NodeEvent-backed view) vs application logs (#11302)
type LogSubTab = 'fleetEvents' | 'appLogs'
const activeSubTab = ref<LogSubTab>('fleetEvents')

// State
const logs = ref<LogRow[]>([])
const isLoading = ref(false)
const isAutoRefresh = ref(true)
const searchQuery = ref('')
const selectedLevel = ref<string>('all')
const selectedSource = ref<string>('all')

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Available log levels and sources
const logLevels = ['all', 'debug', 'info', 'warning', 'error', 'critical']
const logSources = computed(() => {
  const sources = new Set(logs.value.map(l => l.source))
  return ['all', ...Array.from(sources).sort()]
})

// Filtered logs
const filteredLogs = computed(() => {
  return logs.value.filter(log => {
    // Level filter
    if (selectedLevel.value !== 'all' && log.level !== selectedLevel.value) {
      return false
    }
    // Source filter
    if (selectedSource.value !== 'all' && log.source !== selectedSource.value) {
      return false
    }
    // Search filter
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      return (
        log.message.toLowerCase().includes(query) ||
        log.source.toLowerCase().includes(query)
      )
    }
    return true
  })
})

// Log level styling
function getLevelClass(level: string): string {
  switch (level) {
    case 'debug': return 'bg-gray-100 text-gray-600'
    case 'info': return 'bg-blue-100 text-blue-700'
    case 'warning': return 'bg-yellow-100 text-yellow-700'
    case 'error': return 'bg-red-100 text-red-700'
    case 'critical': return 'bg-red-200 text-red-800 font-semibold'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts)
  const tz = getTimezone()
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    ...(tz ? { timeZone: tz } : {}),
  })
}

function formatDate(ts: string): string {
  const date = new Date(ts)
  const tz = getTimezone()
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(tz ? { timeZone: tz } : {}),
  })
}

const severityToLevel: Record<string, LogRow['level']> = {
  debug: 'debug',
  info: 'info',
  warning: 'warning',
  error: 'error',
  critical: 'critical',
}

async function fetchLogs() {
  isLoading.value = true
  try {
    const data = await getMonitoringLogs({ per_page: 200 })
    logs.value = (data.logs ?? []).map(entry => ({
      timestamp: entry.timestamp,
      level: severityToLevel[entry.severity] ?? 'info',
      source: entry.hostname || entry.event_type,
      message: entry.message,
      event_id: entry.event_id,
      node_id: entry.node_id,
    }))
  } catch (err) {
    logger.error('Failed to fetch logs:', err)
    logs.value = []
  } finally {
    isLoading.value = false
  }
}

function clearLogs() {
  logs.value = []
}

function toggleAutoRefresh() {
  isAutoRefresh.value = !isAutoRefresh.value
  if (isAutoRefresh.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

function startAutoRefresh() {
  if (refreshInterval) return
  refreshInterval = setInterval(fetchLogs, 5000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

// =============================================================================
// Application logs (Issue #11302) — tails allowlisted on-node log files via
// GET /monitoring/app-logs, separate from the NodeEvent-backed fleet view above.
// =============================================================================

const appLogServices = ['backend', 'celery', 'celery-beat', 'mcp-bridge', 'chromadb'] as const
const appLogSeverities = ['error', 'warning', 'info', 'debug'] as const

const appLogNodeId = ref('')
const appLogService = ref<(typeof appLogServices)[number]>('backend')
const appLogSeverity = ref('')
const appLogHours = ref(1)
const appLogQuery = ref('')
const appLogMcpInstance = ref('')
const appLogPage = ref(1)
const appLogPerPage = 100

const appLogEntries = ref<AppLogEntry[]>([])
const appLogTotal = ref(0)
const isAppLogLoading = ref(false)
const appLogError = ref<string | null>(null)

const appLogTotalPages = computed(() => Math.max(1, Math.ceil(appLogTotal.value / appLogPerPage)))

function severityLabel(severity: string): string {
  const key = `monitoring.logViewer.appLogs.severity${severity.charAt(0).toUpperCase()}${severity.slice(1)}`
  return t(key)
}

async function fetchAppLogs() {
  if (!appLogNodeId.value) {
    appLogEntries.value = []
    appLogTotal.value = 0
    return
  }
  isAppLogLoading.value = true
  appLogError.value = null
  try {
    const data = await getAppLogs({
      node_id: appLogNodeId.value,
      service: appLogService.value,
      severity: appLogSeverity.value || undefined,
      hours: appLogHours.value,
      q: appLogQuery.value || undefined,
      page: appLogPage.value,
      per_page: appLogPerPage,
      mcp_instance: appLogService.value === 'mcp-bridge' ? appLogMcpInstance.value || undefined : undefined,
    })
    appLogEntries.value = data.entries
    appLogTotal.value = data.total
  } catch (err) {
    logger.error('Failed to fetch application logs:', err)
    appLogEntries.value = []
    appLogTotal.value = 0
    appLogError.value = err instanceof Error ? err.message : String(err)
  } finally {
    isAppLogLoading.value = false
  }
}

function applyAppLogFilters() {
  appLogPage.value = 1
  fetchAppLogs()
}

function goToAppLogPage(delta: number) {
  const next = appLogPage.value + delta
  if (next < 1 || next > appLogTotalPages.value) return
  appLogPage.value = next
  fetchAppLogs()
}

function switchSubTab(tab: LogSubTab) {
  activeSubTab.value = tab
  if (tab === 'appLogs' && appLogNodeId.value && appLogEntries.value.length === 0) {
    fetchAppLogs()
  }
}

onMounted(() => {
  fetchLogs()
  if (isAutoRefresh.value) {
    startAutoRefresh()
  }
  fleetStore.fetchNodes()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-gray-900">{{ $t('monitoring.logViewer.logViewer') }}</h2>
      <div v-if="activeSubTab === 'fleetEvents'" class="flex items-center gap-2">
        <button
          @click="toggleAutoRefresh"
          :class="[
            'px-3 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2',
            isAutoRefresh
              ? 'bg-success-100 text-success-700'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          ]"
        >
          <span :class="['w-2 h-2 rounded-full', isAutoRefresh ? 'bg-success-500 animate-pulse' : 'bg-gray-400']"></span>
          {{ isAutoRefresh ? $t('monitoring.logViewer.live') : $t('monitoring.logViewer.paused') }}
        </button>
        <button
          @click="fetchLogs"
          :disabled="isLoading"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          {{ $t('monitoring.logViewer.refresh') }}
        </button>
        <button
          @click="clearLogs"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          {{ $t('monitoring.logViewer.clear') }}
        </button>
      </div>
      <button
        v-else
        @click="fetchAppLogs"
        :disabled="isAppLogLoading || !appLogNodeId"
        class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
      >
        {{ $t('monitoring.logViewer.appLogs.refresh') }}
      </button>
    </div>

    <!-- Sub-tabs: fleet events (NodeEvent-backed) vs application logs (#11302) -->
    <div class="flex gap-1 mb-4 border-b border-gray-200" role="tablist">
      <button
        role="tab"
        :aria-selected="activeSubTab === 'fleetEvents'"
        @click="switchSubTab('fleetEvents')"
        :class="[
          'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
          activeSubTab === 'fleetEvents'
            ? 'border-primary-500 text-primary-600'
            : 'border-transparent text-gray-500 hover:text-gray-700'
        ]"
      >
        {{ $t('monitoring.logViewer.appLogs.fleetEvents') }}
      </button>
      <button
        role="tab"
        :aria-selected="activeSubTab === 'appLogs'"
        @click="switchSubTab('appLogs')"
        :class="[
          'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
          activeSubTab === 'appLogs'
            ? 'border-primary-500 text-primary-600'
            : 'border-transparent text-gray-500 hover:text-gray-700'
        ]"
      >
        {{ $t('monitoring.logViewer.appLogs.applicationLogs') }}
      </button>
    </div>

    <template v-if="activeSubTab === 'fleetEvents'">
    <!-- Filters -->
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4 mb-4">
      <div class="flex flex-wrap items-center gap-4">
        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="$t('monitoring.logViewer.searchLogs')"
            class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Level Filter -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.level') }}</label>
          <select
            v-model="selectedLevel"
            class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option v-for="level in logLevels" :key="level" :value="level">
              {{ level === 'all' ? $t('monitoring.logViewer.allLevels') : level.charAt(0).toUpperCase() + level.slice(1) }}
            </option>
          </select>
        </div>

        <!-- Source Filter -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.source') }}</label>
          <select
            v-model="selectedSource"
            class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option v-for="source in logSources" :key="source" :value="source">
              {{ source === 'all' ? $t('monitoring.logViewer.allSources') : source }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- Log Count -->
    <div class="text-sm text-gray-500 mb-2">{{ $t('monitoring.logViewer.showingCountOfCount2Entries', { count: filteredLogs.length, count2: logs.length }) }}</div>

    <!-- Log Table -->
    <div class="bg-white rounded-lg shadow-xs border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto max-h-[600px] overflow-y-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50 sticky top-0">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                {{ $t('monitoring.logViewer.time') }}
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-20">
                {{ $t('monitoring.logViewer.level1') }}
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                {{ $t('monitoring.logViewer.source1') }}
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {{ $t('monitoring.logViewer.message') }}
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr
              v-for="(log, index) in filteredLogs"
              :key="index"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                <div>{{ formatTimestamp(log.timestamp) }}</div>
                <div class="text-gray-400">{{ formatDate(log.timestamp) }}</div>
              </td>
              <td class="px-4 py-2 whitespace-nowrap">
                <span :class="['px-2 py-0.5 text-xs rounded-sm', getLevelClass(log.level)]">
                  {{ log.level.toUpperCase() }}
                </span>
              </td>
              <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-600">
                {{ log.source }}
              </td>
              <td class="px-4 py-2 text-sm text-gray-900 font-mono">
                {{ log.message }}
              </td>
            </tr>
            <tr v-if="filteredLogs.length === 0">
              <td colspan="4" class="px-4 py-8 text-center text-gray-500">
                {{ isLoading ? $t('monitoring.logViewer.loadingLogs') : $t('monitoring.logViewer.noLogsFound') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    </template>

    <!-- Application logs (Issue #11302) -->
    <template v-else>
      <!-- Filters -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4 mb-4">
        <div class="flex flex-wrap items-end gap-4">
          <div class="flex flex-col gap-1">
            <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.appLogs.node') }}</label>
            <select
              v-model="appLogNodeId"
              @change="applyAppLogFilters"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 min-w-[180px]"
            >
              <option value="">{{ $t('monitoring.logViewer.appLogs.selectNode') }}</option>
              <option v-for="node in fleetStore.nodeList" :key="node.node_id" :value="node.node_id">
                {{ node.hostname }}
              </option>
            </select>
          </div>

          <div class="flex flex-col gap-1">
            <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.appLogs.service') }}</label>
            <select
              v-model="appLogService"
              @change="applyAppLogFilters"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option v-for="svc in appLogServices" :key="svc" :value="svc">{{ svc }}</option>
            </select>
          </div>

          <div v-if="appLogService === 'mcp-bridge'" class="flex flex-col gap-1">
            <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.appLogs.mcpInstance') }}</label>
            <input
              v-model="appLogMcpInstance"
              type="text"
              :placeholder="$t('monitoring.logViewer.appLogs.mcpInstancePlaceholder')"
              @change="applyAppLogFilters"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 w-32"
            />
          </div>

          <div class="flex flex-col gap-1">
            <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.appLogs.severity') }}</label>
            <select
              v-model="appLogSeverity"
              @change="applyAppLogFilters"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="">{{ $t('monitoring.logViewer.appLogs.allSeverities') }}</option>
              <option v-for="sev in appLogSeverities" :key="sev" :value="sev">{{ severityLabel(sev) }}</option>
            </select>
          </div>

          <div class="flex flex-col gap-1">
            <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.appLogs.hours') }}</label>
            <input
              v-model.number="appLogHours"
              type="number"
              min="1"
              max="168"
              @change="applyAppLogFilters"
              class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 w-24"
            />
          </div>

          <div class="flex-1 min-w-[200px] flex flex-col gap-1">
            <label class="text-sm text-gray-600">{{ $t('monitoring.logViewer.appLogs.search') }}</label>
            <input
              v-model="appLogQuery"
              type="text"
              :placeholder="$t('monitoring.logViewer.appLogs.search')"
              @keyup.enter="applyAppLogFilters"
              @blur="applyAppLogFilters"
              class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
        </div>
      </div>

      <!-- Error banner -->
      <div
        v-if="appLogError"
        role="alert"
        class="bg-danger-50 text-danger-700 border border-danger-200 rounded-lg px-4 py-2 mb-4 text-sm"
      >
        {{ $t('monitoring.logViewer.appLogs.fetchError', { error: appLogError }) }}
      </div>

      <!-- Log Count + Pagination -->
      <div class="flex items-center justify-between mb-2">
        <div class="text-sm text-gray-500">
          {{ $t('monitoring.logViewer.appLogs.showingCountOfTotalEntries', { count: appLogEntries.length, total: appLogTotal }) }}
        </div>
        <div v-if="appLogNodeId" class="flex items-center gap-2">
          <button
            @click="goToAppLogPage(-1)"
            :disabled="appLogPage <= 1"
            class="px-3 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {{ $t('monitoring.logViewer.appLogs.previous') }}
          </button>
          <span class="text-sm text-gray-500">
            {{ $t('monitoring.logViewer.appLogs.pageOfTotal', { page: appLogPage, totalPages: appLogTotalPages }) }}
          </span>
          <button
            @click="goToAppLogPage(1)"
            :disabled="appLogPage >= appLogTotalPages"
            class="px-3 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {{ $t('monitoring.logViewer.appLogs.next') }}
          </button>
        </div>
      </div>

      <!-- Application Log Table -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto max-h-[600px] overflow-y-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50 sticky top-0">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                  {{ $t('monitoring.logViewer.appLogs.time') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-20">
                  {{ $t('monitoring.logViewer.appLogs.severity') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  {{ $t('monitoring.logViewer.appLogs.message') }}
                </th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="entry in appLogEntries" :key="entry.line_number" class="hover:bg-gray-50">
                <td class="px-4 py-2 whitespace-nowrap text-xs text-gray-500">
                  {{ entry.timestamp ? formatTimestamp(entry.timestamp) : '—' }}
                </td>
                <td class="px-4 py-2 whitespace-nowrap">
                  <span
                    v-if="entry.severity"
                    :class="['px-2 py-0.5 text-xs rounded-sm', getLevelClass((entry.severity || '').toLowerCase())]"
                  >
                    {{ entry.severity }}
                  </span>
                </td>
                <td class="px-4 py-2 text-sm text-gray-900 font-mono">
                  {{ entry.message }}
                </td>
              </tr>
              <tr v-if="appLogEntries.length === 0">
                <td colspan="3" class="px-4 py-8 text-center text-gray-500">
                  {{
                    isAppLogLoading
                      ? $t('monitoring.logViewer.appLogs.loadingLogs')
                      : !appLogNodeId
                        ? $t('monitoring.logViewer.appLogs.selectNode')
                        : $t('monitoring.logViewer.appLogs.noLogsFound')
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
