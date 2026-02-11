// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * LoadBalancingView - NPU Worker Load Balancing Visualization
 *
 * Displays load balancing strategy configuration, task distribution
 * across NPU workers as horizontal bar charts, per-worker load
 * overview cards, and rebalancing controls.
 *
 * Auto-refreshes every 10 seconds.
 *
 * Related to Issue #590 (NPU Dashboard Improvements).
 */

import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type {
  NPULoadBalancingConfig,
  NPUFleetMetrics,
  NPUWorkerMetrics,
} from '@/types/slm'

const logger = createLogger('LoadBalancingView')

const fleetStore = useFleetStore()

// ============================================================
// State
// ============================================================

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const notification = ref<string | null>(null)
const autoRebalance = ref(false)
const refreshIntervalId = ref<ReturnType<typeof setInterval> | null>(null)

const selectedStrategy = ref<NPULoadBalancingConfig['strategy']>('round-robin')

// ============================================================
// Computed
// ============================================================

const fleetMetrics = computed<NPUFleetMetrics | null>(
  () => fleetStore.npuFleetMetrics
)

const workerMetrics = computed<NPUWorkerMetrics[]>(
  () => fleetMetrics.value?.node_metrics ?? []
)

const currentConfig = computed<NPULoadBalancingConfig | null>(
  () => fleetStore.npuLoadBalancingConfig
)

const maxQueueDepth = computed(() => {
  if (workerMetrics.value.length === 0) return 1
  return Math.max(...workerMetrics.value.map(w => w.queue_depth), 1)
})

const totalQueueDepth = computed(() => {
  return workerMetrics.value.reduce((sum, w) => sum + w.queue_depth, 0)
})

/**
 * Workers sorted by utilization, highest first.
 */
const sortedWorkers = computed(() => {
  return [...workerMetrics.value].sort(
    (a, b) => b.utilization - a.utilization
  )
})

const strategyDescriptions: Record<NPULoadBalancingConfig['strategy'], string> = {
  'round-robin': 'Distributes requests evenly across all NPU workers in sequence.',
  'least-loaded': 'Routes each request to the worker with the lowest current utilization.',
  'model-affinity': 'Routes requests to workers that already have the required model loaded.',
}

// ============================================================
// Helpers
// ============================================================

/**
 * Resolve the hostname for a worker from the fleet store nodes.
 */
function getWorkerHostname(nodeId: string): string {
  const node = fleetStore.getNode(nodeId)
  return node?.hostname ?? nodeId
}

/**
 * Resolve the IP address for a worker from the fleet store nodes.
 */
function getWorkerIp(nodeId: string): string {
  const node = fleetStore.getNode(nodeId)
  return node?.ip_address ?? 'N/A'
}

/**
 * Get the worker config (priority, weight, assigned models) from the store cache.
 */
function getWorkerConfig(nodeId: string) {
  return fleetStore.npuWorkerConfigs.get(nodeId)
}

/**
 * Return the bar color class based on queue depth relative to max.
 */
function queueBarColor(queueDepth: number): string {
  if (maxQueueDepth.value === 0) return 'bg-green-500'
  const ratio = queueDepth / maxQueueDepth.value
  if (ratio > 0.7) return 'bg-red-500'
  if (ratio >= 0.3) return 'bg-yellow-500'
  return 'bg-green-500'
}

/**
 * Return the bar width percentage for a given queue depth.
 */
function queueBarWidth(queueDepth: number): number {
  if (totalQueueDepth.value === 0) return 0
  return Math.round((queueDepth / totalQueueDepth.value) * 100)
}

/**
 * Return the utilization bar color class.
 */
function utilizationColor(utilization: number): string {
  if (utilization >= 80) return 'bg-red-500'
  if (utilization >= 60) return 'bg-yellow-500'
  return 'bg-green-500'
}

/**
 * Show a temporary notification message.
 */
function showNotification(message: string): void {
  notification.value = message
  setTimeout(() => {
    notification.value = null
  }, 4000)
}

// ============================================================
// Actions
// ============================================================

/**
 * Load all data: fleet metrics, load balancing config, worker configs.
 */
async function refreshData(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    await Promise.all([
      fleetStore.fetchNodes(),
      fleetStore.fetchNpuFleetMetrics(),
      fleetStore.fetchNpuLoadBalancing(),
    ])

    // Sync selected strategy with fetched config
    if (currentConfig.value) {
      selectedStrategy.value = currentConfig.value.strategy
    }

    // Fetch per-worker configs for priority/weight display
    const nodeMetrics = fleetMetrics.value?.node_metrics ?? []
    await Promise.all(
      nodeMetrics.map(m => fleetStore.fetchNpuWorkerConfig(m.node_id))
    )
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Failed to load data'
    error.value = msg
    logger.error('refreshData failed:', msg)
  } finally {
    loading.value = false
  }
}

