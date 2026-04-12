<template>
  <div class="stats-overview" role="region" :aria-label="$t('knowledge.stats.overview.ariaLabel')">
    <BasePanel variant="elevated" size="small" role="article" aria-labelledby="facts-title">
      <div class="stat-icon facts" aria-hidden="true">
        <i class="fas fa-lightbulb"></i>
      </div>
      <div class="stat-content">
        <h4 id="facts-title">{{ $t('knowledge.stats.overview.totalFacts') }}</h4>
        <p class="stat-value" aria-live="polite">{{ totalFacts }}</p>
        <p class="stat-change" :aria-label="$t('knowledge.stats.overview.factsAriaLabel')">
          {{ $t('knowledge.stats.overview.factsDescription') }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="small" role="article" aria-labelledby="documents-title">
      <div class="stat-icon documents" aria-hidden="true">
        <i class="fas fa-file-alt"></i>
      </div>
      <div class="stat-content">
        <h4 id="documents-title">{{ $t('knowledge.stats.overview.totalDocuments') }}</h4>
        <p class="stat-value" aria-live="polite">{{ totalDocuments }}</p>
        <p class="stat-change" :class="{ 'needs-vectorization': needsVectorization }"
           :aria-label="needsVectorization ? $t('knowledge.stats.overview.notVectorizedAria') : $t('knowledge.stats.overview.vectorizedAria')">
          <i v-if="needsVectorization" class="fas fa-exclamation-triangle" aria-hidden="true"></i>
          {{ needsVectorization ? $t('knowledge.stats.overview.notVectorized') : $t('knowledge.stats.overview.vectorizedForRag') }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="small" role="article" aria-labelledby="categories-title">
      <div class="stat-icon categories" aria-hidden="true">
        <i class="fas fa-folder"></i>
      </div>
      <div class="stat-content">
        <h4 id="categories-title">{{ $t('knowledge.stats.overview.categories') }}</h4>
        <p class="stat-value" aria-live="polite">{{ categoryCount }}</p>
        <p class="stat-change" :aria-label="$t('knowledge.stats.overview.avgDocsPerCategoryAria')">
          {{ $t('knowledge.stats.overview.avgDocsPerCategory', { count: avgDocsPerCategory }) }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="small">
      <div class="stat-icon tags">
        <i class="fas fa-tags"></i>
      </div>
      <div class="stat-content">
        <h4>{{ $t('knowledge.stats.overview.uniqueTags') }}</h4>
        <p class="stat-value">{{ uniqueTagsCount }}</p>
        <p class="stat-change">
          {{ $t('knowledge.stats.overview.avgTagsPerDoc', { count: avgTagsPerDoc }) }}
        </p>
      </div>
    </BasePanel>

    <BasePanel variant="elevated" size="small">
      <div class="stat-icon storage">
        <i class="fas fa-database"></i>
      </div>
      <div class="stat-content">
        <h4>{{ $t('knowledge.stats.overview.storageUsed') }}</h4>
        <p class="stat-value">{{ formatFileSize(totalStorageSize) }}</p>
        <p class="stat-change">
          {{ $t('knowledge.stats.overview.avgPerDoc', { size: formatFileSize(avgDocSize) }) }}
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
 * Displays overview statistics cards for knowledge base.
 * Extracted from KnowledgeStats.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import { formatFileSize } from '@/utils/formatHelpers'

interface Props {
  totalFacts: number
  totalDocuments: number
  categoryCount: number
  uniqueTagsCount: number
  avgDocsPerCategory: number
  avgTagsPerDoc: string
  totalStorageSize: number
  avgDocSize: number
  needsVectorization: boolean
}

defineProps<Props>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-8);
}

.stat-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  color: var(--text-on-primary);
}

.stat-icon.facts { background: var(--chart-pink); }
.stat-icon.documents { background: var(--color-primary); }
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
  font-size: 1.875rem;
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

.stat-change.positive { color: var(--color-success); }

.stat-change.needs-vectorization {
  color: var(--color-warning);
  font-weight: var(--font-medium);
}

@media (max-width: 768px) {
  .stats-overview {
    grid-template-columns: 1fr;
  }
}
</style>
