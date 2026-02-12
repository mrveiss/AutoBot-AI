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
  status: 'running' | 'stopped' | 'failed' | 'unknown' | 'healthy' | 'unhealthy'
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

  const colorClasses = {
    running: { dot: 'bg-green-500', text: 'text-green-600' },
    stopped: { dot: 'bg-gray-400', text: 'text-gray-500' },
    failed: { dot: 'bg-red-500', text: 'text-red-600' },
    unknown: { dot: 'bg-yellow-500', text: 'text-yellow-600' },
    healthy: { dot: 'bg-green-500', text: 'text-green-600' },
    unhealthy: { dot: 'bg-red-500', text: 'text-red-600' },
  }

  return {
    dot: `${baseClasses.dot} ${sizeClasses[props.size].dot} ${colorClasses[props.status].dot}`,
    text: `${baseClasses.text} ${sizeClasses[props.size].text} ${colorClasses[props.status].text}`,
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
