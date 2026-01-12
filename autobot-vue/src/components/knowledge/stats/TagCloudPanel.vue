<template>
  <BasePanel variant="bordered" size="medium">
    <h4>Popular Tags</h4>
    <div class="tag-cloud" role="list" aria-label="Popular tags in knowledge base">
      <span
        v-for="tag in tags"
        :key="tag.name"
        class="tag-cloud-item"
        :style="{ fontSize: `${tag.size}rem` }"
        :title="`${tag.count} documents`"
        :aria-label="`${tag.name}: ${tag.count} documents`"
        role="listitem"
        tabindex="0"
        @click="$emit('tag-click', tag.name)"
        @keypress.enter="$emit('tag-click', tag.name)"
      >
        {{ tag.name }}
      </span>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Tag Cloud Panel Component
 *
 * Displays a cloud of popular tags with varying sizes.
 * Extracted from KnowledgeStats.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'

interface Tag {
  name: string
  count: number
  size: number
}

interface Props {
  tags: Tag[]
}

interface Emits {
  (e: 'tag-click', tagName: string): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  align-items: center;
}

.tag-cloud-item {
  color: var(--color-primary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
  outline: none;
}

.tag-cloud-item:hover,
.tag-cloud-item:focus {
  color: var(--color-primary-hover);
  transform: scale(1.1);
}

.tag-cloud-item:focus {
  box-shadow: var(--ring-primary);
  background: var(--color-primary-bg);
}
</style>
