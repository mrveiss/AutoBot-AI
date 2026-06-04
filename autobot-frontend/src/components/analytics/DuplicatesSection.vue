<template>
  <div class="duplicates-section analytics-section">
    <h3>
      <Icon name="copy" /> {{ $t('analytics.duplicates.title') }}
      <span v-if="duplicates && duplicates.length > 0" class="total-count">
        ({{ duplicates.length.toLocaleString() }} {{ $t('analytics.duplicates.pairs') }})
      </span>
      <div v-if="duplicates && duplicates.length > 0" class="section-export-buttons">
        <button @click="emit('export', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')">
          <Icon name="file-alt" /> MD
        </button>
        <button @click="emit('export', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')">
          <Icon name="file-code" /> JSON
        </button>
      </div>
    </h3>
    <div v-if="loading" class="section-loading">
      <Icon name="spinner" class="animate-spin" />
      <span>{{ $t('analytics.codebase.actions.loading') }}</span>
    </div>
    <div v-else-if="duplicates && duplicates.length > 0" class="section-content">
      <!-- Similarity Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ duplicates.length.toLocaleString() }}</div>
          <div class="summary-label">{{ $t('analytics.duplicates.totalPairs') }}</div>
        </div>
        <div class="summary-card high">
          <div class="summary-value">{{ duplicatesBySimilarity.high?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.duplicates.highLabel') }}</div>
        </div>
        <div class="summary-card medium">
          <div class="summary-value">{{ duplicatesBySimilarity.medium?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.duplicates.mediumLabel') }}</div>
        </div>
        <div class="summary-card low">
          <div class="summary-value">{{ duplicatesBySimilarity.low?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.duplicates.lowLabel') }}</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ totalDuplicateLines.toLocaleString() }}</div>
          <div class="summary-label">{{ $t('analytics.duplicates.totalLines') }}</div>
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
              <Icon :name="isGroupExpanded(similarity) ? 'chevron-down' : 'chevron-right'" />
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
            <div v-if="isGroupExpanded(similarity)" class="accordion-items">
              <div
                v-for="(duplicate, index) in group.slice(0, 20)"
                :key="index"
                class="list-item"
                :class="`item-${similarity}`"
              >
                <div class="item-header">
                  <span class="item-similarity" :class="similarity">{{ duplicate.similarity }}% {{ $t('analytics.duplicates.similar') }}</span>
                  <span class="item-lines">{{ duplicate.lines }} {{ $t('analytics.duplicates.lines') }}</span>
                </div>
                <div class="item-files">
                  <div class="item-file">{{ duplicate.file1 }}</div>
                  <div class="item-file">{{ duplicate.file2 }}</div>
                </div>
              </div>
              <div v-if="group.length > 20" class="show-more">
                <span class="muted">{{ $t('analytics.duplicates.showingOf', { shown: 20, total: group.length.toLocaleString() }) }}</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else-if="!loading"
      icon="check-circle"
      :message="$t('analytics.duplicates.emptyMessage')"
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

import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useAggregationMemo } from '@/composables/useComputedMemo'
import { useExpansion } from '@/composables/useExpansion'

const { t } = useI18n()

interface Duplicate {
  similarity: number
  lines: number
  file1: string
  file2: string
}

interface Props {
  duplicates: Duplicate[]
  /** #5368: render a spinner during the scan instead of empty-state. */
  loading?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  export: [format: 'md' | 'json']
}>()

const groupExpansion = useExpansion<string>()
const isGroupExpanded = groupExpansion.isExpanded

const duplicatesBySimilarity = computed(() => {
  const groups: Record<string, Duplicate[]> = { high: [], medium: [], low: [] }
  props.duplicates.forEach(d => {
    if (d.similarity >= 90) groups.high.push(d)
    else if (d.similarity >= 70) groups.medium.push(d)
    else groups.low.push(d)
  })
  return groups
})

// Issue #4036: Memoized line count aggregation
const totalDuplicateLines = useAggregationMemo(
  () => props.duplicates.reduce((sum, d) => sum + d.lines, 0),
  () => [props.duplicates],
  { ttl: 60000 } // 1 minute TTL for line counts
)

const toggleDuplicateGroup = (similarity: string) => {
  groupExpansion.toggle(similarity)
}

const formatSimilarityGroup = (similarity: string): string => {
  const key = `analytics.duplicates.similarityGroups.${similarity}`
  const translated = t(key)
  return translated !== key ? translated : similarity
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
  flex-wrap: wrap;
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

/* #5368: loading state shown during scan in progress */
.section-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-6);
  background: var(--bg-primary-alpha);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.section-loading i {
  color: var(--color-info);
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

.section-export-buttons {
  display: flex;
  gap: var(--spacing-2);
  margin-left: auto;
}

.export-btn {
  padding: var(--spacing-1) var(--spacing-2-5);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 0.8em;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  transition: all var(--duration-150) var(--ease-out);
}

.export-btn:hover {
  background: var(--bg-card);
  border-color: var(--color-info-dark);
  color: var(--text-primary);
}
</style>
