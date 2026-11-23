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
    running: { dot: 'bg-autobot-dot-ok', text: 'text-autobot-success' },
    active: { dot: 'bg-autobot-dot-ok', text: 'text-autobot-success' },
    activating: { dot: 'bg-autobot-primary', text: 'text-autobot-text-link' },
    online: { dot: 'bg-autobot-dot-ok', text: 'text-autobot-success' },
    stopped: { dot: 'bg-autobot-dot-idle', text: 'text-autobot-text-tertiary' },
    inactive: { dot: 'bg-autobot-dot-idle', text: 'text-autobot-text-tertiary' },
    deactivating: { dot: 'bg-autobot-primary', text: 'text-autobot-warning' },
    offline: { dot: 'bg-autobot-text-tertiary', text: 'text-autobot-text-secondary' },
    failed: { dot: 'bg-autobot-dot-bad', text: 'text-autobot-error' },
    error: { dot: 'bg-autobot-dot-bad', text: 'text-autobot-error' },
    unknown: { dot: 'bg-autobot-dot-warn', text: 'text-autobot-warning' },
    healthy: { dot: 'bg-autobot-dot-ok', text: 'text-autobot-success' },
    unhealthy: { dot: 'bg-autobot-dot-bad', text: 'text-autobot-error' },
    degraded: { dot: 'bg-autobot-dot-warn', text: 'text-autobot-warning' },
    maintenance: { dot: 'bg-autobot-primary', text: 'text-autobot-text-primary' },
  }

  // Fallback for unknown status values
  const defaultColors = { dot: 'bg-autobot-dot-idle', text: 'text-autobot-text-tertiary' }
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
