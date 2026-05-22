<template>
  <div class="hardcodes-section analytics-section">
    <h3>
      <Icon name="bolt" /> {{ $t('analytics.hardcodes.title') }}
      <span v-if="hardcodes && hardcodes.length > 0" class="total-count">
        ({{ hardcodes.length.toLocaleString() }} {{ $t('analytics.hardcodes.values') }})
      </span>
      <div v-if="hardcodes && hardcodes.length > 0" class="section-export-buttons">
        <button @click="emit('export', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')">
          <Icon name="file-alt" /> MD
        </button>
        <button @click="emit('export', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')">
          <Icon name="file-code" /> JSON
        </button>
      </div>
    </h3>
    <div v-if="loading" class="section-loading">
      <Icon name="spinner" :spin="true" />
      <span>{{ $t('analytics.codebase.actions.loading') }}</span>
    </div>
    <div v-else-if="hardcodes && hardcodes.length > 0" class="section-content">
      <!-- Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ hardcodes.length.toLocaleString() }}</div>
          <div class="summary-label">{{ $t('analytics.hardcodes.totalValues') }}</div>
        </div>
        <div class="summary-card high">
          <div class="summary-value">{{ hardcodesBySeverity.high?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.hardcodes.highLabel') }}</div>
        </div>
        <div class="summary-card medium">
          <div class="summary-value">{{ hardcodesBySeverity.medium?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.hardcodes.mediumLabel') }}</div>
        </div>
        <div class="summary-card low">
          <div class="summary-value">{{ hardcodesBySeverity.low?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.hardcodes.lowLabel') }}</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ uniqueTypeCount }}</div>
          <div class="summary-label">{{ $t('analytics.hardcodes.uniqueTypes') }}</div>
        </div>
      </div>

      <!-- Hardcoded Values by Severity Group -->
      <div class="accordion-groups">
        <div
          v-for="(group, severity) in hardcodesBySeverity"
          :key="severity"
          v-show="group && group.length > 0"
          class="accordion-group"
        >
          <div
            class="accordion-header"
            @click="toggleGroup(String(severity))"
          >
            <div class="header-info">
              <i :class="isGroupExpanded(severity) ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">{{ formatSeverityGroup(String(severity)) }}</span>
              <span class="header-count">({{ group.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge" :class="severity">{{ severity }}</span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="isGroupExpanded(severity)" class="accordion-items">
              <div
                v-for="(hc, index) in group.slice(0, 20)"
                :key="index"
                class="list-item"
                :class="`item-${severity}`"
              >
                <div class="item-header">
                  <span class="item-type">{{ hc.type }}</span>
                  <span class="item-location">{{ hc.file }}:{{ hc.line }}</span>
                </div>
                <div class="item-body">
                  <div v-if="hc.variable_name" class="item-row">
                    <span class="item-label">{{ $t('analytics.hardcodes.variable') }}:</span>
                    <code class="item-code">{{ hc.variable_name }}</code>
                  </div>
                  <div class="item-row">
                    <span class="item-label">{{ $t('analytics.hardcodes.value') }}:</span>
                    <code class="item-code">{{ hc.value }}</code>
                  </div>
                  <div v-if="hc.suggested_env_var" class="item-row">
                    <span class="item-label">{{ $t('analytics.hardcodes.suggestedEnvVar') }}:</span>
                    <code class="item-code item-suggestion">{{ hc.suggested_env_var }}</code>
                  </div>
                </div>
              </div>
              <div v-if="group.length > 20" class="show-more">
                <span class="muted">{{ $t('analytics.hardcodes.showingOf', { shown: 20, total: group.length.toLocaleString() }) }}</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else-if="!loading"
      icon="check-circle"
      :message="$t('analytics.hardcodes.emptyMessage')"
      variant="success"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Hardcodes Section Component
 *
 * Displays hardcoded-value detection results grouped by severity.
 * Issue #5277: wire previously-fetched hardcodeAnalysis data into the UI.
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useExpansion } from '@/composables/useExpansion'
import type { HardcodedValue } from '@/composables/analytics/analyticsTypes'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()

interface Props {
  hardcodes: HardcodedValue[]
  /**
   * #5368: when true, render a spinner in place of the empty-state
   * message so users don't misread a running scan as "no results".
   */
  loading?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  export: [format: 'md' | 'json']
}>()

const groupExpansion = useExpansion<string>()
const isGroupExpanded = groupExpansion.isExpanded

const hardcodesBySeverity = computed(() => {
  const groups: Record<string, HardcodedValue[]> = { high: [], medium: [], low: [] }
  props.hardcodes.forEach(h => {
    const sev = (h.severity || '').toLowerCase()
    if (sev === 'high' || sev === 'critical') groups.high.push(h)
    else if (sev === 'medium') groups.medium.push(h)
    else groups.low.push(h)
  })
  return groups
})

const uniqueTypeCount = computed(
  () => new Set(props.hardcodes.map(h => h.type).filter(Boolean)).size,
)

const toggleGroup = (severity: string) => {
  groupExpansion.toggle(severity)
}

const formatSeverityGroup = (severity: string): string => {
  const key = `analytics.hardcodes.severityGroups.${severity}`
  const translated = t(key)
  return translated !== key ? translated : severity
}
</script>

<style scoped>
.hardcodes-section {
  margin-bottom: var(--spacing-6);
}

.hardcodes-section h3 {
  color: var(--color-warning);
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
  color: var(--color-warning);
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

.severity-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: capitalize;
}

.severity-badge.high { background: var(--color-error-bg); color: var(--color-error); }
.severity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.severity-badge.low { background: var(--color-success-bg); color: var(--color-success); }

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
  align-items: center;
  margin-bottom: var(--spacing-2);
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.item-type {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  background: var(--bg-tertiary-alpha);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.item-location {
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.item-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.item-row {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
}

.item-label {
  color: var(--text-muted);
  min-width: 100px;
  flex-shrink: 0;
}

.item-code {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  background: var(--bg-tertiary-alpha);
  padding: var(--spacing-0-5) var(--spacing-1);
  border-radius: var(--radius-default);
  word-break: break-all;
}

.item-code.item-suggestion {
  color: var(--color-success);
  background: var(--color-success-bg);
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
  border-color: var(--color-warning-dark);
  color: var(--text-primary);
}
</style>
