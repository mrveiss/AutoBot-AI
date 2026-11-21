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

import { formatFleetTime } from '@/composables/useTimezone'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { PollingPausedAlert, BaseSkeleton, formatUptime } from '@autobot/ui'
import { useDashboardPoller } from '@/composables/useDashboardPoller'
import type { NPUFleetMetrics, NPUWorkerMetrics } from '@/types/slm'
import { useFleetStore } from '@/stores/fleet'

const fleetStore = useFleetStore()

const isLoading = ref(true)
const expandedNodes = ref<Set<string>>(new Set())

const REFRESH_INTERVAL_MS = 5000

// -- Computed --

const metrics = computed<NPUFleetMetrics | null>(
  () => fleetStore.npuFleetMetrics
)

const nodeMetrics = computed<NPUWorkerMetrics[]>(
  () => metrics.value?.node_metrics ?? []
)

// -- Helpers --

function utilizationBarColor(pct: number): string {
  if (pct > 80) return 'bg-autobot-dot-bad'
  if (pct >= 60) return 'bg-autobot-dot-warn'
  return 'bg-autobot-dot-ok'
}

function utilizationTextColor(pct: number): string {
  if (pct > 80) return 'text-autobot-error'
  if (pct >= 60) return 'text-autobot-pill-warn-fg'
  return 'text-autobot-success'
}

// #13138: `temperature_celsius` is optional AND nullable in the contract
// (`temperature_celsius?: float | None`), so an absent reading arrives as
// `undefined`, not `null` — a `=== null` test alone let it fall through to the
// "cool" branch and render `undefined°C`.
function temperatureColor(temp: number | null | undefined): string {
  if (temp === null || temp === undefined) return 'text-autobot-text-tertiary'
  if (temp > 75) return 'text-autobot-error'
  if (temp >= 60) return 'text-autobot-pill-warn-fg'
  return 'text-autobot-success'
}

