<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * MetricsDetailsView - Comprehensive metrics dashboard
 * Issue #896 - SLM Metrics Dashboard
 */

import { onMounted, onUnmounted, ref, computed } from 'vue'
import { usePrometheusMetrics } from '@/composables/usePrometheusMetrics'
import FleetMetricsCard from '@/components/monitoring/FleetMetricsCard.vue'
import NodeMetricsGrid from '@/components/monitoring/NodeMetricsGrid.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('MetricsDetailsView')

const {
  fleetMetrics,
  performanceOverview,
  npuFleetMetrics,
  prometheusExport,
  isLoading,
  error,
  lastUpdate,
  refreshMetrics,
  fetchFleetMetrics,
  fetchPerformanceOverview,
  fetchNPUFleetMetrics,
  fetchPrometheusExport,
} = usePrometheusMetrics({ autoFetch: false })

const showNPUMetrics = ref(false)
let refreshInterval: ReturnType<typeof setInterval> | null = null

const hasNPUNodes = computed(() => {
  return npuFleetMetrics.value && npuFleetMetrics.value.total_npu_nodes > 0
})

async function loadMetrics() {
  await refreshMetrics()
  // Check if NPU nodes exist
  if (npuFleetMetrics.value && npuFleetMetrics.value.total_npu_nodes > 0) {
    showNPUMetrics.value = true
  }
}

async function downloadPrometheusMetrics() {
  await fetchPrometheusExport()
  if (prometheusExport.value) {
    const blob = new Blob([prometheusExport.value], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `prometheus-metrics-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }
}

function handleNodeSelect(nodeId: string) {
  // Navigate to node details or show modal
  logger.debug('Selected node:', nodeId)
  // TODO: Implement node detail view
}

onMounted(async () => {
  await loadMetrics()
  // Auto-refresh every 30 seconds
  refreshInterval = setInterval(loadMetrics, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Metrics Details</h2>
        <p class="text-sm text-gray-500 mt-1">
          Real-time fleet and performance metrics
          <span v-if="lastUpdate" class="ml-2">
            • Last updated: {{ lastUpdate.toLocaleTimeString() }}
          </span>
        </p>
      </div>
      <div class="flex gap-2">
        <button
          @click="loadMetrics"
          :disabled="isLoading"
          class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', { 'animate-spin': isLoading }]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
        <button
          @click="downloadPrometheusMetrics"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export Prometheus
        </button>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="bg-danger-50 border border-danger-200 rounded-lg p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-danger-600 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <h3 class="text-sm font-medium text-danger-800">Error Loading Metrics</h3>
          <p class="text-sm text-danger-700 mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Fleet Metrics Card -->
    <FleetMetricsCard :metrics="fleetMetrics" :loading="isLoading" />

    <!-- Node Metrics Grid -->
    <NodeMetricsGrid
      :nodes="fleetMetrics?.nodes || []"
      :loading="isLoading"
      @select-node="handleNodeSelect"
    />

    <!-- Performance Metrics Panel -->
    <div v-if="performanceOverview" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 class="text-lg font-semibold text-gray-900 mb-4">Performance Metrics</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Avg Response Time</div>
          <div class="text-3xl font-bold text-gray-900">
            {{ performanceOverview.avg_response_time_ms.toFixed(0) }}ms
          </div>
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">P95 Response Time</div>
          <div class="text-3xl font-bold text-gray-900">
            {{ performanceOverview.p95_response_time_ms.toFixed(0) }}ms
          </div>
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Request Rate</div>
          <div class="text-3xl font-bold text-gray-900">
            {{ performanceOverview.request_rate.toFixed(1) }}/s
          </div>
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Error Rate</div>
          <div
            :class="[
              'text-3xl font-bold',
              performanceOverview.error_rate > 5 ? 'text-danger-600' :
              performanceOverview.error_rate > 1 ? 'text-warning-600' : 'text-success-600'
            ]"
          >
            {{ performanceOverview.error_rate.toFixed(2) }}%
          </div>
        </div>
      </div>
    </div>

    <!-- NPU Metrics Panel (conditional) -->
    <div v-if="showNPUMetrics && npuFleetMetrics" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 class="text-lg font-semibold text-gray-900 mb-4">NPU Fleet Metrics</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">NPU Nodes</div>
          <div class="text-3xl font-bold text-gray-900">
            {{ npuFleetMetrics.online_npu_nodes }}/{{ npuFleetMetrics.total_npu_nodes }}
          </div>
          <div class="text-xs text-gray-600">Online</div>
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Active Workers</div>
          <div class="text-3xl font-bold text-gray-900">
            {{ npuFleetMetrics.active_workers }}/{{ npuFleetMetrics.total_workers }}
          </div>
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Avg Utilization</div>
          <div class="text-3xl font-bold text-primary-600">
            {{ npuFleetMetrics.avg_utilization_percent.toFixed(1) }}%
          </div>
        </div>
        <div class="space-y-2">
          <div class="text-sm font-medium text-gray-500">Total Inferences</div>
          <div class="text-3xl font-bold text-gray-900">
            {{ npuFleetMetrics.total_inferences.toLocaleString() }}
          </div>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && !fleetMetrics" class="flex items-center justify-center py-12">
      <div class="text-center">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
        <p class="text-gray-500 mt-4">Loading metrics...</p>
      </div>
    </div>
  </div>
</template>
