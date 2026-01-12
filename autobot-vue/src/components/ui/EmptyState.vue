<template>
  <div class="empty-state" :class="{ 'compact': compact }">
    <i :class="iconClass" class="empty-icon"></i>
    <h4 v-if="title" class="empty-title">{{ title }}</h4>
    <p v-if="message" class="empty-message">{{ message }}</p>
    <slot name="actions"></slot>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * Reusable Empty State Component
 *
 * Displays consistent empty states across the application.
 * Eliminates duplicate empty state implementations in 11+ components.
 *
 * Usage:
 * ```vue
 * <EmptyState
 *   icon="fas fa-inbox"
 *   title="No documents found"
 *   message="Start by adding your first document"
 * >
 *   <template #actions>
 *     <button @click="addDocument">Add Document</button>
 *   </template>
 * </EmptyState>
 * ```
 */

interface Props {
  /** Icon class (Font Awesome) */
  icon?: string
  /** Title text */
  title?: string
  /** Message text */
  message?: string
  /** Compact mode (smaller spacing) */
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  icon: 'fas fa-inbox',
  compact: false
})

const iconClass = computed(() => props.icon)
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.empty-state {
  text-align: center;
  padding: var(--spacing-16) var(--spacing-8);
  color: var(--text-secondary);
}

.empty-state.compact {
  padding: var(--spacing-8) var(--spacing-4);
}

.empty-icon {
  font-size: var(--text-5xl);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.empty-state.compact .empty-icon {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-3);
}

.empty-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.empty-state.compact .empty-title {
  font-size: var(--text-base);
  margin-bottom: var(--spacing-1-5);
}

.empty-message {
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-4);
}

.empty-state.compact .empty-message {
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-3);
}
</style>