/**
 * Save the selected load balancing strategy.
 */
async function saveStrategy(): Promise<void> {
  saving.value = true
  error.value = null

  try {
    const config: NPULoadBalancingConfig = {
      strategy: selectedStrategy.value,
      modelAffinity: currentConfig.value?.modelAffinity ?? {},
    }
    await fleetStore.updateNpuLoadBalancing(config)
    showNotification('Load balancing strategy updated successfully.')
    logger.info('Strategy updated to', selectedStrategy.value)
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Failed to save strategy'
    error.value = msg
    logger.error('saveStrategy failed:', msg)
  } finally {
    saving.value = false
  }
}

/**
 * Trigger a manual rebalance by refreshing fleet metrics.
 */
async function rebalanceNow(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    await fleetStore.fetchNpuFleetMetrics()
    showNotification('Fleet metrics refreshed. Load distribution updated.')
    logger.info('Manual rebalance triggered')
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Rebalance failed'
    error.value = msg
    logger.error('rebalanceNow failed:', msg)
  } finally {
    loading.value = false
  }
}

/**
 * Compute the recommended action when auto-rebalance is toggled on.
 */
const autoRebalanceRecommendation = computed(() => {
  if (!autoRebalance.value) return null
  if (workerMetrics.value.length < 2) return 'Need at least 2 workers for rebalancing.'

  const utils = workerMetrics.value.map(w => w.utilization)
  const maxUtil = Math.max(...utils)
  const minUtil = Math.min(...utils)
  const spread = maxUtil - minUtil

  if (spread > 40) {
    return `High utilization spread (${spread.toFixed(0)}%). Consider switching to "least-loaded" strategy.`
  }
  if (spread > 20) {
    return `Moderate utilization spread (${spread.toFixed(0)}%). Current strategy may be adequate.`
  }
  return 'Load is well distributed. No action needed.'
})

// ============================================================
// Lifecycle
// ============================================================

onMounted(() => {
  refreshData()
  refreshIntervalId.value = setInterval(refreshData, 10_000)
})

