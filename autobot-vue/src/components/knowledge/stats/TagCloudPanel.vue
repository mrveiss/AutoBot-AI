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
h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}

.tag-cloud-item {
  color: #3b82f6;
  cursor: pointer;
  transition: all 0.2s;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  outline: none;
}

.tag-cloud-item:hover,
.tag-cloud-item:focus {
  color: #2563eb;
  transform: scale(1.1);
}

.tag-cloud-item:focus {
  box-shadow: 0 0 0 2px #3b82f6;
  background: rgba(59, 130, 246, 0.1);
}
</style>
