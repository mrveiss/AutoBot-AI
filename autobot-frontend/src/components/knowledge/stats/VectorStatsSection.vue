<template>
  <div v-if="vectorStats" class="vector-chart-section">
    <h4><Icon name="chart-pie" /> {{ $t('knowledge.stats.vectorDistribution') }}</h4>
    <div class="vector-categories-chart">
      <div
        v-for="(category, idx) in vectorStats.categories"
        :key="idx"
        class="category-bar"
      >
        <div class="category-info">
          <span class="category-name">{{ formatCategoryName(category) }}</span>
          <span class="category-count">{{ $t('knowledge.stats.factsCount', { count: getCategoryFactCount(category) }) }}</span>
        </div>
        <div class="category-progress">
          <div
            class="category-fill"
            :style="{
              width: getCategoryPercentage(category) + '%',
              backgroundColor: getCategoryColor(idx)
            }"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Vector Stats Section Component
 *
 * Displays vector category distribution chart for KnowledgeHealthAnalytics.
 * Self-contained: owns useVectorStats and useKnowledgeStats composables.
 * Wired into KnowledgeHealthAnalytics.vue (#11562).
 *
 * Issue #184: Split oversized Vue components
 * Issue #11562: Wire in orphaned stats subpanels
 */

import Icon from '@/components/ui/Icon.vue'
import { useVectorStats } from '@/composables/knowledge/useVectorStats'
import { useKnowledgeStats } from '@/composables/knowledge/useKnowledgeStats'
import { formatCategoryName } from '@/utils/formatHelpers'

const { vectorStats } = useVectorStats()
const { categoryFactCounts } = useKnowledgeStats()

const getCategoryFactCount = (category: string): number => {
  return categoryFactCounts.value[category] || 0
}

const getCategoryPercentage = (category: string): number => {
  const total = vectorStats.value?.total_facts || 1
  const count = getCategoryFactCount(category)
  return Math.round((count / total) * 100)
}

const getCategoryColor = (index: number): string => {
  const colors = [
    'var(--color-primary)',
    'var(--color-success)',
    'var(--color-warning)',
    'var(--chart-purple)',
    'var(--color-error)',
    'var(--chart-cyan)'
  ]
  return colors[index % colors.length]
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.vector-chart-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.vector-chart-section h4 {
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-6);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.vector-categories-chart {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.category-bar {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.category-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-sm);
}

.category-name {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.category-count {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.category-progress {
  height: 1.5rem;
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  overflow: hidden;
  position: relative;
}

.category-fill {
  height: 100%;
  border-radius: var(--radius-xl);
  transition: width var(--duration-500) var(--ease-out);
}
</style>
