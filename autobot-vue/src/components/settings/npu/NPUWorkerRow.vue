<template>
  <tr :class="rowClass">
    <!-- Worker Name & ID -->
    <td>
      <div class="worker-info">
        <div class="worker-name">{{ worker.name }}</div>
        <div class="worker-id">{{ worker.id }}</div>
      </div>
    </td>

    <!-- Platform -->
    <td>
      <div class="platform-badge" :class="platformClass">
        <i :class="platformIcon" class="mr-1"></i>
        {{ worker.platform }}
      </div>
    </td>

    <!-- Connection -->
    <td>
      <div class="connection-info">
        <div class="text-sm font-mono">{{ worker.ip_address }}:{{ worker.port }}</div>
        <div class="text-xs text-gray-500">{{ worker.last_heartbeat }}</div>
      </div>
    </td>

    <!-- Status -->
    <td>
      <StatusBadge :variant="statusVariant" size="small">
        <span class="status-dot" :class="statusDotClass"></span>
        {{ worker.status }}
      </StatusBadge>
    </td>

    <!-- Load -->
    <td>
      <div class="load-info">
        <div class="load-bar-container">
          <div
            class="load-bar"
            :class="loadBarClass"
            :style="{ width: worker.current_load + '%' }"
          ></div>
        </div>
        <div class="load-text">{{ worker.current_load }}% / {{ worker.max_capacity }}</div>
      </div>
    </td>

    <!-- Uptime -->
    <td>
      <div class="uptime-info">{{ worker.uptime }}</div>
    </td>

    <!-- Priority & Weight -->
    <td>
      <div class="priority-info">
        <div class="text-sm">P: {{ worker.priority }}</div>
        <div class="text-xs text-gray-500">W: {{ worker.weight }}</div>
      </div>
    </td>

    <!-- Actions -->
    <td>
      <div class="action-buttons">
        <button
          @click="$emit('test', worker)"
          :disabled="isTesting"
          class="action-btn test-btn"
          :title="'Test connection to ' + worker.name"
        >
          <i :class="isTesting ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
        </button>
        <button
          @click="$emit('metrics', worker)"
          class="action-btn metrics-btn"
          title="View detailed metrics"
        >
          <i class="fas fa-chart-line"></i>
        </button>
        <button
          @click="$emit('edit', worker)"
          class="action-btn edit-btn"
          title="Edit worker configuration"
        >
          <i class="fas fa-edit"></i>
        </button>
        <button
          @click="$emit('delete', worker)"
          class="action-btn delete-btn"
          title="Remove worker"
        >
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * NPU Worker Row Component
 *
 * Displays a single worker row in the NPU workers table.
 * Extracted from NPUWorkersSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

interface NPUWorker {
  id: string
  name: string
  platform: string
  ip_address: string
  port: number
  status: string
  current_load: number
  max_capacity: number
  priority: number
  weight: number
  uptime: string
  last_heartbeat: string
}

interface Props {
  worker: NPUWorker
  isTesting?: boolean
}

interface Emits {
  (e: 'test', worker: NPUWorker): void
  (e: 'metrics', worker: NPUWorker): void
  (e: 'edit', worker: NPUWorker): void
  (e: 'delete', worker: NPUWorker): void
}

const props = withDefaults(defineProps<Props>(), {
  isTesting: false
})

defineEmits<Emits>()

// Computed styling helpers
const platformIcon = computed(() => {
  const icons: Record<string, string> = {
    linux: 'fab fa-linux',
    windows: 'fab fa-windows',
    macos: 'fab fa-apple'
  }
  return icons[props.worker.platform] || 'fas fa-server'
})

const platformClass = computed(() => {
  const classes: Record<string, string> = {
    linux: 'platform-linux',
    windows: 'platform-windows',
    macos: 'platform-macos'
  }
  return classes[props.worker.platform] || ''
})

const statusVariant = computed((): 'success' | 'danger' | 'warning' | 'secondary' => {
  const variants: Record<string, 'success' | 'danger' | 'warning' | 'secondary'> = {
    online: 'success',
    offline: 'danger',
    busy: 'warning',
    idle: 'secondary'
  }
  return variants[props.worker.status] || 'secondary'
})

const statusDotClass = computed(() => {
  const classes: Record<string, string> = {
    online: 'dot-online',
    offline: 'dot-offline',
    busy: 'dot-busy',
    idle: 'dot-idle'
  }
  return classes[props.worker.status] || ''
})

const loadBarClass = computed(() => {
  const load = props.worker.current_load
  if (load >= 90) return 'load-critical'
  if (load >= 70) return 'load-high'
  if (load >= 40) return 'load-medium'
  return 'load-low'
})

const rowClass = computed(() => {
  return {
    'worker-row': true,
    'worker-offline': props.worker.status === 'offline',
    'worker-busy': props.worker.status === 'busy'
  }
})
</script>

<style scoped>
.worker-row {
  @apply transition-colors duration-200;
}

.worker-row:hover {
  @apply bg-gray-50;
}

.worker-offline {
  @apply opacity-60;
}

.worker-busy {
  @apply bg-yellow-50;
}

.worker-info {
  @apply flex flex-col;
}

.worker-name {
  @apply font-medium text-gray-900;
}

.worker-id {
  @apply text-xs text-gray-500 font-mono;
}

.platform-badge {
  @apply inline-flex items-center px-2 py-1 rounded text-xs font-medium;
}

.platform-linux {
  @apply bg-orange-100 text-orange-800;
}

.platform-windows {
  @apply bg-blue-100 text-blue-800;
}

.platform-macos {
  @apply bg-gray-100 text-gray-800;
}

.connection-info {
  @apply flex flex-col;
}

.status-dot {
  @apply w-2 h-2 rounded-full mr-1.5;
}

.dot-online {
  @apply bg-green-500;
}

.dot-offline {
  @apply bg-red-500;
}

.dot-busy {
  @apply bg-yellow-500;
}

.dot-idle {
  @apply bg-gray-400;
}

.load-info {
  @apply flex flex-col gap-1;
}

.load-bar-container {
  @apply w-24 h-2 bg-gray-200 rounded-full overflow-hidden;
}

.load-bar {
  @apply h-full rounded-full transition-all duration-300;
}

.load-low {
  @apply bg-green-500;
}

.load-medium {
  @apply bg-yellow-500;
}

.load-high {
  @apply bg-orange-500;
}

.load-critical {
  @apply bg-red-500;
}

.load-text {
  @apply text-xs text-gray-500;
}

.uptime-info {
  @apply text-sm text-gray-600;
}

.priority-info {
  @apply flex flex-col;
}

.action-buttons {
  @apply flex gap-1;
}

.action-btn {
  @apply p-1.5 rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed;
}

.test-btn:hover:not(:disabled) {
  @apply text-blue-600 bg-blue-50;
}

.metrics-btn:hover {
  @apply text-purple-600 bg-purple-50;
}

.edit-btn:hover {
  @apply text-green-600 bg-green-50;
}

.delete-btn:hover {
  @apply text-red-600 bg-red-50;
}
</style>
