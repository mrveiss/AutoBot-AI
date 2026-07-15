<template>
  <BasePanel variant="bordered" size="md">
    <h4>{{ $t('knowledge.stats.popularTags') }}</h4>
    <div class="tag-cloud" role="list" :aria-label="$t('knowledge.stats.popularTagsAriaLabel')">
      <span
        v-for="tag in tags"
        :key="tag.name"
        class="tag-cloud-item"
        :style="{ fontSize: `${tag.size}rem` }"
        :title="$t('knowledge.health.tagDocCount', { count: tag.count })"
        :aria-label="`${tag.name}: ${$t('knowledge.health.tagDocCount', { count: tag.count })}`"
        role="listitem"
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
 * Wired into KnowledgeHealthAnalytics.vue (#11562).
 *
 * Issue #184: Split oversized Vue components
 * Issue #11562: Wire in orphaned stats subpanels
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

defineProps<Props>()
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
  color: var(--color-info);
  transition: var(--transition-all);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
}

.tag-cloud-item:hover {
  color: var(--color-info-hover);
  transform: scale(1.1);
}
</style>
