<template>
  <div class="stats-overview" role="region" :aria-label="$t('knowledge.stats.overviewAriaLabel')">
    <BasePanel variant="elevated" size="sm" role="article" aria-labelledby="analytics-documents-title">
      <div class="stat-icon documents" aria-hidden="true">
        <Icon name="file-alt" />
      </div>
      <div class="stat-content">
        <h4 id="analytics-documents-title">{{ $t('knowledge.stats.totalDocuments') }}</h4>
        <p class="stat-value" aria-live="polite">{{ documentCount }}</p>
        <p class="stat-change">
          {{ $t('knowledge.stats.avgTagsPerDoc', { count: avgTagsPerDoc }) }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="sm" role="article" aria-labelledby="analytics-categories-title">
      <div class="stat-icon categories" aria-hidden="true">
        <Icon name="folder" />
      </div>
      <div class="stat-content">
        <h4 id="analytics-categories-title">{{ $t('knowledge.stats.categories') }}</h4>
        <p class="stat-value" aria-live="polite">{{ categoryCount }}</p>
        <p class="stat-change">
          {{ $t('knowledge.stats.avgDocsPerCategoryValue', { count: avgDocsPerCategory }) }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="sm">
      <div class="stat-icon tags">
        <Icon name="tags" />
      </div>
      <div class="stat-content">
        <h4>{{ $t('knowledge.stats.uniqueTags') }}</h4>
        <p class="stat-value">{{ uniqueTagsCount }}</p>
        <p class="stat-change">
          {{ $t('knowledge.stats.avgTagsPerDoc', { count: avgTagsPerDoc }) }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="sm">
      <div class="stat-icon storage">
        <Icon name="database" />
      </div>
      <div class="stat-content">
        <h4>{{ $t('knowledge.stats.storageUsedTitle') }}</h4>
        <p class="stat-value">{{ formatFileSize(totalStorageSize) }}</p>
        <p class="stat-change">
          {{ $t('knowledge.stats.avgPerDoc', { size: formatFileSize(avgDocSize) }) }}
        </p>
      </div>
    </BasePanel>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Stats Overview Cards Component
 *
 * Displays overview statistics cards for knowledge base (4-card layout:
 * documents, categories, tags, storage). Wired into KnowledgeHealthAnalytics.vue (#11562).
 *
 * Issue #184: Split oversized Vue components
 * Issue #11562: Wire in orphaned stats subpanels
 */

import Icon from '@/components/ui/Icon.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import { formatFileSize } from '@/utils/formatHelpers'

interface Props {
  documentCount: number
  categoryCount: number
  uniqueTagsCount: number
  avgDocsPerCategory: number
  avgTagsPerDoc: string
  totalStorageSize: number
  avgDocSize: number
}

defineProps<Props>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--spacing-6);
}

.stat-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
  color: var(--text-on-primary);
}

.stat-icon.documents { background: var(--color-info); }
.stat-icon.categories { background: var(--color-success); }
.stat-icon.tags { background: var(--color-warning); }
.stat-icon.storage { background: var(--chart-purple); }

.stat-content { flex: 1; }

.stat-content h4 {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.stat-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.stat-change {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

@media (max-width: 768px) {
  .stats-overview {
    grid-template-columns: 1fr;
  }
}
</style>
