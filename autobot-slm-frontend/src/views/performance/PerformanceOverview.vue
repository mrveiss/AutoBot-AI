<script setup lang="ts">
import { BaseAlert, PollingPausedAlert, formatDuration } from '@autobot/ui'
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

import { onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'
import { injectPerformanceMonitoring } from '@/composables/monitoringPollContext'
import { formatFleetDateTime } from '@/composables/useTimezone'

// #19851: PerformanceView owns the poll and shows the paused notice; this view only
// polls (and shows its own notice) when rendered without that layout.
const { state: performance, ownsPoll } = injectPerformanceMonitoring(() => usePerformanceMonitoring())
const {
  overview,
  loading,
  error,
  startPolling,
  poller,
} = performance

const { t } = useI18n()

// #19482: the composable's poller carries the shared dashboard policy (30s default)
onMounted(() => {
  if (ownsPoll) startPolling()
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
  if (ms < 200) return 'text-autobot-success'
  if (ms < 1000) return 'text-autobot-warning'
  return 'text-autobot-error'
}

/**
 * Determine color class for error rate.
 */
function errorRateColor(pct: number): string {
  if (pct < 1) return 'text-autobot-success'
  if (pct < 5) return 'text-autobot-warning'
  return 'text-autobot-error'
}

/**
 * Determine color class for SLO compliance progress bar.
 */
function sloBarColor(): string {
  const pct = sloCompliance.value
  if (pct >= 99) return 'bg-autobot-dot-ok'
  if (pct >= 95) return 'bg-autobot-dot-warn'
  return 'bg-autobot-dot-bad'
}

/**
 * Format trace status for display.
 */
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'ok': return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'error': return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    case 'timeout': return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    default: return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
  }
}

/**
 * Format duration for display.
 */

</script>

