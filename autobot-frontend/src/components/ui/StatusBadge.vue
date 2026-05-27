<template>
  <span class="status-badge" :class="[`status-${variant}`, sizeClass, { 'with-icon': icon }]">
    <Icon v-if="icon" :name="icon" />
    <slot></slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon, { type IconName } from '@/components/ui/Icon.vue'

/**
 * Reusable Status Badge Component
 *
 * Provides consistent status indicators across the application.
 * Supports multiple variants and sizes.
 *
 * Usage:
 * ```vue
 * <StatusBadge variant="success" icon="check-circle">Active</StatusBadge>
 * <StatusBadge variant="error" size="lg">Failed</StatusBadge>
 * <StatusBadge variant="warning">Pending</StatusBadge>
 * ```
 */

interface Props {
  /** Badge variant: success, error, warning, info, secondary */
  variant?: 'success' | 'error' | 'warning' | 'info' | 'secondary' | 'primary'
  /** Badge size: sm, md, lg */
  size?: 'sm' | 'md' | 'lg'
  /** Optional icon name (IconName) */
  icon?: IconName
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'secondary',
  size: 'md'
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
.status-sm {
  padding: var(--spacing-0-5) var(--spacing-2);
  font-size: var(--text-xs);
  gap: var(--spacing-1);
}

.status-md {
  padding: var(--spacing-1) var(--spacing-3);
  font-size: var(--text-sm);
  gap: var(--spacing-1-5);
}

.status-lg {
  padding: var(--spacing-1-5) var(--spacing-4);
  font-size: var(--text-base);
  gap: var(--spacing-2);
}

/* Variants */
.status-success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-error {
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
.with-icon svg {
  width: 0.875em;
  height: 0.875em;
}
</style>
