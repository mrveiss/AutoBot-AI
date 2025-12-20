<template>
  <div class="charts-section">
    <!-- Documents by Category -->
    <BasePanel variant="bordered" size="medium">
      <h4>Documents by Category</h4>
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
                backgroundColor: category.color || '#3b82f6'
              }"
            ></div>
            <span class="bar-value">{{ category.documentCount }}</span>
          </div>
        </div>
      </div>
    </BasePanel>

    <!-- Documents by Type -->
    <BasePanel variant="bordered" size="medium">
      <h4>Documents by Type</h4>
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
 * Extracted from KnowledgeStats.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
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
    document: '#3b82f6',
    webpage: '#10b981',
    api: '#f59e0b',
    upload: '#8b5cf6'
  }
  return colors[type] || '#6b7280'
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
.charts-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.charts-section h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

/* Bar Chart */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bar-item {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.bar-label {
  width: 120px;
  font-size: 0.875rem;
  color: #374151;
}

.bar-wrapper {
  flex: 1;
  height: 1.5rem;
  background: #f3f4f6;
  border-radius: 0.375rem;
  position: relative;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.5s ease;
}

.bar-value {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.75rem;
  font-weight: 500;
  color: #374151;
}

/* Type Stats */
.type-stats {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.type-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem;
  background: #f9fafb;
  border-radius: 0.375rem;
}

.type-color {
  width: 1rem;
  height: 1rem;
  border-radius: 0.25rem;
}

.type-name {
  flex: 1;
  font-weight: 500;
  color: #374151;
}

.type-count {
  font-weight: 600;
  color: #1f2937;
}

.type-percentage {
  font-size: 0.875rem;
  color: #6b7280;
}

@media (max-width: 768px) {
  .charts-section {
    grid-template-columns: 1fr;
  }

  .bar-label {
    width: 80px;
    font-size: 0.75rem;
  }
}
</style>
