// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AdminMonitoringView')
/**
 * AdminMonitoringView - Admin Monitoring Dashboard
 *
 * Provides monitoring access to the main AutoBot backend systems.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const autoRefresh = ref(true)
const refreshInterval = 30

interface ErrorStat {
  level: string
  count: number
}

interface SystemHealth {
  status: 'healthy' | 'degraded' | 'critical'
  cpu_percent?: number
  memory_percent?: number
  disk_percent?: number
  uptime_seconds?: number
  services?: { name: string; status: string }[]
}

interface ErrorStats {
  total_errors: number
  last_24h: number
  by_level: ErrorStat[]
  resolved_count: number
}

interface MetricSummary {
  name: string
  value: string | number
  status: 'good' | 'warning' | 'critical'
  trend?: 'up' | 'down' | 'stable'
}

const systemHealth = ref<SystemHealth | null>(null)
const errorStats = ref<ErrorStats | null>(null)
const recentErrors = ref<any[]>([])
const metrics = ref<MetricSummary[]>([])

let refreshTimer: ReturnType<typeof setInterval> | null = null

// Computed
const healthStatus = computed(() => {
  if (!systemHealth.value) return 'unknown'
  return systemHealth.value.status
})

const healthStatusClass = computed(() => {
  switch (healthStatus.value) {
    case 'healthy': return 'bg-green-100 border-green-500'
    case 'degraded': return 'bg-yellow-100 border-yellow-500'
    case 'critical': return 'bg-red-100 border-red-500'
    default: return 'bg-gray-100 border-gray-500'
  }
})

const healthIcon = computed(() => {
  switch (healthStatus.value) {
    case 'healthy': return 'text-green-600'
    case 'degraded': return 'text-yellow-600'
    case 'critical': return 'text-red-600'
    default: return 'text-gray-600'
  }
})

// Methods
function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString()
}

function getErrorLevelClass(level: string): string {
  switch (level.toLowerCase()) {
    case 'error': return 'bg-red-100 text-red-800'
    case 'warning': return 'bg-yellow-100 text-yellow-800'
    case 'info': return 'bg-blue-100 text-blue-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

async function loadSystemHealth(): Promise<void> {
  try {
    const data = await api.getSystemHealth()
    systemHealth.value = data
  } catch (e) {
    logger.error('Failed to load system health:', e)
  }
}

async function loadErrorStats(): Promise<void> {
  try {
    const data = await api.getErrorStatistics()
    errorStats.value = data
  } catch (e) {
    logger.error('Failed to load error stats:', e)
  }
}

async function loadRecentErrors(): Promise<void> {
  try {
    const data = await api.getRecentErrors(10)
    recentErrors.value = data.errors || []
  } catch (e) {
    logger.error('Failed to load recent errors:', e)
  }
}

async function loadMetrics(): Promise<void> {
  try {
    const data = await api.getMetricsSummary()
    metrics.value = data.metrics || []
  } catch (e) {
    logger.error('Failed to load metrics:', e)
  }
}

async function refreshAllData(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    await Promise.all([
      loadSystemHealth(),
      loadErrorStats(),
      loadRecentErrors(),
      loadMetrics()
    ])
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load data'
  } finally {
    loading.value = false
  }
}

function toggleAutoRefresh(): void {
  if (autoRefresh.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

function startAutoRefresh(): void {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = setInterval(() => refreshAllData(), refreshInterval * 1000)
}

function stopAutoRefresh(): void {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  refreshAllData()
  if (autoRefresh.value) {
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
      <div class="flex items-center gap-3">
        <div class="p-2 bg-amber-100 rounded-lg">
          <svg class="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Admin Monitoring</h1>
          <p class="text-sm text-gray-500">AutoBot system health and error tracking</p>
        </div>
      </div>

      <div class="flex items-center gap-4">
        <!-- Auto-refresh toggle -->
        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="autoRefresh" @change="toggleAutoRefresh" class="rounded" />
          <span class="text-gray-600">Auto-refresh ({{ refreshInterval }}s)</span>
        </label>

        <!-- Refresh button -->
        <button
          @click="refreshAllData"
          :disabled="loading"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- Health Status Bar -->
    <div
      v-if="systemHealth"
      :class="['p-4 rounded-lg border-l-4 mb-6', healthStatusClass]"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <svg :class="['w-6 h-6', healthIcon]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path v-if="healthStatus === 'healthy'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            <path v-else-if="healthStatus === 'degraded'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span class="font-medium capitalize">System Status: {{ healthStatus }}</span>
        </div>
        <div class="text-sm text-gray-600">
          Uptime: {{ formatUptime(systemHealth.uptime_seconds ?? 0) }}
        </div>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      {{ error }}
    </div>

    <!-- Stats Grid -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <!-- System Resources -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm text-gray-500">CPU Usage</span>
          <span :class="[
            'text-lg font-bold',
            (systemHealth?.cpu_percent ?? 0) > 80 ? 'text-red-600' :
            (systemHealth?.cpu_percent ?? 0) > 60 ? 'text-yellow-600' : 'text-green-600'
          ]">
            {{ systemHealth?.cpu_percent?.toFixed(1) ?? '0' }}%
          </span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div
            class="h-2 rounded-full transition-all"
            :class="[
              (systemHealth?.cpu_percent ?? 0) > 80 ? 'bg-red-500' :
              (systemHealth?.cpu_percent ?? 0) > 60 ? 'bg-yellow-500' : 'bg-green-500'
            ]"
            :style="{ width: `${systemHealth?.cpu_percent ?? 0}%` }"
          ></div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm text-gray-500">Memory Usage</span>
          <span :class="[
            'text-lg font-bold',
            (systemHealth?.memory_percent ?? 0) > 80 ? 'text-red-600' :
            (systemHealth?.memory_percent ?? 0) > 60 ? 'text-yellow-600' : 'text-green-600'
          ]">
            {{ systemHealth?.memory_percent?.toFixed(1) ?? '0' }}%
          </span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div
            class="h-2 rounded-full transition-all"
            :class="[
              (systemHealth?.memory_percent ?? 0) > 80 ? 'bg-red-500' :
              (systemHealth?.memory_percent ?? 0) > 60 ? 'bg-yellow-500' : 'bg-green-500'
            ]"
            :style="{ width: `${systemHealth?.memory_percent ?? 0}%` }"
          ></div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm text-gray-500">Disk Usage</span>
          <span :class="[
            'text-lg font-bold',
            (systemHealth?.disk_percent ?? 0) > 90 ? 'text-red-600' :
            (systemHealth?.disk_percent ?? 0) > 70 ? 'text-yellow-600' : 'text-green-600'
          ]">
            {{ systemHealth?.disk_percent?.toFixed(1) ?? '0' }}%
          </span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div
            class="h-2 rounded-full transition-all"
            :class="[
              (systemHealth?.disk_percent ?? 0) > 90 ? 'bg-red-500' :
              (systemHealth?.disk_percent ?? 0) > 70 ? 'bg-yellow-500' : 'bg-green-500'
            ]"
            :style="{ width: `${systemHealth?.disk_percent ?? 0}%` }"
          ></div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Total Errors (24h)</p>
            <p class="text-2xl font-bold text-gray-900">{{ errorStats?.last_24h || 0 }}</p>
          </div>
          <div class="p-3 bg-red-100 rounded-lg">
            <svg class="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Recent Errors -->
      <div class="lg:col-span-2 bg-white rounded-lg shadow-sm border border-gray-200">
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Recent Errors
          </h2>
        </div>
        <div class="p-6">
          <div v-if="recentErrors.length === 0" class="text-center py-8 text-gray-500">
            <svg class="w-12 h-12 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            No recent errors
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="err in recentErrors"
              :key="err.id"
              class="p-4 bg-gray-50 rounded-lg border border-gray-200"
            >
              <div class="flex items-start justify-between">
                <div class="flex-1">
                  <div class="flex items-center gap-2 mb-1">
                    <span :class="['px-2 py-0.5 text-xs font-medium rounded', getErrorLevelClass(err.level)]">
                      {{ err.level }}
                    </span>
                    <span class="text-xs text-gray-500">{{ err.component }}</span>
                  </div>
                  <p class="text-sm text-gray-900 font-medium">{{ err.message }}</p>
                  <p class="text-xs text-gray-500 mt-1">{{ formatDate(err.timestamp) }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Error Stats & Services -->
      <div class="space-y-6">
        <!-- Error Breakdown -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200">
          <div class="px-6 py-4 border-b border-gray-200">
            <h2 class="text-lg font-semibold text-gray-900">Error Breakdown</h2>
          </div>
          <div class="p-6">
            <div v-if="errorStats?.by_level?.length" class="space-y-3">
              <div
                v-for="stat in errorStats.by_level"
                :key="stat.level"
                class="flex items-center justify-between"
              >
                <span :class="['px-2 py-1 text-xs font-medium rounded', getErrorLevelClass(stat.level)]">
                  {{ stat.level }}
                </span>
                <span class="font-bold text-gray-900">{{ stat.count }}</span>
              </div>
            </div>
            <div v-else class="text-center py-4 text-gray-500 text-sm">
              No error data available
            </div>
          </div>
        </div>

        <!-- Services Status -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200">
          <div class="px-6 py-4 border-b border-gray-200">
            <h2 class="text-lg font-semibold text-gray-900">Services</h2>
          </div>
          <div class="p-6">
            <div v-if="systemHealth?.services?.length" class="space-y-2">
              <div
                v-for="service in systemHealth.services"
                :key="service.name"
                class="flex items-center justify-between py-2"
              >
                <span class="text-sm text-gray-700">{{ service.name }}</span>
                <span :class="[
                  'px-2 py-0.5 text-xs font-medium rounded-full',
                  service.status === 'running' ? 'bg-green-100 text-green-800' :
                  service.status === 'stopped' ? 'bg-red-100 text-red-800' :
                  'bg-yellow-100 text-yellow-800'
                ]">
                  {{ service.status }}
                </span>
              </div>
            </div>
            <div v-else class="text-center py-4 text-gray-500 text-sm">
              No service data available
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
