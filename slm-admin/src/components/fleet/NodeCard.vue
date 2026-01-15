<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import type { SLMNode } from '@/types/slm'

const props = defineProps<{
  node: SLMNode
}>()

const emit = defineEmits<{
  (e: 'action', action: string, nodeId: string): void
}>()

const statusClass = computed(() => {
  switch (props.node.status) {
    case 'healthy': return 'bg-success-500'
    case 'degraded': return 'bg-warning-500'
    case 'unhealthy': return 'bg-danger-500'
    default: return 'bg-gray-400'
  }
})

const statusText = computed(() => {
  return props.node.status.charAt(0).toUpperCase() + props.node.status.slice(1)
})

const lastSeen = computed(() => {
  if (!props.node.health?.last_heartbeat) return 'Never'
  const date = new Date(props.node.health.last_heartbeat)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  return `${diffHr}h ago`
})

function handleAction(action: string): void {
  emit('action', action, props.node.node_id)
}
</script>

<template>
  <div class="card p-4 hover:shadow-md transition-shadow">
    <!-- Header -->
    <div class="flex items-start justify-between mb-3">
      <div class="flex items-center gap-2">
        <div :class="['w-3 h-3 rounded-full', statusClass]"></div>
        <span class="font-medium text-gray-900 truncate">{{ node.hostname }}</span>
      </div>
      <span class="text-xs text-gray-500">{{ statusText }}</span>
    </div>

    <!-- IP Address -->
    <div class="text-sm text-gray-500 mb-3">
      {{ node.ip_address }}
    </div>

    <!-- Roles -->
    <div class="flex flex-wrap gap-1 mb-3">
      <span
        v-for="role in node.roles"
        :key="role"
        class="px-2 py-0.5 text-xs font-medium bg-primary-100 text-primary-700 rounded"
      >
        {{ role }}
      </span>
    </div>

    <!-- Health Metrics -->
    <div v-if="node.health" class="space-y-2 mb-3">
      <!-- CPU -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gray-500">CPU</span>
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all',
              node.health.cpu_percent > 80 ? 'bg-danger-500' :
              node.health.cpu_percent > 60 ? 'bg-warning-500' : 'bg-success-500'
            ]"
            :style="{ width: `${node.health.cpu_percent}%` }"
          ></div>
        </div>
        <span class="w-8 text-right text-gray-600">{{ node.health.cpu_percent?.toFixed(0) || 0 }}%</span>
      </div>

      <!-- Memory -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gray-500">MEM</span>
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all',
              node.health.memory_percent > 80 ? 'bg-danger-500' :
              node.health.memory_percent > 60 ? 'bg-warning-500' : 'bg-success-500'
            ]"
            :style="{ width: `${node.health.memory_percent}%` }"
          ></div>
        </div>
        <span class="w-8 text-right text-gray-600">{{ node.health.memory_percent?.toFixed(0) || 0 }}%</span>
      </div>

      <!-- Disk -->
      <div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gray-500">DISK</span>
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all',
              node.health.disk_percent > 80 ? 'bg-danger-500' :
              node.health.disk_percent > 60 ? 'bg-warning-500' : 'bg-success-500'
            ]"
            :style="{ width: `${node.health.disk_percent}%` }"
          ></div>
        </div>
        <span class="w-8 text-right text-gray-600">{{ node.health.disk_percent?.toFixed(0) || 0 }}%</span>
      </div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between pt-3 border-t border-gray-100">
      <span class="text-xs text-gray-400">Last seen: {{ lastSeen }}</span>
      <div class="flex gap-1">
        <button
          @click="handleAction('view')"
          class="p-1 text-gray-400 hover:text-primary-600 transition-colors"
          title="View details"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </button>
        <button
          @click="handleAction('restart')"
          class="p-1 text-gray-400 hover:text-warning-500 transition-colors"
          title="Restart services"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
