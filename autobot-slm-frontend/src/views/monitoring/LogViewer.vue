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
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LogViewer')

interface LogEntry {
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  source: string
  message: string
  event_id?: string
  node_id?: string
}

const { getMonitoringLogs } = useSlmApi()

// State
const logs = ref<LogEntry[]>([])
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
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDate(ts: string): string {
  const date = new Date(ts)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

const severityToLevel: Record<string, LogEntry['level']> = {
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

onMounted(() => {
  fetchLogs()
  if (isAutoRefresh.value) {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-gray-900">Log Viewer</h2>
      <div class="flex items-center gap-2">
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
          {{ isAutoRefresh ? 'Live' : 'Paused' }}
        </button>
        <button
          @click="fetchLogs"
          :disabled="isLoading"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          Refresh
        </button>
        <button
          @click="clearLogs"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Clear
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
      <div class="flex flex-wrap items-center gap-4">
        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search logs..."
            class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        <!-- Level Filter -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600">Level:</label>
          <select
            v-model="selectedLevel"
            class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option v-for="level in logLevels" :key="level" :value="level">
              {{ level === 'all' ? 'All Levels' : level.charAt(0).toUpperCase() + level.slice(1) }}
            </option>
          </select>
        </div>

        <!-- Source Filter -->
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600">Source:</label>
          <select
            v-model="selectedSource"
            class="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option v-for="source in logSources" :key="source" :value="source">
              {{ source === 'all' ? 'All Sources' : source }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- Log Count -->
    <div class="text-sm text-gray-500 mb-2">
      Showing {{ filteredLogs.length }} of {{ logs.length }} entries
    </div>

    <!-- Log Table -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto max-h-[600px] overflow-y-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50 sticky top-0">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                Time
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-20">
                Level
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                Source
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Message
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
                <span :class="['px-2 py-0.5 text-xs rounded', getLevelClass(log.level)]">
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
                {{ isLoading ? 'Loading logs...' : 'No logs found' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
