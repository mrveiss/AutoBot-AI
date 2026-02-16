<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * FleetMetricsCard - Aggregate fleet metrics summary
 * Issue #896 - SLM Metrics Dashboard
 */

import { computed } from 'vue'
import type { FleetMetricsDetailed } from '@/composables/usePrometheusMetrics'

interface Props {
  metrics: FleetMetricsDetailed | null
  loading?: boolean
}

const props = defineProps<Props>()

const healthPercentage = computed(() => {
  if (!props.metrics || props.metrics.total_nodes === 0) return 0
  return Math.round((props.metrics.online_nodes / props.metrics.total_nodes) * 100)
})

const healthColor = computed(() => {
  const pct = healthPercentage.value
  if (pct >= 90) return 'text-success-600'
  if (pct >= 70) return 'text-warning-600'
  return 'text-danger-600'
})

function getMetricColor(value: number): string {
  if (value >= 90) return 'text-danger-600'
  if (value >= 70) return 'text-warning-600'
  return 'text-success-600'
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString()
}
</script>

<template>
  <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h3 class="text-lg font-semibold text-gray-900">Fleet Metrics Summary</h3>
      <div v-if="metrics" class="text-sm text-gray-500">
        Updated: {{ formatTimestamp(metrics.timestamp) }}
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-8">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
    </div>

    <div v-else-if="!metrics" class="text-center py-8 text-gray-500">
      No fleet metrics available
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <!-- Fleet Health -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-gray-500">Fleet Health</div>
        <div :class="['text-3xl font-bold', healthColor]">
          {{ healthPercentage }}%
        </div>
        <div class="text-xs text-gray-600">
          {{ metrics.online_nodes }}/{{ metrics.total_nodes }} nodes online
        </div>
      </div>

      <!-- CPU Usage -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-gray-500">Avg CPU Usage</div>
        <div :class="['text-3xl font-bold', getMetricColor(metrics.avg_cpu_percent)]">
          {{ metrics.avg_cpu_percent.toFixed(1) }}%
        </div>
        <div class="text-xs text-gray-600">
          Across {{ metrics.total_nodes }} nodes
        </div>
      </div>

      <!-- Memory Usage -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-gray-500">Avg Memory Usage</div>
        <div :class="['text-3xl font-bold', getMetricColor(metrics.avg_memory_percent)]">
          {{ metrics.avg_memory_percent.toFixed(1) }}%
        </div>
        <div class="text-xs text-gray-600">
          Across {{ metrics.total_nodes }} nodes
        </div>
      </div>

      <!-- Services -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-gray-500">Services</div>
        <div class="text-3xl font-bold text-gray-900">
          {{ metrics.running_services }}/{{ metrics.total_services }}
        </div>
        <div class="text-xs text-gray-600">
          <span v-if="metrics.failed_services > 0" class="text-danger-600">
            {{ metrics.failed_services }} failed
          </span>
          <span v-else class="text-success-600">All healthy</span>
        </div>
      </div>
    </div>

    <!-- Status Breakdown -->
    <div v-if="metrics" class="mt-6 pt-6 border-t border-gray-200">
      <div class="grid grid-cols-3 gap-4 text-center">
        <div>
          <div class="text-2xl font-bold text-success-600">{{ metrics.online_nodes }}</div>
          <div class="text-xs text-gray-500">Online</div>
        </div>
        <div>
          <div class="text-2xl font-bold text-warning-600">{{ metrics.degraded_nodes }}</div>
          <div class="text-xs text-gray-500">Degraded</div>
        </div>
        <div>
          <div class="text-2xl font-bold text-gray-400">{{ metrics.offline_nodes }}</div>
          <div class="text-xs text-gray-500">Offline</div>
        </div>
      </div>
    </div>
  </div>
</template>
