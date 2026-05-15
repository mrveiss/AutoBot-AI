<template>
  <div class="empty-state" :class="{ 'compact': compact }">
    <Icon :name="icon" class="empty-icon" />
    <h4 v-if="title" class="empty-title">{{ title }}</h4>
    <p v-if="message" class="empty-message">{{ message }}</p>
    <slot name="actions"></slot>
  </div>
</template>

<script setup lang="ts">
import Icon, { type IconName } from './Icon.vue'

interface Props {
  /** Icon name from Icon.vue registry */
  icon?: IconName
  /** Title text */
  title?: string
  /** Message text */
  message?: string
  /** Compact mode (smaller spacing) */
  compact?: boolean
}

withDefaults(defineProps<Props>(), {
  icon: 'inbox',
  compact: false
})
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
  width: var(--text-5xl);
  height: var(--text-5xl);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.empty-state.compact .empty-icon {
  width: var(--text-3xl);
  height: var(--text-3xl);
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