function temperatureDisplay(temp: number | null | undefined): string {
  if (temp === null || temp === undefined) return 'N/A'
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

const { t } = useI18n()

/** One tick; the store rethrows a failed read, so the poller counts it. */
async function loadMetrics(): Promise<void> {
  try {
    await fleetStore.fetchNpuFleetMetrics()
  } finally {
    isLoading.value = false
  }
}

// #19482: the shared dashboard policy (stop on unmount and after repeated failures, paused alert)
const metricsPoller = useDashboardPoller(loadMetrics, REFRESH_INTERVAL_MS)

// -- Lifecycle --

onMounted(() => metricsPoller.start(''))
</script>

<template>
  <div class="space-y-6">
    <PollingPausedAlert
      :poller="metricsPoller"
      :message="t('common.polling.paused')"
      :retry-label="t('common.polling.retry')"
      @retry="metricsPoller.start('')"
    />
    <!-- Loading Skeleton -->
    <template v-if="isLoading">
      <!-- Summary skeleton -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="i in 4"
          :key="i"
          class="bg-white rounded-lg shadow-xs border border-autobot-border p-4"
        >
          <div class="flex items-center gap-3" role="status" aria-busy="true" :aria-label="t('fleet.loadBalancingView.loadingNPUFleetData')">
            <div class="w-10 shrink-0"><BaseSkeleton shape="block" height="2.5rem" /></div>
            <div class="flex-1"><BaseSkeleton :lines="2" /></div>
          </div>
        </div>
      </div>

      <!-- Per-node skeleton -->
      <div class="space-y-3">
        <div
          v-for="i in 3"
          :key="i"
          class="bg-white rounded-lg shadow-xs border border-autobot-border p-4"
        >
          <div role="status" aria-busy="true" :aria-label="t('fleet.loadBalancingView.loadingNPUFleetData')"><BaseSkeleton :lines="3" /></div>
        </div>
      </div>
    </template>

    <!-- Loaded Content -->
    <template v-else>
      <!-- Fleet Summary Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- Total Inferences -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-autobot-pill-info-bg">
              <!-- Bolt / lightning icon -->
              <svg class="w-5 h-5 text-autobot-text-link" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-autobot-text-primary">
                {{ (metrics?.total_inference_count ?? 0).toLocaleString() }}
              </p>
              <p class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.totalInferences') }}</p>
            </div>
          </div>
        </div>

        <!-- Avg Latency -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-autobot-illus-2-tint">
              <!-- Clock icon -->
              <svg class="w-5 h-5 text-autobot-text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-autobot-text-primary">
                {{ (metrics?.avg_latency_ms ?? 0).toFixed(1) }}
              </p>
              <p class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.avgLatencyMs') }}</p>
            </div>
          </div>
        </div>

        <!-- Throughput -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-autobot-pill-ok-bg">
              <!-- Trending up icon -->
              <svg class="w-5 h-5 text-autobot-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-autobot-text-primary">
                {{ (metrics?.total_throughput_rps ?? 0).toFixed(2) }}
              </p>
              <p class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.throughputReqS') }}</p>
            </div>
          </div>
        </div>

        <!-- Queue Depth -->
        <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-autobot-pill-warn-bg">
              <!-- Queue / list icon -->
              <svg class="w-5 h-5 text-autobot-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </div>
            <div>
              <p class="text-2xl font-bold text-autobot-text-primary">
                {{ metrics?.total_queue_depth ?? 0 }}
              </p>
              <p class="text-sm text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.totalQueueDepth') }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Online / Total indicator -->
      <div class="flex items-center gap-2 text-sm text-autobot-text-tertiary">
        <span class="inline-block w-2 h-2 rounded-full bg-autobot-dot-ok" />{{ $t('fleet.nPUPerformanceMetrics.value0OfValue1NPUNodesOnline', { value0: metrics?.online_nodes ?? 0, value1: metrics?.total_nodes ?? 0 }) }}</div>

      <!-- Per-Node Metrics -->
      <div class="space-y-3">
        <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('fleet.nPUPerformanceMetrics.perNodeMetrics') }}</h3>

        <p
          v-if="nodeMetrics.length === 0"
          class="text-sm text-autobot-text-tertiary bg-white rounded-lg shadow-xs border border-autobot-border p-6 text-center"
        >{{ $t('fleet.nPUPerformanceMetrics.noNPUWorkerMetricsAvailable') }}</p>

        <div
          v-for="node in nodeMetrics"
          :key="node.node_id"
          class="bg-white rounded-lg shadow-xs border border-autobot-border overflow-hidden"
        >
          <!-- Collapsed row header -->
          <button
            type="button"
            class="w-full px-4 py-3 flex items-center justify-between hover:bg-autobot-bg-hover transition-colors text-left"
            @click="toggleNode(node.node_id)"
          >
            <div class="flex items-center gap-3 min-w-0">
              <!-- Chevron -->
              <svg
                :class="[
                  'w-4 h-4 text-autobot-text-tertiary transition-transform shrink-0',
                  isExpanded(node.node_id) ? 'rotate-90' : '',
                ]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>

              <span class="font-medium text-autobot-text-primary truncate">
                {{ node.node_id }}
              </span>
            </div>

            <div class="flex items-center gap-4 shrink-0 text-sm">
              <!-- Utilization badge -->
              <span :class="['font-medium', utilizationTextColor(node.utilization)]">
                {{ node.utilization.toFixed(1) }}%
              </span>

              <!-- Latency -->
              <span class="text-autobot-text-tertiary hidden sm:inline">
                {{ node.avg_latency_ms.toFixed(1) }} ms
              </span>

              <!-- Error badge -->
              <span
                v-if="node.error_count > 0"
                class="px-2 py-0.5 rounded-full text-xs font-medium bg-autobot-pill-bad-bg text-autobot-pill-bad-fg"
              >{{ $t('fleet.nPUPerformanceMetrics.value0Errors', { value0: node.error_count }) }}</span>
            </div>
          </button>

          <!-- Expanded details -->
          <div
            v-if="isExpanded(node.node_id)"
            class="border-t border-autobot-border px-4 py-4 space-y-4"
          >
            <!-- Utilization bar -->
            <div>
              <div class="flex items-center justify-between text-xs text-autobot-text-tertiary mb-1">
                <span>{{ $t('fleet.nPUPerformanceMetrics.utilization') }}</span>
                <span :class="utilizationTextColor(node.utilization)">
                  {{ node.utilization.toFixed(1) }}%
                </span>
              </div>
              <div class="w-full h-2.5 bg-autobot-bg-active rounded-full overflow-hidden">
                <div
                  :class="['h-full rounded-full transition-all', utilizationBarColor(node.utilization)]"
                  :style="{ width: `${Math.min(100, node.utilization)}%` }"
                />
              </div>
            </div>

            <!-- Memory bar -->
            <div>
              <div class="flex items-center justify-between text-xs text-autobot-text-tertiary mb-1">
                <span>{{ $t('fleet.nPUPerformanceMetrics.memory') }}</span>
                <span>
                  {{ node.memory_used_gb.toFixed(1) }} / {{ node.memory_total_gb.toFixed(1) }} GB
                </span>
              </div>
              <div class="w-full h-2.5 bg-autobot-bg-active rounded-full overflow-hidden">
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
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p :class="['text-lg font-semibold', temperatureColor(node.temperature_celsius)]">
                  {{ temperatureDisplay(node.temperature_celsius) }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.temperature') }}</p>
              </div>

              <!-- Inference Count -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p class="text-lg font-semibold text-autobot-text-primary">
                  {{ node.inference_count.toLocaleString() }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.inferences') }}</p>
              </div>

              <!-- Avg Latency -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p class="text-lg font-semibold text-autobot-text-primary">
                  {{ node.avg_latency_ms.toFixed(1) }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.avgLatencyMs') }}</p>
              </div>

              <!-- Throughput -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p class="text-lg font-semibold text-autobot-text-primary">
                  {{ node.throughput_rps.toFixed(2) }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.throughputReqS') }}</p>
              </div>

              <!-- Queue Depth -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p class="text-lg font-semibold text-autobot-text-primary">
                  {{ node.queue_depth }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.queueDepth') }}</p>
              </div>

              <!-- Error Count -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p
                  :class="[
                    'text-lg font-semibold',
                    node.error_count > 0 ? 'text-autobot-error' : 'text-autobot-text-primary',
                  ]"
                >
                  {{ node.error_count }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.errors') }}</p>
              </div>

              <!-- Uptime -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p class="text-lg font-semibold text-autobot-text-primary">
                  {{ formatUptime(node.uptime_seconds) }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.uptime') }}</p>
              </div>

              <!-- Last Report -->
              <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
                <p class="text-lg font-semibold text-autobot-text-primary">
                  {{ node.timestamp ? formatFleetTime(node.timestamp) : 'N/A' }}
                </p>
                <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUPerformanceMetrics.lastReport') }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
