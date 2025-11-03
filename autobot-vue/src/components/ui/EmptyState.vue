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
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #6b7280;
}

.empty-state.compact {
  padding: 2rem 1rem;
}

.empty-icon {
  font-size: 3rem;
  color: #d1d5db;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-state.compact .empty-icon {
  font-size: 2rem;
  margin-bottom: 0.75rem;
}

.empty-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.empty-state.compact .empty-title {
  font-size: 1rem;
  margin-bottom: 0.375rem;
}

.empty-message {
  color: #9ca3af;
  margin-bottom: 1rem;
}

.empty-state.compact .empty-message {
  font-size: 0.875rem;
  margin-bottom: 0.75rem;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .empty-state {
    color: #9ca3af;
  }

  .empty-icon {
    color: #4b5563;
  }

  .empty-title {
    color: #9ca3af;
  }

  .empty-message {
    color: #6b7280;
  }
}
</style>
