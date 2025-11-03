<template>
  <span class="status-badge" :class="[`status-${variant}`, sizeClass, { 'with-icon': icon }]">
    <i v-if="icon" :class="icon"></i>
    <slot></slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * Reusable Status Badge Component
 *
 * Provides consistent status indicators across the application.
 * Supports multiple variants and sizes.
 *
 * Usage:
 * ```vue
 * <StatusBadge variant="success" icon="fas fa-check-circle">Active</StatusBadge>
 * <StatusBadge variant="danger" size="large">Failed</StatusBadge>
 * <StatusBadge variant="warning">Pending</StatusBadge>
 * ```
 */

interface Props {
  /** Badge variant: success, danger, warning, info, secondary */
  variant?: 'success' | 'danger' | 'warning' | 'info' | 'secondary' | 'primary'
  /** Badge size: small, medium, large */
  size?: 'small' | 'medium' | 'large'
  /** Optional icon class (Font Awesome) */
  icon?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'secondary',
  size: 'medium'
})

const sizeClass = computed(() => `status-${props.size}`)
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s;
}

/* Sizes */
.status-small {
  padding: 0.125rem 0.5rem;
  font-size: 0.75rem;
  gap: 0.25rem;
}

.status-medium {
  padding: 0.25rem 0.75rem;
  font-size: 0.875rem;
  gap: 0.375rem;
}

.status-large {
  padding: 0.375rem 1rem;
  font-size: 1rem;
  gap: 0.5rem;
}

/* Variants */
.status-success {
  background: #d1fae5;
  color: #065f46;
}

.status-danger {
  background: #fee2e2;
  color: #991b1b;
}

.status-warning {
  background: #fef3c7;
  color: #92400e;
}

.status-info {
  background: #dbeafe;
  color: #1e40af;
}

.status-primary {
  background: #dbeafe;
  color: #1e40af;
}

.status-secondary {
  background: #f3f4f6;
  color: #6b7280;
}

/* Icon */
.with-icon i {
  font-size: 0.875em;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .status-success {
    background: #065f46;
    color: #d1fae5;
  }

  .status-danger {
    background: #991b1b;
    color: #fee2e2;
  }

  .status-warning {
    background: #92400e;
    color: #fef3c7;
  }

  .status-info,
  .status-primary {
    background: #1e40af;
    color: #dbeafe;
  }

  .status-secondary {
    background: #4b5563;
    color: #d1d5db;
  }
}
</style>
