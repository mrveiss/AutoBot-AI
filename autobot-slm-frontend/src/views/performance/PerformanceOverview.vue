<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * PerformanceOverview - Main performance dashboard
 *
 * Displays metric cards, SLO compliance bar, and top slow traces table.
 * Auto-refreshes every 30s with manual refresh support.
 * Issue #752 - Comprehensive performance monitoring.
 */

import { onMounted, onUnmounted, computed } from 'vue'
import { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'

const {
  overview,
  loading,
  error,
  fetchOverview,
} = usePerformanceMonitoring()

let refreshTimer: ReturnType<typeof setInterval> | null = null
const REFRESH_INTERVAL = 30000

onMounted(() => {
  fetchOverview()
  refreshTimer = setInterval(fetchOverview, REFRESH_INTERVAL)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})

const avgLatency = computed(() => overview.value?.avg_latency_ms ?? 0)
const p95Latency = computed(() => overview.value?.p95_latency_ms ?? 0)
const throughput = computed(() => overview.value?.throughput_rpm ?? 0)
const errorRate = computed(() => overview.value?.error_rate_percent ?? 0)
const sloCompliance = computed(() => overview.value?.slo_compliance_percent ?? 0)
const activeSlos = computed(() => overview.value?.active_slos ?? 0)
const totalTraces = computed(() => overview.value?.total_traces ?? 0)
const topSlowTraces = computed(() => overview.value?.top_slow_traces ?? [])

/**
 * Determine color class for latency values.
 */
function latencyColor(ms: number): string {
  if (ms < 200) return 'text-green-600'
  if (ms < 1000) return 'text-amber-600'
  return 'text-red-600'
}

/**
 * Determine color class for error rate.
 */
function errorRateColor(pct: number): string {
  if (pct < 1) return 'text-green-600'
  if (pct < 5) return 'text-amber-600'
  return 'text-red-600'
}

/**
 * Determine color class for SLO compliance progress bar.
 */
function sloBarColor(): string {
  const pct = sloCompliance.value
  if (pct >= 99) return 'bg-green-500'
  if (pct >= 95) return 'bg-amber-500'
  return 'bg-red-500'
}

/**
 * Format trace status for display.
 */
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'ok': return 'bg-green-100 text-green-700'
    case 'error': return 'bg-red-100 text-red-700'
    case 'timeout': return 'bg-amber-100 text-amber-700'
    default: return 'bg-gray-100 text-gray-700'
  }
}

/**
 * Format duration for display.
 */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/**
 * Format date string for display.
 */
function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString()
}
</script>

<template>
  <div class="p-6">
    <!-- Error Banner -->
    <div
      v-if="error"
      class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
    >
      {{ error }}
    </div>

    <!-- Refresh Bar -->
    <div class="flex items-center justify-between mb-6">
      <div class="text-sm text-gray-500">
        <span v-if="totalTraces > 0">{{ totalTraces.toLocaleString() }} total traces</span>
        <span v-if="activeSlos > 0" class="ml-4">{{ activeSlos }} active SLOs</span>
      </div>
      <button
        @click="fetchOverview"
        :disabled="loading"
        class="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
      >
        <svg
          :class="['w-4 h-4', loading ? 'animate-spin' : '']"
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

    <!-- Metric Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <!-- Avg Latency -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500 mb-1">Avg Latency</p>
        <p :class="['text-3xl font-bold', latencyColor(avgLatency)]">
          {{ formatDuration(avgLatency) }}
        </p>
        <p class="text-xs text-gray-400 mt-1">P95: {{ formatDuration(p95Latency) }}</p>
      </div>

      <!-- P95 Latency -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500 mb-1">P95 Latency</p>
        <p :class="['text-3xl font-bold', latencyColor(p95Latency)]">
          {{ formatDuration(p95Latency) }}
        </p>
        <p class="text-xs text-gray-400 mt-1">
          P99: {{ formatDuration(overview?.p99_latency_ms ?? 0) }}
        </p>
      </div>

      <!-- Throughput -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500 mb-1">Throughput</p>
        <p class="text-3xl font-bold text-gray-900">
          {{ throughput.toLocaleString() }}
        </p>
        <p class="text-xs text-gray-400 mt-1">requests / min</p>
      </div>

      <!-- Error Rate -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500 mb-1">Error Rate</p>
        <p :class="['text-3xl font-bold', errorRateColor(errorRate)]">
          {{ errorRate.toFixed(2) }}%
        </p>
        <p class="text-xs text-gray-400 mt-1">of total requests</p>
      </div>
    </div>

    <!-- SLO Compliance -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-medium text-gray-700">SLO Compliance</h2>
        <span class="text-sm font-semibold text-gray-900">
          {{ sloCompliance.toFixed(1) }}%
        </span>
      </div>
      <div class="w-full bg-gray-200 rounded-full h-3">
        <div
          :class="['h-3 rounded-full transition-all duration-500', sloBarColor()]"
          :style="{ width: `${Math.min(sloCompliance, 100)}%` }"
        ></div>
      </div>
      <p class="text-xs text-gray-400 mt-1">
        {{ activeSlos }} active SLO{{ activeSlos !== 1 ? 's' : '' }} tracked
      </p>
    </div>

    <!-- Top 10 Slowest Traces -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200">
      <div class="px-4 py-3 border-b border-gray-200">
        <h2 class="text-sm font-medium text-gray-700">Top 10 Slowest Traces</h2>
      </div>
      <div v-if="topSlowTraces.length === 0 && !loading" class="p-8 text-center text-gray-400">
        No trace data available
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Spans</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Time</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr
              v-for="trace in topSlowTraces"
              :key="trace.trace_id"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-2 text-sm text-gray-900 font-medium max-w-xs truncate">
                {{ trace.name }}
              </td>
              <td class="px-4 py-2 text-sm font-mono">
                <span :class="latencyColor(trace.duration_ms)">
                  {{ formatDuration(trace.duration_ms) }}
                </span>
              </td>
              <td class="px-4 py-2 text-sm text-gray-600">{{ trace.span_count }}</td>
              <td class="px-4 py-2">
                <span
                  :class="['px-2 py-0.5 text-xs font-medium rounded-full', statusBadgeClass(trace.status)]"
                >
                  {{ trace.status }}
                </span>
              </td>
              <td class="px-4 py-2 text-sm text-gray-500">
                {{ trace.source_node_id ?? '-' }}
              </td>
              <td class="px-4 py-2 text-sm text-gray-500 whitespace-nowrap">
                {{ formatDate(trace.created_at) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
