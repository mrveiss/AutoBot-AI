<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * PerformanceView - Layout wrapper for performance monitoring subsections
 *
 * Provides navigation tabs for performance sub-routes and displays
 * the active sub-view via router-view.
 * Issue #752 - Comprehensive performance monitoring.
 *
 * Issue #754: Added ARIA tablist/tab roles, aria-selected,
 * accessible status indicators and labels.
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TabbedRouteLayout from '@/components/common/TabbedRouteLayout.vue'
import { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'
import { providePerformanceMonitoring } from '@/composables/monitoringPollContext'

const { t } = useI18n()

// #19851: this layout owns the route's one performance poll; child routes read it
const performance = usePerformanceMonitoring({
  autoFetch: true,
  pollInterval: 30000,
})
providePerformanceMonitoring(performance)
const { overview, loading, poller } = performance

// Navigation tabs for performance sub-routes (Issue #752)
const tabs = computed(() => [
  {
    id: 'overview',
    label: t('performanceView.tabs.overview'),
    path: '/monitoring/performance/overview',
    icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1',
  },
  {
    id: 'traces',
    label: t('performanceView.tabs.traces'),
    path: '/monitoring/performance/traces',
    icon: 'M13 10V3L4 14h7v7l9-11h-7z',
  },
  {
    id: 'slos',
    label: t('performanceView.tabs.slos'),
    path: '/monitoring/performance/slos',
    icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  {
    id: 'alerts',
    label: t('performanceView.tabs.alertRules'),
    path: '/monitoring/performance/alerts',
    icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9',
  },
])

const avgLatency = computed(() => overview.value?.avg_latency_ms ?? 0)
const errorRate = computed(() => overview.value?.error_rate_percent ?? 0)
const sloCompliance = computed(() => overview.value?.slo_compliance_percent ?? 0)

/**
 * Determine health color class from SLO compliance.
 */
function complianceColor(): string {
  const pct = sloCompliance.value
  if (pct >= 99) return 'text-green-600'
  if (pct >= 95) return 'text-amber-600'
  return 'text-red-600'
}
</script>

<template>
  <TabbedRouteLayout
    :title="t('performanceView.performance')"
    :tabs-label="t('performanceView.performanceSections')"
    :tabs="tabs"
    default-tab="overview"
    nested
    :poller="poller"
  >
    <template #header-end>
      <!-- Quick Stats Bar -->
      <div class="flex items-center gap-6 text-sm" role="status" :aria-label="$t('performanceView.performanceSummary')">
        <div class="flex items-center gap-2 text-gray-600">
          <span class="text-gray-400">{{ $t('performanceView.avgLatency') }}</span>
          <span class="font-semibold">{{ avgLatency.toFixed(1) }}ms</span>
        </div>
        <div class="flex items-center gap-2 text-gray-600">
          <span class="text-gray-400">{{ $t('performanceView.errorRate') }}</span>
          <span
            :class="[
              'font-semibold',
              errorRate > 5 ? 'text-red-600' : errorRate > 1 ? 'text-amber-600' : 'text-green-600'
            ]"
          >
            {{ errorRate.toFixed(2) }}%
          </span>
        </div>
        <div class="flex items-center gap-2 text-gray-600">
          <span class="text-gray-400">{{ $t('performanceView.sLOCompliance') }}</span>
          <span :class="['font-semibold', complianceColor()]">
            {{ sloCompliance.toFixed(1) }}%
          </span>
        </div>
        <button
          @click="poller.start('')"
          :disabled="loading"
          class="p-1.5 text-gray-400 hover:text-gray-600 rounded-sm transition-colors"
          :aria-label="$t('performanceView.refreshPerformanceData')"
        >
          <svg
            :class="['w-4 h-4', loading ? 'animate-spin' : '']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>
    </template>
  </TabbedRouteLayout>
</template>
