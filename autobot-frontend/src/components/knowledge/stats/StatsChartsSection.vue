<template>
  <div class="charts-section">
    <!-- Documents by Category -->
    <BasePanel variant="bordered" size="md">
      <h4>{{ $t('knowledge.stats.docsByCategory') }}</h4>
      <div class="bar-chart">
        <div
          v-for="category in topCategories"
          :key="category.name"
          class="bar-item"
        >
          <div class="bar-label">{{ category.name }}</div>
          <div class="bar-wrapper">
            <div
              class="bar-fill"
              :style="{
                width: `${(category.documentCount / maxCategoryCount) * 100}%`,
                backgroundColor: category.color || 'var(--color-info)'
              }"
            ></div>
            <span class="bar-value">{{ category.documentCount }}</span>
          </div>
        </div>
      </div>
    </BasePanel>

    <!-- Documents by Type -->
    <BasePanel variant="bordered" size="md">
      <h4>{{ $t('knowledge.stats.docsByType') }}</h4>
      <div class="pie-chart">
        <div class="type-stats">
          <div v-for="(count, type) in documentsByType" :key="type" class="type-item">
            <div class="type-color" :style="{ backgroundColor: getTypeColor(String(type)) }"></div>
            <span class="type-name">{{ capitalize(String(type)) }}</span>
            <span class="type-count">{{ count }}</span>
            <span class="type-percentage">({{ getTypePercentage(count) }}%)</span>
          </div>
        </div>
      </div>
    </BasePanel>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Stats Charts Section Component
 *
 * Displays chart visualizations for documents by category and type.
 * Wired into KnowledgeHealthAnalytics.vue (#11562).
 *
 * Issue #184: Split oversized Vue components
 * Issue #11562: Wire in orphaned stats subpanels
 */

import BasePanel from '@/components/base/BasePanel.vue'

interface Category {
  name: string
  documentCount: number
  color?: string
}

interface Props {
  topCategories: Category[]
  maxCategoryCount: number
  documentsByType: Record<string, number>
  totalDocuments: number
}

const props = defineProps<Props>()

const getTypeColor = (type: string): string => {
  const colors: Record<string, string> = {
    document: 'var(--color-info)',
    webpage: 'var(--color-success)',
    api: 'var(--color-warning)',
    upload: 'var(--chart-purple)'
  }
  return colors[type] || 'var(--text-tertiary)'
}

const getTypePercentage = (count: number): number => {
  if (props.totalDocuments === 0) return 0
  return Math.round((count / props.totalDocuments) * 100)
}

const capitalize = (str: string): string => {
  return str && str.length > 0 ? str.charAt(0).toUpperCase() + str.slice(1) : str || ''
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.charts-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-6);
}

.charts-section h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

/* Bar Chart */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.bar-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.bar-label {
  width: 120px;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.bar-wrapper {
  flex: 1;
  height: 1.5rem;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  position: relative;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width var(--duration-500) var(--ease-out);
}

.bar-value {
  position: absolute;
  right: var(--spacing-2);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

/* Type Stats */
.type-stats {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.type-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.type-color {
  width: 1rem;
  height: 1rem;
  border-radius: var(--radius-default);
}

.type-name {
  flex: 1;
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.type-count {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.type-percentage {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .charts-section {
    grid-template-columns: 1fr;
  }

  .bar-label {
    width: 80px;
    font-size: var(--text-xs);
  }
}
</style>
