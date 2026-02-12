<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * ServiceStatusBadge - Service status display component (Issue #850 Phase 2)
 *
 * Displays service status with colored dot and text.
 * Used across orchestration views for consistent status display.
 */

import { computed } from 'vue'

interface Props {
  status: string
  size?: 'sm' | 'md' | 'lg'
  showText?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  showText: true,
})

const statusClasses = computed(() => {
  const baseClasses = {
    dot: 'rounded-full',
    text: 'capitalize',
  }

  const sizeClasses = {
    sm: { dot: 'w-1.5 h-1.5', text: 'text-xs' },
    md: { dot: 'w-2 h-2', text: 'text-sm' },
    lg: { dot: 'w-2.5 h-2.5', text: 'text-base' },
  }

  const colorClasses: Record<string, { dot: string; text: string }> = {
    running: { dot: 'bg-green-500', text: 'text-green-600' },
    active: { dot: 'bg-green-500', text: 'text-green-600' },
    activating: { dot: 'bg-blue-500', text: 'text-blue-600' },
    online: { dot: 'bg-green-500', text: 'text-green-600' },
    stopped: { dot: 'bg-gray-400', text: 'text-gray-500' },
    inactive: { dot: 'bg-gray-400', text: 'text-gray-500' },
    deactivating: { dot: 'bg-orange-500', text: 'text-orange-600' },
    offline: { dot: 'bg-gray-500', text: 'text-gray-600' },
    failed: { dot: 'bg-red-500', text: 'text-red-600' },
    error: { dot: 'bg-red-500', text: 'text-red-600' },
    unknown: { dot: 'bg-yellow-500', text: 'text-yellow-600' },
    healthy: { dot: 'bg-green-500', text: 'text-green-600' },
    unhealthy: { dot: 'bg-red-500', text: 'text-red-600' },
    degraded: { dot: 'bg-yellow-500', text: 'text-yellow-600' },
    maintenance: { dot: 'bg-purple-500', text: 'text-purple-600' },
  }

  // Fallback for unknown status values
  const defaultColors = { dot: 'bg-gray-400', text: 'text-gray-500' }
  const colors = colorClasses[props.status.toLowerCase()] || defaultColors

  return {
    dot: `${baseClasses.dot} ${sizeClasses[props.size].dot} ${colors.dot}`,
    text: `${baseClasses.text} ${sizeClasses[props.size].text} ${colors.text}`,
  }
})
</script>

<template>
  <div class="flex items-center gap-1.5">
    <span :class="statusClasses.dot"></span>
    <span v-if="showText" :class="statusClasses.text">
      {{ status }}
    </span>
  </div>
</template>
