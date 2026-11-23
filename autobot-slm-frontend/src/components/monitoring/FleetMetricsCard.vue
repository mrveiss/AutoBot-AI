<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * FleetMetricsCard - Aggregate fleet metrics summary
 * Issue #896 - SLM Metrics Dashboard
 */

import { computed } from 'vue'
import type { FleetMetricsDetailed } from '@/composables/useFleetMetrics'
import { createDateFormatter } from '@autobot/ui'

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
  return 'text-error-600'
})

function getMetricColor(value: number): string {
  if (value >= 90) return 'text-error-600'
  if (value >= 70) return 'text-warning-600'
  return 'text-success-600'
}

const formatTimestamp = createDateFormatter({ kind: 'time' })
</script>

<template>
  <div class="bg-white rounded-lg shadow-xs border border-autobot-border p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('monitoring.fleetMetricsCard.fleetMetricsSummary') }}</h3>
      <div v-if="metrics" class="text-sm text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.updatedValue0', { value0: formatTimestamp(metrics.timestamp) }) }}</div>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-8">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
    </div>

    <div v-else-if="!metrics" class="text-center py-8 text-autobot-text-tertiary">
      {{ $t('monitoring.fleetMetricsCard.noFleetMetricsAvailable') }}
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <!-- Fleet Health -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.fleetHealth') }}</div>
        <div :class="['text-3xl font-bold', healthColor]">
          {{ healthPercentage }}%
        </div>
        <div class="text-xs text-autobot-text-secondary">{{ $t('monitoring.fleetMetricsCard.value0Value1NodesOnline', { value0: metrics.online_nodes, value1: metrics.total_nodes }) }}</div>
      </div>

      <!-- CPU Usage -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.avgCPUUsage') }}</div>
        <div :class="['text-3xl font-bold', getMetricColor(metrics.avg_cpu_percent)]">
          {{ metrics.avg_cpu_percent.toFixed(1) }}%
        </div>
        <div class="text-xs text-autobot-text-secondary">{{ $t('monitoring.fleetMetricsCard.acrossValue0Nodes', { value0: metrics.total_nodes }) }}</div>
      </div>

      <!-- Memory Usage -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.avgMemoryUsage') }}</div>
        <div :class="['text-3xl font-bold', getMetricColor(metrics.avg_memory_percent)]">
          {{ metrics.avg_memory_percent.toFixed(1) }}%
        </div>
        <div class="text-xs text-autobot-text-secondary">{{ $t('monitoring.fleetMetricsCard.acrossValue0Nodes', { value0: metrics.total_nodes }) }}</div>
      </div>

      <!-- Services -->
      <div class="space-y-2">
        <div class="text-sm font-medium text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.services') }}</div>
        <div class="text-3xl font-bold text-autobot-text-primary">
          {{ metrics.running_services }}/{{ metrics.total_services }}
        </div>
        <div class="text-xs text-autobot-text-secondary">
          <span v-if="metrics.failed_services > 0" class="text-error-600">{{ $t('monitoring.fleetMetricsCard.value0Failed', { value0: metrics.failed_services }) }}</span>
          <span v-else class="text-success-600">{{ $t('monitoring.fleetMetricsCard.allHealthy') }}</span>
        </div>
      </div>
    </div>

    <!-- Status Breakdown -->
    <div v-if="metrics" class="mt-6 pt-6 border-t border-autobot-border">
      <div class="grid grid-cols-3 gap-4 text-center">
        <div>
          <div class="text-2xl font-bold text-success-600">{{ metrics.online_nodes }}</div>
          <div class="text-xs text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.online') }}</div>
        </div>
        <div>
          <div class="text-2xl font-bold text-warning-600">{{ metrics.degraded_nodes }}</div>
          <div class="text-xs text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.degraded') }}</div>
        </div>
        <div>
          <div class="text-2xl font-bold text-autobot-text-tertiary">{{ metrics.offline_nodes }}</div>
          <div class="text-xs text-autobot-text-tertiary">{{ $t('monitoring.fleetMetricsCard.offline') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
