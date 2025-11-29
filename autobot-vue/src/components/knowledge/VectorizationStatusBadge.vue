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
.vectorization-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 600;
  transition: all 0.2s ease;
  cursor: default;
}

.vectorization-badge.compact {
  padding: 0.125rem 0.375rem;
  font-size: 0.6875rem;
}

.vectorization-badge i {
  font-size: 0.875rem;
}

.vectorization-badge.compact i {
  font-size: 0.75rem;
}

/* Vectorized status - green */
.status-vectorized {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.status-vectorized i {
  color: #10b981;
}

.status-vectorized:hover {
  background: rgba(16, 185, 129, 0.15);
}

/* Pending status - yellow */
.status-pending {
  background: rgba(251, 191, 36, 0.1);
  color: #d97706;
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.status-pending i {
  color: #fbbf24;
}

.status-pending:hover {
  background: rgba(251, 191, 36, 0.15);
}

/* Failed status - red */
.status-failed {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
  border: 1px solid rgba(239, 68, 68, 0.3);
  cursor: pointer;
}

.status-failed i {
  color: #ef4444;
}

.status-failed:hover {
  background: rgba(239, 68, 68, 0.2);
  transform: scale(1.05);
}

/* Unknown status - gray */
.status-unknown {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
  border: 1px solid rgba(107, 114, 128, 0.3);
}

.status-unknown i {
  color: #9ca3af;
}

.status-unknown:hover {
  background: rgba(107, 114, 128, 0.15);
}

.badge-label {
  white-space: nowrap;
}

</style>
