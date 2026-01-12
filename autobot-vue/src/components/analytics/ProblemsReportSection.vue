<template>
  <div class="problems-section analytics-section">
    <h3>
      <i class="fas fa-exclamation-triangle"></i> Code Problems
      <span v-if="problems && problems.length > 0" class="total-count">
        ({{ problems.length.toLocaleString() }} total)
      </span>
    </h3>
    <div v-if="problems && problems.length > 0" class="section-content">
      <!-- Severity Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ problems.length.toLocaleString() }}</div>
          <div class="summary-label">Total</div>
        </div>
        <div
          v-for="(problemList, severity) in problemsBySeverity"
          :key="severity"
          class="summary-card"
          :class="severity"
        >
          <div class="summary-value">{{ problemList.length.toLocaleString() }}</div>
          <div class="summary-label">{{ capitalize(severity) }}</div>
        </div>
      </div>

      <!-- Grouped by Type (Accordion) -->
      <div class="accordion-groups">
        <div
          v-for="(typeData, type) in problemsByType"
          :key="type"
          class="accordion-group"
        >
          <div
            class="accordion-header"
            @click="toggleProblemType(String(type))"
          >
            <div class="header-info">
              <i :class="expandedProblemTypes[type] ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">{{ formatProblemType(String(type)) }}</span>
              <span class="header-count">({{ typeData.problems.length.toLocaleString() }})</span>
            </div>
            <div class="header-badges">
              <span v-if="typeData.severityCounts.critical" class="severity-badge critical">
                {{ typeData.severityCounts.critical }} critical
              </span>
              <span v-if="typeData.severityCounts.high" class="severity-badge high">
                {{ typeData.severityCounts.high }} high
              </span>
              <span v-if="typeData.severityCounts.medium" class="severity-badge medium">
                {{ typeData.severityCounts.medium }} medium
              </span>
              <span v-if="typeData.severityCounts.low" class="severity-badge low">
                {{ typeData.severityCounts.low }} low
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expandedProblemTypes[type]" class="accordion-items">
              <div
                v-for="(problem, index) in typeData.problems.slice(0, 20)"
                :key="index"
                class="list-item"
                :class="getItemSeverityClass(problem.severity)"
              >
                <div class="item-header">
                  <span class="item-severity" :class="problem.severity?.toLowerCase()">
                    {{ problem.severity || 'unknown' }}
                  </span>
                </div>
                <div class="item-description">{{ problem.description }}</div>
                <div class="item-location">{{ problem.file_path }}{{ problem.line_number ? ':' + problem.line_number : '' }}</div>
                <div v-if="problem.suggestion" class="item-suggestion">{{ problem.suggestion }}</div>
              </div>
              <div v-if="typeData.problems.length > 20" class="show-more">
                <span class="muted">Showing 20 of {{ typeData.problems.length.toLocaleString() }} {{ formatProblemType(String(type)) }} issues</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else
      icon="fas fa-check-circle"
      message="No code problems detected or analysis not run yet."
      variant="success"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Problems Report Section Component
 *
 * Displays code problems grouped by type and severity.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface Problem {
  severity: string
  description: string
  file_path: string
  line_number?: number
  suggestion?: string
  problem_type?: string
}

interface Props {
  problems: Problem[]
}

const props = defineProps<Props>()

const expandedProblemTypes = ref<Record<string, boolean>>({})

const problemsBySeverity = computed(() => {
  const groups: Record<string, Problem[]> = {
    critical: [],
    high: [],
    medium: [],
    low: []
  }
  props.problems.forEach(p => {
    const sev = (p.severity || 'low').toLowerCase()
    if (groups[sev]) groups[sev].push(p)
  })
  return groups
})

const problemsByType = computed(() => {
  const groups: Record<string, { problems: Problem[], severityCounts: Record<string, number> }> = {}
  props.problems.forEach(p => {
    const type = p.problem_type || 'unknown'
    if (!groups[type]) {
      groups[type] = { problems: [], severityCounts: { critical: 0, high: 0, medium: 0, low: 0 } }
    }
    groups[type].problems.push(p)
    const sev = (p.severity || 'low').toLowerCase()
    if (groups[type].severityCounts[sev] !== undefined) {
      groups[type].severityCounts[sev]++
    }
  })
  return groups
})

const toggleProblemType = (type: string) => {
  expandedProblemTypes.value[type] = !expandedProblemTypes.value[type]
}

const formatProblemType = (type: string): string => {
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const capitalize = (str: string): string => {
  return str.charAt(0).toUpperCase() + str.slice(1)
}

const getItemSeverityClass = (severity: string): string => {
  return `item-${(severity || 'low').toLowerCase()}`
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.problems-section {
  margin-bottom: var(--spacing-6);
}

.problems-section h3 {
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
.summary-card.critical { background: var(--color-error-bg); }
.summary-card.high { background: var(--color-warning-bg); }
.summary-card.medium { background: var(--color-warning-bg); }
.summary-card.low { background: var(--color-success-bg); }

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

.header-badges {
  display: flex;
  gap: var(--spacing-2);
}

.severity-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.severity-badge.critical { background: var(--color-error-bg); color: var(--color-error); }
.severity-badge.high { background: var(--color-warning-bg); color: var(--color-warning); }
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

.list-item.item-critical { border-left-color: var(--color-error); }
.list-item.item-high { border-left-color: var(--color-warning); }
.list-item.item-medium { border-left-color: var(--color-warning); }
.list-item.item-low { border-left-color: var(--color-success); }

.item-header {
  margin-bottom: var(--spacing-2);
}

.item-severity {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 10px;
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.item-severity.critical { background: var(--color-error-bg); color: var(--color-error); }
.item-severity.high { background: var(--color-warning-bg); color: var(--color-warning); }
.item-severity.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.item-severity.low { background: var(--color-success-bg); color: var(--color-success); }

.item-description {
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-1-5);
}

.item-location {
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.item-suggestion {
  color: var(--color-info);
  font-size: var(--text-xs);
  margin-top: var(--spacing-1-5);
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
