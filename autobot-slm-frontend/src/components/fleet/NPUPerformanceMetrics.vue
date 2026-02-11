<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NPUPerformanceMetrics - Fleet-wide NPU performance dashboard
 *
 * Displays aggregate performance stats and per-node detailed metrics
 * for all NPU workers. Auto-refreshes every 5 seconds.
 *
 * Issue #590 - NPU Dashboard Improvements.
 */

import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { NPUFleetMetrics, NPUWorkerMetrics } from '@/types/slm'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('NPUPerformanceMetrics')
const fleetStore = useFleetStore()

const isLoading = ref(true)
const expandedNodes = ref<Set<string>>(new Set())
let refreshTimer: ReturnType<typeof setInterval> | null = null

const REFRESH_INTERVAL_MS = 5000

// -- Computed --

const metrics = computed<NPUFleetMetrics | null>(
  () => fleetStore.npuFleetMetrics
)

const nodeMetrics = computed<NPUWorkerMetrics[]>(
  () => metrics.value?.node_metrics ?? []
)

// -- Helpers --

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hrs = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hrs}h`
  if (hrs > 0) return `${hrs}h ${mins}m`
  return `${mins}m`
}

function utilizationBarColor(pct: number): string {
  if (pct > 80) return 'bg-red-500'
  if (pct >= 60) return 'bg-yellow-500'
  return 'bg-green-500'
}

function utilizationTextColor(pct: number): string {
  if (pct > 80) return 'text-red-600'
  if (pct >= 60) return 'text-yellow-600'
  return 'text-green-600'
}

function temperatureColor(temp: number | null): string {
  if (temp === null) return 'text-gray-400'
  if (temp > 75) return 'text-red-600'
  if (temp >= 60) return 'text-yellow-600'
  return 'text-green-600'
}

function temperatureDisplay(temp: number | null): string {
  if (temp === null) return 'N/A'
  return `${temp.toFixed(1)}\u00B0C`
}

function memoryPercent(used: number, total: number): number {
  if (total <= 0) return 0
  return Math.min(100, (used / total) * 100)
}

function toggleNode(nodeId: string): void {
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId)
  } else {
    expandedNodes.value.add(nodeId)
  }
}

function isExpanded(nodeId: string): boolean {
  return expandedNodes.value.has(nodeId)
}

// -- Data Fetching --

async function loadMetrics(): Promise<void> {
  try {
    await fleetStore.fetchNpuFleetMetrics()
  } catch (err) {
    logger.error('Failed to load NPU fleet metrics', err)
  } finally {
    isLoading.value = false
  }
}

function startAutoRefresh(): void {
  stopAutoRefresh()
  refreshTimer = setInterval(loadMetrics, REFRESH_INTERVAL_MS)
}

function stopAutoRefresh(): void {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// -- Lifecycle --

onMounted(async () => {
  await loadMetrics()
  startAutoRefresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Loading Skeleton -->
    <template v-if="isLoading">
      <!-- Summary skeleton -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="i in 4"
          :key="i"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"
        >
          <div class="animate-pulse flex items-center gap-3">
            <div class="w-10 h-10 bg-gray-200 rounded-lg" />
            <div class="flex-1 space-y-2">
              <div class="h-5 bg-gray-200 rounded w-16" />
              <div class="h-3 bg-gray-200 rounded w-24" />
            </div>
          </div>
        </div>
      </div>

      <!-- Per-node skeleton -->
      <div class="space-y-3">
        <div
          v-for="i in 3"
          :key="i"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"
        >
          <div class="animate-pulse space-y-3">
            <div class="flex justify-between">
              <div class="h-4 bg-gray-200 rounded w-32" />
              <div class="h-4 bg-gray-200 rounded w-16" />
            </div>
            <div class="h-2 bg-gray-200 rounded w-full" />
            <div class="h-2 bg-gray-200 rounded w-3/4" />
          </div>
        </div>
      </div>
    </template>

    <!-- Loaded Content -->
    <template v-else>
      <!-- Fleet Summary Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- Total Inferences -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-blue-100">
              <!-- Bolt / lightning icon -->
              <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-gray-900">
                {{ (metrics?.total_inference_count ?? 0).toLocaleString() }}
              </p>
              <p class="text-sm text-gray-500">Total Inferences</p>
            </div>
          </div>
        </div>

        <!-- Avg Latency -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-purple-100">
              <!-- Clock icon -->
              <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-gray-900">
                {{ (metrics?.avg_latency_ms ?? 0).toFixed(1) }}
              </p>
              <p class="text-sm text-gray-500">Avg Latency (ms)</p>
            </div>
          </div>
        </div>

        <!-- Throughput -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-green-100">
              <!-- Trending up icon -->
              <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-gray-900">
                {{ (metrics?.total_throughput_rps ?? 0).toFixed(2) }}
              </p>
              <p class="text-sm text-gray-500">Throughput (req/s)</p>
            </div>
          </div>
        </div>

        <!-- Queue Depth -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-amber-100">
              <!-- Queue / list icon -->
              <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-gray-900">
                {{ metrics?.total_queue_depth ?? 0 }}
              </p>
              <p class="text-sm text-gray-500">Total Queue Depth</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Online / Total indicator -->
      <div class="flex items-center gap-2 text-sm text-gray-500">
        <span class="inline-block w-2 h-2 rounded-full bg-green-500" />
        {{ metrics?.online_nodes ?? 0 }} of {{ metrics?.total_nodes ?? 0 }} NPU nodes online
      </div>

      <!-- Per-Node Metrics -->
      <div class="space-y-3">
        <h3 class="text-lg font-semibold text-gray-900">Per-Node Metrics</h3>

        <p
          v-if="nodeMetrics.length === 0"
          class="text-sm text-gray-500 bg-white rounded-lg shadow-sm border border-gray-200 p-6 text-center"
        >
          No NPU worker metrics available.
        </p>

        <div
          v-for="node in nodeMetrics"
          :key="node.node_id"
          class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
        >
          <!-- Collapsed row header -->
          <button
            type="button"
            class="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors text-left"
            @click="toggleNode(node.node_id)"
          >
            <div class="flex items-center gap-3 min-w-0">
              <!-- Chevron -->
              <svg
                :class="[
                  'w-4 h-4 text-gray-400 transition-transform flex-shrink-0',
                  isExpanded(node.node_id) ? 'rotate-90' : '',
                ]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>

              <span class="font-medium text-gray-900 truncate">
                {{ node.node_id }}
              </span>
            </div>

            <div class="flex items-center gap-4 flex-shrink-0 text-sm">
              <!-- Utilization badge -->
              <span :class="['font-medium', utilizationTextColor(node.utilization)]">
                {{ node.utilization.toFixed(1) }}%
              </span>

              <!-- Latency -->
              <span class="text-gray-500 hidden sm:inline">
                {{ node.avg_latency_ms.toFixed(1) }} ms
              </span>

              <!-- Error badge -->
              <span
                v-if="node.error_count > 0"
                class="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700"
              >
                {{ node.error_count }} errors
              </span>
            </div>
          </button>

          <!-- Expanded details -->
          <div
            v-if="isExpanded(node.node_id)"
            class="border-t border-gray-200 px-4 py-4 space-y-4"
          >
            <!-- Utilization bar -->
            <div>
              <div class="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span>Utilization</span>
                <span :class="utilizationTextColor(node.utilization)">
                  {{ node.utilization.toFixed(1) }}%
                </span>
              </div>
              <div class="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  :class="['h-full rounded-full transition-all', utilizationBarColor(node.utilization)]"
                  :style="{ width: `${Math.min(100, node.utilization)}%` }"
                />
              </div>
            </div>

            <!-- Memory bar -->
            <div>
              <div class="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span>Memory</span>
                <span>
                  {{ node.memory_used_gb.toFixed(1) }} / {{ node.memory_total_gb.toFixed(1) }} GB
                </span>
              </div>
              <div class="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  :class="[
                    'h-full rounded-full transition-all',
                    utilizationBarColor(memoryPercent(node.memory_used_gb, node.memory_total_gb)),
                  ]"
                  :style="{ width: `${memoryPercent(node.memory_used_gb, node.memory_total_gb)}%` }"
                />
              </div>
            </div>

            <!-- Detail grid -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <!-- Temperature -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p :class="['text-lg font-semibold', temperatureColor(node.temperature_celsius)]">
                  {{ temperatureDisplay(node.temperature_celsius) }}
                </p>
                <p class="text-xs text-gray-500">Temperature</p>
              </div>

              <!-- Inference Count -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p class="text-lg font-semibold text-gray-900">
                  {{ node.inference_count.toLocaleString() }}
                </p>
                <p class="text-xs text-gray-500">Inferences</p>
              </div>

              <!-- Avg Latency -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p class="text-lg font-semibold text-gray-900">
                  {{ node.avg_latency_ms.toFixed(1) }}
                </p>
                <p class="text-xs text-gray-500">Avg Latency (ms)</p>
              </div>

              <!-- Throughput -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p class="text-lg font-semibold text-gray-900">
                  {{ node.throughput_rps.toFixed(2) }}
                </p>
                <p class="text-xs text-gray-500">Throughput (req/s)</p>
              </div>

              <!-- Queue Depth -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p class="text-lg font-semibold text-gray-900">
                  {{ node.queue_depth }}
                </p>
                <p class="text-xs text-gray-500">Queue Depth</p>
              </div>

              <!-- Error Count -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p
                  :class="[
                    'text-lg font-semibold',
                    node.error_count > 0 ? 'text-red-600' : 'text-gray-900',
                  ]"
                >
                  {{ node.error_count }}
                </p>
                <p class="text-xs text-gray-500">Errors</p>
              </div>

              <!-- Uptime -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p class="text-lg font-semibold text-gray-900">
                  {{ formatUptime(node.uptime_seconds) }}
                </p>
                <p class="text-xs text-gray-500">Uptime</p>
              </div>

              <!-- Last Report -->
              <div class="text-center p-2 bg-gray-50 rounded">
                <p class="text-lg font-semibold text-gray-900">
                  {{ node.timestamp ? new Date(node.timestamp).toLocaleTimeString() : 'N/A' }}
                </p>
                <p class="text-xs text-gray-500">Last Report</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
