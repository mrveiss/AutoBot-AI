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
.duplicates-section {
  margin-bottom: 24px;
}

.duplicates-section h3 {
  color: #00d4ff;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.total-count {
  font-size: 0.8em;
  color: rgba(255, 255, 255, 0.6);
}

.section-content {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 16px;
}

.summary-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.summary-card {
  padding: 12px 20px;
  border-radius: 8px;
  text-align: center;
  min-width: 80px;
}

.summary-card.total { background: rgba(255, 255, 255, 0.1); }
.summary-card.high { background: rgba(244, 67, 54, 0.2); }
.summary-card.medium { background: rgba(255, 152, 0, 0.2); }
.summary-card.low { background: rgba(76, 175, 80, 0.2); }
.summary-card.info { background: rgba(0, 212, 255, 0.2); }

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: white;
}

.summary-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accordion-group {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
}

.accordion-header:hover {
  background: rgba(255, 255, 255, 0.1);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-name {
  font-weight: 600;
  color: white;
}

.header-count {
  color: rgba(255, 255, 255, 0.5);
  font-size: 13px;
}

.similarity-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.similarity-badge.high { background: rgba(244, 67, 54, 0.3); color: #f44336; }
.similarity-badge.medium { background: rgba(255, 152, 0, 0.3); color: #ff9800; }
.similarity-badge.low { background: rgba(76, 175, 80, 0.3); color: #4caf50; }

.accordion-items {
  padding: 0 16px 16px;
}

.list-item {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
  border-left: 3px solid #666;
}

.list-item.item-high { border-left-color: #f44336; }
.list-item.item-medium { border-left-color: #ff9800; }
.list-item.item-low { border-left-color: #4caf50; }

.item-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.item-similarity {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.item-similarity.high { background: rgba(244, 67, 54, 0.3); color: #f44336; }
.item-similarity.medium { background: rgba(255, 152, 0, 0.3); color: #ff9800; }
.item-similarity.low { background: rgba(76, 175, 80, 0.3); color: #4caf50; }

.item-lines {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
}

.item-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-file {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  font-family: monospace;
}

.show-more {
  text-align: center;
  padding: 8px;
}

.muted {
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
}

.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