<template>
  <div class="p-6">
    <PollingPausedAlert v-if="ownsPoll" :poller="poller" :message="t('common.polling.paused')" :retry-label="t('common.polling.retry')" class="mb-4" @retry="poller.start('')" />

    <!-- Error Banner -->
    <BaseAlert v-if="error" variant="error" class="mb-4" :message="error" />

    <!-- Refresh Bar -->
    <div class="flex items-center justify-between mb-6">
      <div class="text-sm text-autobot-text-tertiary">
        <span v-if="totalTraces > 0">{{ $t('performance.performanceOverview.value0TotalTraces', { value0: totalTraces.toLocaleString() }) }}</span>
        <span v-if="activeSlos > 0" class="ml-4">{{ $t('performance.performanceOverview.value0ActiveSLOs', { value0: activeSlos }) }}</span>
      </div>
      <button
        @click="poller.start('')"
        :disabled="loading"
        class="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover transition-colors disabled:opacity-50"
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
        {{ $t('performance.performanceOverview.refresh') }}
      </button>
    </div>

    <!-- Metric Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <!-- Avg Latency -->
      <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
        <p class="text-sm text-autobot-text-tertiary mb-1">{{ $t('performance.performanceOverview.avgLatency') }}</p>
        <p :class="['text-3xl font-bold', latencyColor(avgLatency)]">
          {{ formatDuration(avgLatency, { style: 'msSeconds2dp' }) }}
        </p>
        <p class="text-xs text-autobot-text-tertiary mt-1">P95: {{ formatDuration(p95Latency, { style: 'msSeconds2dp' }) }}</p>
      </div>

      <!-- P95 Latency -->
      <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
        <p class="text-sm text-autobot-text-tertiary mb-1">{{ $t('performance.performanceOverview.p95Latency') }}</p>
        <p :class="['text-3xl font-bold', latencyColor(p95Latency)]">
          {{ formatDuration(p95Latency, { style: 'msSeconds2dp' }) }}
        </p>
        <p class="text-xs text-autobot-text-tertiary mt-1">
          P99: {{ formatDuration(overview?.p99_latency_ms ?? 0, { style: 'msSeconds2dp' }) }}
        </p>
      </div>

      <!-- Throughput -->
      <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
        <p class="text-sm text-autobot-text-tertiary mb-1">{{ $t('performance.performanceOverview.throughput') }}</p>
        <p class="text-3xl font-bold text-autobot-text-primary">
          {{ throughput.toLocaleString() }}
        </p>
        <p class="text-xs text-autobot-text-tertiary mt-1">{{ $t('performance.performanceOverview.requestsMin') }}</p>
      </div>

      <!-- Error Rate -->
      <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4">
        <p class="text-sm text-autobot-text-tertiary mb-1">{{ $t('performance.performanceOverview.errorRate') }}</p>
        <p :class="['text-3xl font-bold', errorRateColor(errorRate)]">
          {{ errorRate.toFixed(2) }}%
        </p>
        <p class="text-xs text-autobot-text-tertiary mt-1">{{ $t('performance.performanceOverview.ofTotalRequests') }}</p>
      </div>
    </div>

    <!-- SLO Compliance -->
    <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-4 mb-6">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-medium text-autobot-text-secondary">{{ $t('performance.performanceOverview.sLOCompliance') }}</h2>
        <span class="text-sm font-semibold text-autobot-text-primary">
          {{ sloCompliance.toFixed(1) }}%
        </span>
      </div>
      <div class="w-full bg-autobot-bg-active rounded-full h-3">
        <div
          :class="['h-3 rounded-full transition-all duration-500', sloBarColor()]"
          :style="{ width: `${Math.min(sloCompliance, 100)}%` }"
        ></div>
      </div>
      <p class="text-xs text-autobot-text-tertiary mt-1">{{ $t('performance.performanceOverview.value0ActiveSLOPluralTracked', { value0: activeSlos, plural: activeSlos !== 1 ? 's' : '' }) }}</p>
    </div>

    <!-- Top 10 Slowest Traces -->
    <div class="bg-white rounded-lg shadow-xs border border-autobot-border">
      <div class="px-4 py-3 border-b border-autobot-border">
        <h2 class="text-sm font-medium text-autobot-text-secondary">{{ $t('performance.performanceOverview.top10SlowestTraces') }}</h2>
      </div>
      <div v-if="topSlowTraces.length === 0 && !loading" class="p-8 text-center text-autobot-text-tertiary">
        {{ $t('performance.performanceOverview.noTraceDataAvailable') }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-autobot-border">
          <thead class="bg-autobot-bg-secondary">
            <tr>
              <th class="px-4 py-2 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('performance.performanceOverview.name') }}</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('performance.performanceOverview.duration') }}</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('performance.performanceOverview.spans') }}</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('performance.performanceOverview.status') }}</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('performance.performanceOverview.node') }}</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-autobot-text-tertiary uppercase">{{ $t('performance.performanceOverview.time') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-autobot-border">
            <tr
              v-for="trace in topSlowTraces"
              :key="trace.trace_id"
              class="hover:bg-autobot-bg-hover"
            >
              <td class="px-4 py-2 text-sm text-autobot-text-primary font-medium max-w-xs truncate">
                {{ trace.name }}
              </td>
              <td class="px-4 py-2 text-sm font-mono">
                <span :class="latencyColor(trace.duration_ms)">
                  {{ formatDuration(trace.duration_ms, { style: 'msSeconds2dp' }) }}
                </span>
              </td>
              <td class="px-4 py-2 text-sm text-autobot-text-secondary">{{ trace.span_count }}</td>
              <td class="px-4 py-2">
                <span
                  :class="['px-2 py-0.5 text-xs font-medium rounded-full', statusBadgeClass(trace.status)]"
                >
                  {{ trace.status }}
                </span>
              </td>
              <td class="px-4 py-2 text-sm text-autobot-text-tertiary">
                {{ trace.source_node_id ?? '-' }}
              </td>
              <td class="px-4 py-2 text-sm text-autobot-text-tertiary whitespace-nowrap">
                {{ formatFleetDateTime(trace.created_at) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
