// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUWorkerMonitor - Real-time NPU worker monitoring dashboard
 *
 * Self-contained component that auto-refreshes every 5 seconds,
 * showing a grid of NPU worker cards with live status indicators,
 * utilization bars, queue depth, and fleet-level summary stats.
 *
 * Related to Issue #590 (NPU Dashboard Improvements).
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import type { SLMNode, NPUWorkerMetrics } from '@/types/slm'
import { useFleetStore } from '@/stores/fleet'

const logger = createLogger('NPUWorkerMonitor')

const emit = defineEmits<{
  'select-node': [node: SLMNode]
}>()

const REFRESH_INTERVAL_MS = 5000

const fleetStore = useFleetStore()
const metricsMap = ref<Map<string, NPUWorkerMetrics>>(new Map())
const loading = ref(false)
const error = ref<string | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | null = null

// -- Computed helpers --

const npuNodes = computed(() => fleetStore.npuNodes)

const onlineCount = computed(() => {
  return npuNodes.value.filter(
    n => n.status === 'online' || n.status === 'healthy'
  ).length
})

const avgUtilization = computed(() => {
  const metrics = Array.from(metricsMap.value.values())
  if (metrics.length === 0) return 0
  const total = metrics.reduce((sum, m) => sum + m.utilization, 0)
  return Math.round(total / metrics.length)
})

function nodeMetrics(nodeId: string): NPUWorkerMetrics | undefined {
  return metricsMap.value.get(nodeId)
}

function nodeStatusIndicator(node: SLMNode): string {
  switch (node.status) {
    case 'online':
    case 'healthy':
      return 'bg-green-500'
    case 'degraded':
      return 'bg-yellow-500'
    default:
      return 'bg-red-500'
  }
}

function nodeStatusLabel(node: SLMNode): string {
  switch (node.status) {
    case 'online':
    case 'healthy':
      return 'Online'
    case 'degraded':
      return 'Degraded'
    case 'offline':
      return 'Offline'
    case 'error':
    case 'unhealthy':
      return 'Error'
    default:
      return node.status
  }
}

function utilizationBarColor(utilization: number): string {
  if (utilization >= 80) return 'bg-red-500'
  if (utilization >= 60) return 'bg-yellow-500'
  return 'bg-green-500'
}

function deviceTypeLabel(nodeId: string): string {
  const status = fleetStore.getNpuStatus(nodeId)
  if (!status?.capabilities?.deviceType) return 'Unknown'
  switch (status.capabilities.deviceType) {
    case 'intel-npu':
      return 'Intel NPU'
    case 'nvidia-gpu':
      return 'NVIDIA GPU'
    case 'amd-gpu':
      return 'AMD GPU'
    default:
      return status.capabilities.deviceType
  }
}

function currentTask(nodeId: string): string {
  const status = fleetStore.getNpuStatus(nodeId)
  if (!status?.loadedModels?.length) return 'Idle'
  return status.loadedModels[0]
}

function connectionStatus(node: SLMNode): string {
  if (node.status === 'online' || node.status === 'healthy') return 'Connected'
  if (node.status === 'degraded') return 'Unstable'
  return 'Disconnected'
}

function connectionColor(node: SLMNode): string {
  if (node.status === 'online' || node.status === 'healthy') {
    return 'text-green-600'
  }
  if (node.status === 'degraded') return 'text-yellow-600'
  return 'text-red-600'
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return 'Never'
  return new Date(ts).toLocaleTimeString()
}

// -- Data fetching --

async function fetchMetrics(): Promise<void> {
  try {
    const fleetMetrics = await fleetStore.fetchNpuFleetMetrics()
    if (fleetMetrics?.node_metrics) {
      const newMap = new Map<string, NPUWorkerMetrics>()
      for (const m of fleetMetrics.node_metrics) {
        newMap.set(m.node_id, m)
      }
      metricsMap.value = newMap
    }
  } catch (e) {
    logger.error('Failed to fetch NPU fleet metrics', e)
    error.value = e instanceof Error ? e.message : 'Failed to fetch NPU metrics'
  }
}

async function refresh(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await fleetStore.fetchNodes()
    await fleetStore.fetchNpuNodes()
    await fetchMetrics()
  } catch (e) {
    logger.error('Refresh failed', e)
    error.value = e instanceof Error ? e.message : 'Refresh failed'
  } finally {
    loading.value = false
  }
}

