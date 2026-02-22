<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeHealthCard - Node status summary card (Issue #850 Phase 2)
 *
 * Displays node health with service counts and status indicators.
 * Used across orchestration views for consistent node status display.
 */


interface Props {
  nodeId: string
  hostname: string
  ipAddress?: string
  status: 'online' | 'offline' | 'unknown'
  runningCount: number
  stoppedCount: number
  failedCount: number
  totalServices: number
  isExpanded?: boolean
  showExpandIcon?: boolean
  showRestartButton?: boolean
  isRestartingAll?: boolean
  restartProgress?: { total: number; completed: number } | null
}

withDefaults(defineProps<Props>(), {
  ipAddress: '',
  isExpanded: false,
  showExpandIcon: true,
  showRestartButton: false,
  isRestartingAll: false,
  restartProgress: null,
})

const emit = defineEmits<{
  toggle: [nodeId: string]
  restartAll: [nodeId: string, hostname: string]
}>()

</script>

<template>
  <button
    @click="emit('toggle', nodeId)"
    class="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
    :class="{ 'cursor-default': !showExpandIcon }"
  >
    <div class="flex items-center gap-4">
      <!-- Expand/Collapse Icon -->
      <svg
        v-if="showExpandIcon"
        :class="[
          'w-5 h-5 text-gray-400 transition-transform',
          isExpanded ? 'rotate-90' : ''
        ]"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>

      <!-- Node Info -->
      <div class="text-left">
        <div class="flex items-center gap-2">
          <span class="font-semibold text-gray-900">{{ hostname }}</span>
          <span v-if="ipAddress" class="text-sm text-gray-500">({{ ipAddress }})</span>
        </div>
        <div class="text-sm text-gray-500">
          {{ totalServices }} service{{ totalServices !== 1 ? 's' : '' }}
        </div>
      </div>
    </div>

    <!-- Status Summary and Actions -->
    <div class="flex items-center gap-4">
      <!-- Running Count -->
      <div v-if="runningCount > 0" class="flex items-center gap-1.5 text-sm">
        <span class="w-2 h-2 rounded-full bg-green-500"></span>
        <span class="text-green-600">{{ runningCount }}</span>
      </div>

      <!-- Stopped Count -->
      <div v-if="stoppedCount > 0" class="flex items-center gap-1.5 text-sm">
        <span class="w-2 h-2 rounded-full bg-gray-400"></span>
        <span class="text-gray-500">{{ stoppedCount }}</span>
      </div>

      <!-- Failed Count -->
      <div v-if="failedCount > 0" class="flex items-center gap-1.5 text-sm">
        <span class="w-2 h-2 rounded-full bg-red-500"></span>
        <span class="text-red-600">{{ failedCount }}</span>
      </div>

      <!-- Restart All Button -->
      <button
        v-if="showRestartButton"
        @click.stop="emit('restartAll', nodeId, hostname)"
        :disabled="isRestartingAll"
        class="px-2.5 py-1 text-xs font-medium text-orange-600 bg-orange-50 border border-orange-200 rounded hover:bg-orange-100 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
        title="Restart all services on this node"
      >
        <svg
          v-if="isRestartingAll"
          class="w-3.5 h-3.5 animate-spin"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        <span v-if="isRestartingAll && restartProgress">
          {{ restartProgress.completed }}/{{ restartProgress.total }}
        </span>
        <span v-else>Restart All</span>
      </button>
    </div>
  </button>
</template>
