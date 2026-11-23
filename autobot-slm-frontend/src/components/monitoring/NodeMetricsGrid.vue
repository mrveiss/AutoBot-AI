<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeMetricsGrid - Detailed per-node metrics table
 * Issue #896 - SLM Metrics Dashboard
 */

import { ref, computed } from 'vue'
import type { NodeMetricsDetailed } from '@/composables/useFleetMetrics'
import { formatFleetDateTime } from '@/composables/useTimezone'

interface Props {
  nodes: NodeMetricsDetailed[]
  loading?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  selectNode: [nodeId: string]
}>()

type SortKey = 'hostname' | 'cpu_percent' | 'memory_percent' | 'disk_percent' | 'status'
type SortOrder = 'asc' | 'desc'

const sortKey = ref<SortKey>('hostname')
const sortOrder = ref<SortOrder>('asc')

const sortedNodes = computed(() => {
  if (!props.nodes) return []

  const sorted = [...props.nodes].sort((a, b) => {
    let aVal: string | number = a[sortKey.value]
    let bVal: string | number = b[sortKey.value]

    if (sortKey.value === 'hostname' || sortKey.value === 'status') {
      aVal = String(aVal).toLowerCase()
      bVal = String(bVal).toLowerCase()
      return sortOrder.value === 'asc'
        ? aVal < bVal ? -1 : 1
        : aVal > bVal ? -1 : 1
    }

    return sortOrder.value === 'asc'
      ? Number(aVal) - Number(bVal)
      : Number(bVal) - Number(aVal)
  })

  return sorted
})

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
}

function getStatusColor(status: string): string {
  switch (status.toLowerCase()) {
    case 'online':
    case 'healthy': return 'bg-success-100 text-success-800'
    case 'degraded': return 'bg-warning-100 text-warning-800'
    case 'offline':
    case 'unhealthy': return 'bg-autobot-bg-tertiary text-autobot-text-primary'
    default: return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
  }
}

function getMetricColor(value: number): string {
  if (value >= 90) return 'text-error-600 font-semibold'
  if (value >= 70) return 'text-warning-600'
  return 'text-autobot-text-primary'
}

function getSortIcon(key: SortKey): string {
  if (sortKey.value !== key) return '↕'
  return sortOrder.value === 'asc' ? '↑' : '↓'
}
</script>

<template>
  <div class="bg-white rounded-lg shadow-xs border border-autobot-border">
    <!-- Header -->
    <div class="px-6 py-4 border-b border-autobot-border">
      <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('monitoring.nodeMetricsGrid.nodeMetrics') }}</h3>
      <p class="text-sm text-autobot-text-tertiary mt-1">{{ $t('monitoring.nodeMetricsGrid.clickColumnHeadersTo') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
    </div>

    <div v-else-if="!nodes || nodes.length === 0" class="text-center py-12 text-autobot-text-tertiary">
      {{ $t('monitoring.nodeMetricsGrid.noNodeMetricsAvailable') }}
    </div>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-autobot-border">
        <thead class="bg-autobot-bg-secondary">
          <tr>
            <th
              @click="toggleSort('hostname')"
              class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider cursor-pointer hover:bg-autobot-bg-hover"
            >{{ $t('monitoring.nodeMetricsGrid.nodeHostname', { hostname: getSortIcon('hostname') }) }}</th>
            <th
              @click="toggleSort('status')"
              class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider cursor-pointer hover:bg-autobot-bg-hover"
            >{{ $t('monitoring.nodeMetricsGrid.statusStatus', { status: getSortIcon('status') }) }}</th>
            <th
              @click="toggleSort('cpu_percent')"
              class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider cursor-pointer hover:bg-autobot-bg-hover"
            >{{ $t('monitoring.nodeMetricsGrid.cPUValue0', { value0: getSortIcon('cpu_percent') }) }}</th>
            <th
              @click="toggleSort('memory_percent')"
              class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider cursor-pointer hover:bg-autobot-bg-hover"
            >{{ $t('monitoring.nodeMetricsGrid.memoryValue0', { value0: getSortIcon('memory_percent') }) }}</th>
            <th
              @click="toggleSort('disk_percent')"
              class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider cursor-pointer hover:bg-autobot-bg-hover"
            >{{ $t('monitoring.nodeMetricsGrid.diskValue0', { value0: getSortIcon('disk_percent') }) }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider">
              {{ $t('monitoring.nodeMetricsGrid.services') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-autobot-text-tertiary uppercase tracking-wider">
              {{ $t('monitoring.nodeMetricsGrid.lastHeartbeat') }}
            </th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-autobot-border">
          <tr
            v-for="node in sortedNodes"
            :key="node.node_id"
            @click="emit('selectNode', node.node_id)"
            class="hover:bg-autobot-bg-hover cursor-pointer transition-colors"
          >
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm font-medium text-autobot-text-primary">{{ node.hostname }}</div>
              <div class="text-xs text-autobot-text-tertiary">{{ node.ip_address }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusColor(node.status)]">
                {{ node.status }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div :class="['text-sm', getMetricColor(node.cpu_percent)]">
                {{ node.cpu_percent.toFixed(1) }}%
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div :class="['text-sm', getMetricColor(node.memory_percent)]">
                {{ node.memory_percent.toFixed(1) }}%
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div :class="['text-sm', getMetricColor(node.disk_percent)]">
                {{ node.disk_percent.toFixed(1) }}%
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm text-autobot-text-primary">
                {{ node.services_running }} / {{ node.services_running + node.services_failed }}
              </div>
              <div v-if="node.services_failed > 0" class="text-xs text-error-600">{{ $t('monitoring.nodeMetricsGrid.value0Failed', { value0: node.services_failed }) }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-autobot-text-tertiary">
              <span v-if="node.last_heartbeat">
                {{ formatFleetDateTime(node.last_heartbeat) }}
              </span>
              <span v-else class="text-autobot-text-tertiary">{{ $t('monitoring.nodeMetricsGrid.noData') }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