function startAutoRefresh(): void {
  stopAutoRefresh()
  refreshTimer = setInterval(() => { fetchMetrics() }, REFRESH_INTERVAL_MS)
}

function stopAutoRefresh(): void {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(async () => {
  await refresh()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div>
    <!-- Fleet Summary Bar -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-6">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            <span class="text-sm font-medium text-gray-700">
              <span class="text-green-600 font-semibold">{{ onlineCount }}</span>
              <span class="text-gray-400"> / </span>
              <span class="font-semibold">{{ npuNodes.length }}</span>
              <span class="text-gray-500 ml-1">online</span>
            </span>
          </div>
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span class="text-sm text-gray-700">Avg utilization: <span class="font-semibold">{{ avgUtilization }}%</span></span>
            <div class="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div :class="['h-full transition-all', utilizationBarColor(avgUtilization)]" :style="{ width: `${avgUtilization}%` }" />
            </div>
          </div>
        </div>
        <button @click="refresh" :disabled="loading" class="p-2 text-gray-400 hover:text-gray-600 transition-colors" title="Refresh now">
          <svg :class="['w-5 h-5', loading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{{ error }}</div>

    <!-- Empty State -->
    <div v-if="npuNodes.length === 0 && !loading" class="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
      <svg class="mx-auto w-12 h-12 text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-1">No NPU Workers</h3>
      <p class="text-sm text-gray-500">No nodes with the npu-worker role are registered in the fleet.</p>
    </div>

    <!-- Worker Cards Grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="node in npuNodes"
        :key="node.node_id"
        @click="emit('select-node', node)"
        class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 cursor-pointer hover:shadow-md hover:border-primary-300 transition-all"
      >
        <!-- Header: hostname, IP, status dot -->
        <div class="flex items-start justify-between mb-3">
          <div class="min-w-0">
            <h3 class="font-medium text-gray-900 truncate">{{ node.hostname }}</h3>
            <p class="text-xs text-gray-500">{{ node.ip_address }}</p>
          </div>
          <div class="flex items-center gap-1.5 shrink-0 ml-2">
            <span :class="['w-2.5 h-2.5 rounded-full', nodeStatusIndicator(node)]" />
            <span class="text-xs text-gray-500">{{ nodeStatusLabel(node) }}</span>
          </div>
        </div>

        <!-- Device Type Badge -->
        <div class="mb-3">
          <span class="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">{{ deviceTypeLabel(node.node_id) }}</span>
        </div>

        <!-- Utilization Bar -->
        <div class="mb-3">
          <div class="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span>Utilization</span>
            <span>{{ nodeMetrics(node.node_id)?.utilization ?? 0 }}%</span>
          </div>
          <div class="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              :class="['h-full transition-all', utilizationBarColor(nodeMetrics(node.node_id)?.utilization ?? 0)]"
              :style="{ width: `${nodeMetrics(node.node_id)?.utilization ?? 0}%` }"
            />
          </div>
        </div>

        <!-- Queue Depth + Current Task -->
        <div class="grid grid-cols-2 gap-2 mb-3">
          <div class="bg-gray-50 rounded p-2">
            <p class="text-xs text-gray-500">Queue Depth</p>
            <p class="text-sm font-semibold text-gray-900">{{ nodeMetrics(node.node_id)?.queue_depth ?? 0 }}</p>
          </div>
          <div class="bg-gray-50 rounded p-2">
            <p class="text-xs text-gray-500">Current Task</p>
            <p class="text-sm font-semibold text-gray-900 truncate" :title="currentTask(node.node_id)">{{ currentTask(node.node_id) }}</p>
          </div>
        </div>

        <!-- Footer: connection status + last health check -->
        <div class="flex items-center justify-between text-xs border-t border-gray-100 pt-2">
          <div class="flex items-center gap-1">
            <svg :class="['w-3.5 h-3.5', connectionColor(node)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.858 15.355-5.858 21.213 0" />
            </svg>
            <span :class="connectionColor(node)">{{ connectionStatus(node) }}</span>
          </div>
          <span class="text-gray-400" :title="nodeMetrics(node.node_id)?.timestamp ?? ''">{{ formatTimestamp(nodeMetrics(node.node_id)?.timestamp) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
