<template>
  <span
    class="vectorization-badge"
    :class="badgeClass"
    :title="tooltipText"
  >
    <i :class="iconClass"></i>
    <span v-if="showLabel" class="badge-label">{{ labelText }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  status: 'vectorized' | 'pending' | 'failed' | 'unknown'
  showLabel?: boolean
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showLabel: false,
  compact: false
})

const badgeClass = computed(() => {
  const classes = ['vectorization-badge']

  if (props.compact) {
    classes.push('compact')
  }

  switch (props.status) {
    case 'vectorized':
      classes.push('status-vectorized')
      break
    case 'pending':
      classes.push('status-pending')
      break
    case 'failed':
      classes.push('status-failed')
      break
    default:
      classes.push('status-unknown')
  }

  return classes.join(' ')
})

const iconClass = computed(() => {
  switch (props.status) {
    case 'vectorized':
      return 'fas fa-check-circle'
    case 'pending':
      return 'fas fa-spinner fa-spin'
    case 'failed':
      return 'fas fa-times-circle'
    default:
      return 'fas fa-question-circle'
  }
})

const labelText = computed(() => {
  switch (props.status) {
    case 'vectorized':
      return 'Vectorized'
    case 'pending':
      return 'Pending'
    case 'failed':
      return 'Failed'
    default:
      return 'Unknown'
  }
})

const tooltipText = computed(() => {
  switch (props.status) {
    case 'vectorized':
      return 'Document has been vectorized and is available for semantic search'
    case 'pending':
      return 'Vectorization pending - document will be processed automatically'
    case 'failed':
      return 'Vectorization failed - click to retry'
    default:
      return 'Vectorization status unknown'
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.vectorization-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  transition: all var(--duration-200) var(--ease-in-out);
  cursor: default;
}

.vectorization-badge.compact {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  font-size: 0.6875rem;
}

.vectorization-badge i {
  font-size: var(--text-sm);
}

.vectorization-badge.compact i {
  font-size: var(--text-xs);
}

/* Vectorized status - green */
.status-vectorized {
  background: var(--color-success-bg-transparent);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
}

.status-vectorized i {
  color: var(--color-success);
}

.status-vectorized:hover {
  background: var(--color-success-bg);
}

/* Pending status - yellow */
.status-pending {
  background: var(--color-warning-bg-transparent);
  color: var(--color-warning);
  border: 1px solid var(--color-warning-border);
}

.status-pending i {
  color: var(--color-warning);
}

.status-pending:hover {
  background: var(--color-warning-bg);
}

/* Failed status - red */
.status-failed {
  background: var(--color-error-bg-transparent);
  color: var(--color-error);
  border: 1px solid var(--color-error-border);
  cursor: pointer;
}

.status-failed i {
  color: var(--color-error);
}

.status-failed:hover {
  background: var(--color-error-bg);
  transform: scale(1.05);
}

/* Unknown status - gray */
.status-unknown {
  background: var(--bg-tertiary-transparent);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.status-unknown i {
  color: var(--text-tertiary);
}

.status-unknown:hover {
  background: var(--bg-tertiary);
}

.badge-label {
  white-space: nowrap;
}
</style>
