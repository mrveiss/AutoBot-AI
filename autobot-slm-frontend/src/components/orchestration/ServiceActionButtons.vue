<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ServiceActionButtons - Service control buttons (Issue #850 Phase 2)
 *
 * Provides start/stop/restart buttons with loading states.
 * Used across orchestration views for consistent service control.
 */

interface Props {
  serviceName: string
  nodeId: string
  status: 'running' | 'stopped' | 'failed' | 'unknown'
  isActionInProgress?: boolean
  activeAction?: { nodeId: string; serviceName: string; action: string } | null
  size?: 'sm' | 'md'
}

const props = withDefaults(defineProps<Props>(), {
  isActionInProgress: false,
  activeAction: null,
  size: 'md',
})

const emit = defineEmits<{
  start: [nodeId: string, serviceName: string]
  stop: [nodeId: string, serviceName: string]
  restart: [nodeId: string, serviceName: string]
}>()

function isActiveAction(action: string): boolean {
  return (
    props.activeAction?.nodeId === props.nodeId &&
    props.activeAction?.serviceName === props.serviceName &&
    props.activeAction?.action === action
  )
}

const buttonSize = props.size === 'sm' ? 'p-0.5' : 'p-1'
const iconSize = props.size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4'
</script>

<template>
  <div class="flex items-center justify-end gap-1">
    <!-- Start Button -->
    <button
      v-if="status !== 'running'"
      @click.stop="emit('start', nodeId, serviceName)"
      :disabled="isActionInProgress"
      :class="`${buttonSize} text-green-600 hover:bg-green-50 rounded disabled:opacity-50`"
      title="Start service"
    >
      <svg
        v-if="isActiveAction('start')"
        :class="`${iconSize} animate-spin`"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <svg v-else :class="iconSize" fill="currentColor" viewBox="0 0 24 24">
        <path d="M8 5v14l11-7z" />
      </svg>
    </button>

    <!-- Stop Button -->
    <button
      v-if="status === 'running'"
      @click.stop="emit('stop', nodeId, serviceName)"
      :disabled="isActionInProgress"
      :class="`${buttonSize} text-red-600 hover:bg-red-50 rounded disabled:opacity-50`"
      title="Stop service"
    >
      <svg
        v-if="isActiveAction('stop')"
        :class="`${iconSize} animate-spin`"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <svg v-else :class="iconSize" fill="currentColor" viewBox="0 0 24 24">
        <rect x="6" y="6" width="12" height="12" />
      </svg>
    </button>

    <!-- Restart Button -->
    <button
      @click.stop="emit('restart', nodeId, serviceName)"
      :disabled="isActionInProgress"
      :class="`${buttonSize} text-blue-600 hover:bg-blue-50 rounded disabled:opacity-50`"
      title="Restart service"
    >
      <svg
        v-if="isActiveAction('restart')"
        :class="`${iconSize} animate-spin`"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <svg v-else :class="iconSize" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    </button>
  </div>
</template>