onBeforeUnmount(() => {
  if (refreshIntervalId.value !== null) {
    clearInterval(refreshIntervalId.value)
    refreshIntervalId.value = null
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- Notification Banner -->
    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 -translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-2"
    >
      <div
        v-if="notification"
        class="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2"
      >
        <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {{ notification }}
      </div>
    </Transition>

    <!-- Error Banner -->
    <div
      v-if="error"
      class="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
    >
      {{ error }}
    </div>

    <!-- ============================================================ -->
    <!-- Strategy Configuration                                        -->
    <!-- ============================================================ -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Strategy Configuration</h2>

      <div class="flex flex-col sm:flex-row sm:items-end gap-4">
        <div class="flex-1">
          <label
            for="lb-strategy"
            class="block text-sm font-medium text-gray-700 mb-1"
          >
            Current Strategy
          </label>
          <select
            id="lb-strategy"
            v-model="selectedStrategy"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white text-sm"
          >
            <option value="round-robin">Round Robin</option>
            <option value="least-loaded">Least Loaded</option>
            <option value="model-affinity">Model Affinity</option>
          </select>
          <p class="text-xs text-gray-500 mt-1">
            {{ strategyDescriptions[selectedStrategy] }}
          </p>
        </div>

        <button
          @click="saveStrategy"
          :disabled="saving || selectedStrategy === currentConfig?.strategy"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium whitespace-nowrap"
        >
          {{ saving ? 'Saving...' : 'Save Strategy' }}
        </button>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- Task Distribution Bar Chart                                   -->
    <!-- ============================================================ -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Task Distribution</h2>

      <div v-if="workerMetrics.length === 0 && !loading" class="text-sm text-gray-500 text-center py-8">
        No NPU worker metrics available.
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="worker in workerMetrics"
          :key="worker.node_id"
          class="flex items-center gap-4"
        >
          <!-- Worker label -->
          <div class="w-36 flex-shrink-0 text-sm">
            <span class="font-medium text-gray-900 truncate block">
              {{ getWorkerHostname(worker.node_id) }}
            </span>
          </div>

          <!-- Bar -->
          <div class="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden relative">
            <div
              :class="['h-full rounded-full transition-all duration-500', queueBarColor(worker.queue_depth)]"
              :style="{ width: `${Math.max(queueBarWidth(worker.queue_depth), 2)}%` }"
            />
            <span
              v-if="worker.queue_depth > 0"
              class="absolute inset-0 flex items-center justify-center text-xs font-medium"
              :class="queueBarWidth(worker.queue_depth) > 40 ? 'text-white' : 'text-gray-700'"
            >
              {{ worker.queue_depth }} tasks
            </span>
          </div>

          <!-- Percentage -->
          <div class="w-14 text-right text-sm font-medium text-gray-600">
            {{ queueBarWidth(worker.queue_depth) }}%
          </div>
        </div>
      </div>

      <!-- Total summary -->
      <div
        v-if="workerMetrics.length > 0"
        class="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between text-sm text-gray-500"
      >
        <span>Total queue depth across all workers</span>
        <span class="font-medium text-gray-900">{{ totalQueueDepth }}</span>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- Worker Load Overview                                          -->
    <!-- ============================================================ -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Worker Load Overview</h2>

      <div v-if="sortedWorkers.length === 0 && !loading" class="text-sm text-gray-500 text-center py-8">
        No NPU workers found.
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="worker in sortedWorkers"
          :key="worker.node_id"
          class="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors"
        >
          <!-- Header: hostname + IP -->
          <div class="mb-3">
            <h3 class="font-medium text-gray-900 text-sm">
              {{ getWorkerHostname(worker.node_id) }}
            </h3>
            <p class="text-xs text-gray-500">{{ getWorkerIp(worker.node_id) }}</p>
          </div>

          <!-- Utilization bar -->
          <div class="mb-3">
            <div class="flex items-center justify-between text-xs text-gray-500 mb-1">
              <span>Utilization</span>
              <span class="font-medium">{{ worker.utilization.toFixed(1) }}%</span>
            </div>
            <div class="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                :class="['h-full rounded-full transition-all duration-500', utilizationColor(worker.utilization)]"
                :style="{ width: `${worker.utilization}%` }"
              />
            </div>
          </div>

          <!-- Stats grid -->
          <div class="grid grid-cols-2 gap-2 text-center">
            <div class="p-2 bg-gray-50 rounded">
              <p class="text-sm font-semibold text-gray-900">{{ worker.queue_depth }}</p>
              <p class="text-xs text-gray-500">Queue Depth</p>
            </div>
            <div class="p-2 bg-gray-50 rounded">
              <p class="text-sm font-semibold text-gray-900">
                {{ getWorkerConfig(worker.node_id)?.assigned_models?.length ?? 0 }}
              </p>
              <p class="text-xs text-gray-500">Models</p>
            </div>
          </div>

          <!-- Priority & Weight (from worker config) -->
          <div
            v-if="getWorkerConfig(worker.node_id)"
            class="mt-3 flex items-center gap-3 text-xs text-gray-500"
          >
            <span>
              Priority:
              <span class="font-medium text-gray-700">
                {{ getWorkerConfig(worker.node_id)?.priority ?? '-' }}
              </span>
            </span>
            <span>
              Weight:
              <span class="font-medium text-gray-700">
                {{ getWorkerConfig(worker.node_id)?.weight ?? '-' }}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- Rebalancing Controls                                          -->
    <!-- ============================================================ -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">Rebalancing Controls</h2>

      <div class="flex flex-col sm:flex-row sm:items-center gap-4">
        <!-- Rebalance Now button -->
        <button
          @click="rebalanceNow"
          :disabled="loading || workerMetrics.length === 0"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', loading ? 'animate-spin' : '']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ loading ? 'Refreshing...' : 'Rebalance Now' }}
        </button>

        <!-- Auto-rebalance toggle -->
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <div class="relative">
            <input
              type="checkbox"
              v-model="autoRebalance"
              class="sr-only peer"
            />
            <div class="w-9 h-5 bg-gray-200 peer-focus:ring-2 peer-focus:ring-primary-300 rounded-full peer peer-checked:bg-primary-600 transition-colors" />
            <div class="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
          </div>
          <span class="text-sm text-gray-700">Auto-rebalance</span>
        </label>
      </div>

      <!-- Auto-rebalance recommendation -->
      <Transition
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="opacity-0 max-h-0"
        enter-to-class="opacity-100 max-h-20"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="opacity-100 max-h-20"
        leave-to-class="opacity-0 max-h-0"
      >
        <div
          v-if="autoRebalanceRecommendation"
          class="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700 flex items-start gap-2"
        >
          <svg class="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{{ autoRebalanceRecommendation }}</span>
        </div>
      </Transition>
    </div>

    <!-- Loading overlay for initial load -->
    <div
      v-if="loading && workerMetrics.length === 0"
      class="flex items-center justify-center py-12 text-gray-500 text-sm"
    >
      <svg class="w-5 h-5 animate-spin mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
      Loading NPU fleet data...
    </div>
  </div>
</template>
