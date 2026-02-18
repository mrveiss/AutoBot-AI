<template>
  <div class="duplicates-section analytics-section">
    <h3>
      <i class="fas fa-copy"></i> Duplicate Code Detection
      <span v-if="duplicates && duplicates.length > 0" class="total-count">
        ({{ duplicates.length.toLocaleString() }} pairs)
      </span>
    </h3>
    <div v-if="duplicates && duplicates.length > 0" class="section-content">
      <!-- Similarity Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ duplicates.length.toLocaleString() }}</div>
          <div class="summary-label">Total Pairs</div>
        </div>
        <div class="summary-card high">
          <div class="summary-value">{{ duplicatesBySimilarity.high?.length || 0 }}</div>
          <div class="summary-label">High (90%+)</div>
        </div>
        <div class="summary-card medium">
          <div class="summary-value">{{ duplicatesBySimilarity.medium?.length || 0 }}</div>
          <div class="summary-label">Medium (70-89%)</div>
        </div>
        <div class="summary-card low">
          <div class="summary-value">{{ duplicatesBySimilarity.low?.length || 0 }}</div>
          <div class="summary-label">Low (&lt;70%)</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ totalDuplicateLines.toLocaleString() }}</div>
          <div class="summary-label">Total Lines</div>
        </div>
      </div>

      <!-- Duplicates by Similarity Group -->
      <div class="accordion-groups">
        <div
          v-for="(group, similarity) in duplicatesBySimilarity"
          :key="similarity"
          v-show="group && group.length > 0"
          class="accordion-group"
        >
          <div
            class="accordion-header"
            @click="toggleDuplicateGroup(String(similarity))"
          >
            <div class="header-info">
              <i :class="expandedDuplicateGroups[similarity] ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">{{ formatSimilarityGroup(String(similarity)) }}</span>
              <span class="header-count">({{ group.length }})</span>
            </div>
            <div class="header-badges">
              <span class="similarity-badge" :class="similarity">
                {{ similarity === 'high' ? '90%+' : similarity === 'medium' ? '70-89%' : '<70%' }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expandedDuplicateGroups[similarity]" class="accordion-items">
              <div
                v-for="(duplicate, index) in group.slice(0, 20)"
                :key="index"
                class="list-item"
                :class="`item-${similarity}`"
              >
                <div class="item-header">
                  <span class="item-similarity" :class="similarity">{{ duplicate.similarity }}% similar</span>
                  <span class="item-lines">{{ duplicate.lines }} lines</span>
                </div>
                <div class="item-files">
                  <div class="item-file">{{ duplicate.file1 }}</div>
                  <div class="item-file">{{ duplicate.file2 }}</div>
                </div>
              </div>
              <div v-if="group.length > 20" class="show-more">
                <span class="muted">Showing 20 of {{ group.length.toLocaleString() }} pairs</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else
      icon="fas fa-check-circle"
      message="No duplicate code detected or analysis not run yet."
      variant="success"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Duplicates Section Component
 *
 * Displays duplicate code detection results grouped by similarity.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface Duplicate {
  similarity: number
  lines: number
  file1: string
  file2: string
}

interface Props {
  duplicates: Duplicate[]
}

const props = defineProps<Props>()

const expandedDuplicateGroups = ref<Record<string, boolean>>({})

const duplicatesBySimilarity = computed(() => {
  const groups: Record<string, Duplicate[]> = { high: [], medium: [], low: [] }
  props.duplicates.forEach(d => {
    if (d.similarity >= 90) groups.high.push(d)
    else if (d.similarity >= 70) groups.medium.push(d)
    else groups.low.push(d)
  })
  return groups
})

const totalDuplicateLines = computed(() => {
  return props.duplicates.reduce((sum, d) => sum + d.lines, 0)
})

const toggleDuplicateGroup = (similarity: string) => {
  expandedDuplicateGroups.value[similarity] = !expandedDuplicateGroups.value[similarity]
}

const formatSimilarityGroup = (similarity: string): string => {
  const labels: Record<string, string> = {
    high: 'High Similarity (90%+)',
    medium: 'Medium Similarity (70-89%)',
    low: 'Low Similarity (<70%)'
  }
  return labels[similarity] || similarity
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.duplicates-section {
  margin-bottom: var(--spacing-6);
}

.duplicates-section h3 {
  color: var(--color-info);
  margin-bottom: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.total-count {
  font-size: 0.8em;
  color: var(--text-muted);
}

.section-content {
  background: var(--bg-primary-alpha);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.summary-cards {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-5);
}

.summary-card {
  padding: var(--spacing-3) var(--spacing-5);
  border-radius: var(--radius-lg);
  text-align: center;
  min-width: 80px;
}

.summary-card.total { background: var(--bg-tertiary-alpha); }
.summary-card.high { background: var(--color-error-bg); }
.summary-card.medium { background: var(--color-warning-bg); }
.summary-card.low { background: var(--color-success-bg); }
.summary-card.info { background: var(--color-info-bg); }

.summary-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-on-primary);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.accordion-group {
  background: var(--bg-tertiary-alpha);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  cursor: pointer;
  transition: background var(--duration-200);
}

.accordion-header:hover {
  background: var(--bg-hover);
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-name {
  font-weight: var(--font-semibold);
  color: var(--text-on-primary);
}

.header-count {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.similarity-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.similarity-badge.high { background: var(--color-error-bg); color: var(--color-error); }
.similarity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.similarity-badge.low { background: var(--color-success-bg); color: var(--color-success); }

.accordion-items {
  padding: 0 var(--spacing-4) var(--spacing-4);
}

.list-item {
  background: var(--bg-primary-alpha);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-2);
  border-left: 3px solid var(--text-tertiary);
}

.list-item.item-high { border-left-color: var(--color-error); }
.list-item.item-medium { border-left-color: var(--color-warning); }
.list-item.item-low { border-left-color: var(--color-success); }

.item-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.item-similarity {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.item-similarity.high { background: var(--color-error-bg); color: var(--color-error); }
.item-similarity.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.item-similarity.low { background: var(--color-success-bg); color: var(--color-success); }

.item-lines {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.item-files {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.item-file {
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.show-more {
  text-align: center;
  padding: var(--spacing-2);
}

.muted {
  color: var(--text-disabled);
  font-size: var(--text-xs);
}

.accordion-enter-active,
.accordion-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
