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
/* Issue #704: Migrated to CSS design tokens */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
  transition: all var(--duration-200) var(--ease-in-out);
}

/* Sizes */
.status-small {
  padding: var(--spacing-0-5) var(--spacing-2);
  font-size: var(--text-xs);
  gap: var(--spacing-1);
}

.status-medium {
  padding: var(--spacing-1) var(--spacing-3);
  font-size: var(--text-sm);
  gap: var(--spacing-1-5);
}

.status-large {
  padding: var(--spacing-1-5) var(--spacing-4);
  font-size: var(--text-base);
  gap: var(--spacing-2);
}

/* Variants */
.status-success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-danger {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.status-warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-info {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.status-primary {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.status-secondary {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

/* Icon */
.with-icon i {
  font-size: 0.875em;
}
</style>
