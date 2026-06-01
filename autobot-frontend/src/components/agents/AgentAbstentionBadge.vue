<template>
  <div
    v-if="task.abstained || task.status === 'abstained'"
    class="abstention-badge"
    :class="{ 'with-tooltip': showTooltip }"
    :title="tooltipText"
  >
    <Icon name="help-circle" class="abstention-icon" />
    <span class="abstention-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import type { AgentTask } from '@/types/models'

/**
 * Agent Abstention Badge Component (GH#6626)
 *
 * Displays a warning badge when an agent abstains from a task due to
 * low confidence. Visually distinct from error/success states.
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

interface Props {
  task: AgentTask
  label?: string
  showTooltip?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: 'Abstained',
  showTooltip: true,
})

const tooltipText = computed(() => {
  if (!props.showTooltip) return ''
  return props.task.abstention_reason || 'Agent could not confidently complete this task'
})
</script>

<style scoped>
.abstention-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  background-color: oklch(0.95 0.03 85); /* Warm yellow background */
  border: 1px solid oklch(0.75 0.12 85); /* Darker yellow border */
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: oklch(0.4 0.12 85); /* Dark yellow text */
  cursor: help;
}

.abstention-badge.with-tooltip:hover {
  background-color: oklch(0.92 0.05 85);
}

.abstention-icon {
  width: 1rem;
  height: 1rem;
  color: oklch(0.5 0.15 85);
}

.abstention-label {
  line-height: 1;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .abstention-badge {
    background-color: oklch(0.3 0.08 85);
    border-color: oklch(0.5 0.12 85);
    color: oklch(0.85 0.1 85);
  }

  .abstention-badge.with-tooltip:hover {
    background-color: oklch(0.35 0.1 85);
  }

  .abstention-icon {
    color: oklch(0.75 0.12 85);
  }
}
</style>
