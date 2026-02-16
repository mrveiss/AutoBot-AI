<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeMetricsGrid - Detailed per-node metrics table
 * Issue #896 - SLM Metrics Dashboard
 */

import { ref, computed } from 'vue'
import type { NodeMetricsDetailed } from '@/composables/usePrometheusMetrics'

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
    case 'unhealthy': return 'bg-gray-100 text-gray-800'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function getMetricColor(value: number): string {
  if (value >= 90) return 'text-danger-600 font-semibold'
  if (value >= 70) return 'text-warning-600'
  return 'text-gray-900'
}

function getSortIcon(key: SortKey): string {
  if (sortKey.value !== key) return '↕'
  return sortOrder.value === 'asc' ? '↑' : '↓'
}
</script>

<template>
  <div class="bg-white rounded-lg shadow-sm border border-gray-200">
    <!-- Header -->
    <div class="px-6 py-4 border-b border-gray-200">
      <h3 class="text-lg font-semibold text-gray-900">Node Metrics</h3>
      <p class="text-sm text-gray-500 mt-1">Click column headers to sort</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
    </div>

    <div v-else-if="!nodes || nodes.length === 0" class="text-center py-12 text-gray-500">
      No node metrics available
    </div>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th
              @click="toggleSort('hostname')"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            >
              Node {{ getSortIcon('hostname') }}
            </th>
            <th
              @click="toggleSort('status')"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            >
              Status {{ getSortIcon('status') }}
            </th>
            <th
              @click="toggleSort('cpu_percent')"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            >
              CPU {{ getSortIcon('cpu_percent') }}
            </th>
            <th
              @click="toggleSort('memory_percent')"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            >
              Memory {{ getSortIcon('memory_percent') }}
            </th>
            <th
              @click="toggleSort('disk_percent')"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            >
              Disk {{ getSortIcon('disk_percent') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Services
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Last Heartbeat
            </th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr
            v-for="node in sortedNodes"
            :key="node.node_id"
            @click="emit('selectNode', node.node_id)"
            class="hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm font-medium text-gray-900">{{ node.hostname }}</div>
              <div class="text-xs text-gray-500">{{ node.ip_address }}</div>
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
              <div class="text-sm text-gray-900">
                {{ node.services_running }} / {{ node.services_running + node.services_failed }}
              </div>
              <div v-if="node.services_failed > 0" class="text-xs text-danger-600">
                {{ node.services_failed }} failed
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              <span v-if="node.last_heartbeat">
                {{ new Date(node.last_heartbeat).toLocaleString() }}
              </span>
              <span v-else class="text-gray-400">No data</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
