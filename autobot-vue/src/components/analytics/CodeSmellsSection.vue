<template>
  <div class="code-smells-section analytics-section">
    <h3>
      <i class="fas fa-bug"></i> Code Smells & Anti-Patterns
      <span v-if="codeHealthScore" class="health-badge" :class="getHealthGradeClass(codeHealthScore.grade)">
        {{ codeHealthScore.grade }} ({{ codeHealthScore.health_score }}/100)
      </span>
      <span v-if="smells.length > 0" class="total-count">
        ({{ smells.length.toLocaleString() }} found)
      </span>
    </h3>
    <div v-if="smells.length > 0" class="section-content">
      <!-- Summary Cards by Severity -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ smells.length.toLocaleString() }}</div>
          <div class="summary-label">Total</div>
        </div>
        <div class="summary-card critical">
          <div class="summary-value">{{ severitySummary.critical }}</div>
          <div class="summary-label">Critical</div>
        </div>
        <div class="summary-card high">
          <div class="summary-value">{{ severitySummary.high }}</div>
          <div class="summary-label">High</div>
        </div>
        <div class="summary-card medium">
          <div class="summary-value">{{ severitySummary.medium }}</div>
          <div class="summary-label">Medium</div>
        </div>
        <div class="summary-card low">
          <div class="summary-value">{{ severitySummary.low }}</div>
          <div class="summary-label">Low</div>
        </div>
      </div>

      <!-- Code Smells by Type (Accordion) -->
      <div class="accordion-groups">
        <div
          v-for="(group, smellType) in smellsByType"
          :key="smellType"
          class="accordion-group"
        >
          <div
            class="accordion-header"
            @click="toggleCodeSmellType(String(smellType))"
          >
            <div class="header-info">
              <i :class="expandedCodeSmellTypes[smellType] ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">{{ formatCodeSmellType(String(smellType)) }}</span>
              <span class="header-count">({{ group.smells.length.toLocaleString() }})</span>
            </div>
            <div class="header-badges">
              <span v-if="group.severityCounts.critical > 0" class="severity-badge critical">
                {{ group.severityCounts.critical }} critical
              </span>
              <span v-if="group.severityCounts.high > 0" class="severity-badge high">
                {{ group.severityCounts.high }} high
              </span>
              <span v-if="group.severityCounts.medium > 0" class="severity-badge medium">
                {{ group.severityCounts.medium }} medium
              </span>
              <span v-if="group.severityCounts.low > 0" class="severity-badge low">
                {{ group.severityCounts.low }} low
              </span>
            </div>
          </div>

          <!-- Expanded smell items -->
          <transition name="accordion">
            <div v-if="expandedCodeSmellTypes[smellType]" class="accordion-items">
              <div
                v-for="(smell, idx) in group.smells.slice(0, 20)"
                :key="idx"
                class="list-item"
                :class="getItemSeverityClass(smell.severity)"
              >
                <div class="item-header">
                  <span class="item-severity" :class="smell.severity?.toLowerCase()">
                    {{ smell.severity || 'unknown' }}
                  </span>
                </div>
                <div class="item-description">{{ smell.description }}</div>
                <div class="item-location">
                  {{ smell.file_path }}{{ smell.line_number ? ':' + smell.line_number : '' }}
                </div>
                <div v-if="smell.suggestion" class="item-suggestion">{{ smell.suggestion }}</div>
              </div>
              <div v-if="group.smells.length > 20" class="show-more">
                <span class="muted">Showing 20 of {{ group.smells.length.toLocaleString() }} {{ formatCodeSmellType(String(smellType)) }} issues</span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else
      icon="fas fa-sparkles"
      message="No code smells detected in indexed data. Run codebase indexing first."
      variant="info"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Code Smells Section Component
 *
 * Displays code smells and anti-patterns grouped by type.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface CodeSmell {
  severity: string
  description: string
  file_path: string
  line_number?: number
  suggestion?: string
  smell_type?: string
}

interface CodeHealthScore {
  grade: string
  health_score: number
}

interface Props {
  smells: CodeSmell[]
  codeHealthScore: CodeHealthScore | null
}

const props = defineProps<Props>()

const expandedCodeSmellTypes = ref<Record<string, boolean>>({})

const severitySummary = computed(() => {
  const counts = { critical: 0, high: 0, medium: 0, low: 0 }
  props.smells.forEach(s => {
    const sev = (s.severity || 'low').toLowerCase()
    if (counts[sev as keyof typeof counts] !== undefined) {
      counts[sev as keyof typeof counts]++
    }
  })
  return counts
})

const smellsByType = computed(() => {
  const groups: Record<string, { smells: CodeSmell[], severityCounts: Record<string, number> }> = {}
  props.smells.forEach(s => {
    const type = s.smell_type || 'unknown'
    if (!groups[type]) {
      groups[type] = { smells: [], severityCounts: { critical: 0, high: 0, medium: 0, low: 0 } }
    }
    groups[type].smells.push(s)
    const sev = (s.severity || 'low').toLowerCase()
    if (groups[type].severityCounts[sev] !== undefined) {
      groups[type].severityCounts[sev]++
    }
  })
  return groups
})

const toggleCodeSmellType = (type: string) => {
  expandedCodeSmellTypes.value[type] = !expandedCodeSmellTypes.value[type]
}

const formatCodeSmellType = (type: string): string => {
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const getHealthGradeClass = (grade: string): string => {
  if (!grade) return ''
  const g = grade.toUpperCase()
  if (g === 'A' || g === 'A+') return 'grade-a'
  if (g === 'B') return 'grade-b'
  if (g === 'C') return 'grade-c'
  if (g === 'D') return 'grade-d'
  return 'grade-f'
}

const getItemSeverityClass = (severity: string): string => {
  return `item-${(severity || 'low').toLowerCase()}`
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.code-smells-section {
  margin-bottom: var(--spacing-6);
}

.code-smells-section h3 {
  color: var(--color-info);
  margin-bottom: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  flex-wrap: wrap;
}

.health-badge {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
}

.grade-a { background: var(--color-success-bg); color: var(--color-success); }
.grade-b { background: var(--chart-light-green-bg); color: var(--chart-light-green); }
.grade-c { background: var(--color-warning-bg); color: var(--color-warning); }
.grade-d { background: var(--chart-orange-bg); color: var(--chart-orange); }
.grade-f { background: var(--color-error-bg); color: var(--color-error); }

.total-count {
  font-size: 0.8em;
  color: var(--text-tertiary);
}

.section-content {
  background: var(--bg-overlay);
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

.summary-card.total { background: var(--bg-tertiary); }
.summary-card.critical { background: var(--color-error-bg); }
.summary-card.high { background: var(--chart-orange-bg); }
.summary-card.medium { background: var(--color-warning-bg); }
.summary-card.low { background: var(--color-success-bg); }

.summary-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.accordion-group {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-in-out);
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
  color: var(--text-primary);
}

.header-count {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.header-badges {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.severity-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.severity-badge.critical { background: var(--color-error-bg); color: var(--color-error); }
.severity-badge.high { background: var(--chart-orange-bg); color: var(--chart-orange); }
.severity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.severity-badge.low { background: var(--color-success-bg); color: var(--color-success); }

.accordion-items {
  padding: 0 var(--spacing-4) var(--spacing-4);
}

.list-item {
  background: var(--bg-overlay);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-2);
  border-left: 3px solid var(--border-default);
}

.list-item.item-critical { border-left-color: var(--color-error); }
.list-item.item-high { border-left-color: var(--chart-orange); }
.list-item.item-medium { border-left-color: var(--color-warning); }
.list-item.item-low { border-left-color: var(--color-success); }

.item-header {
  margin-bottom: var(--spacing-2);
}

.item-severity {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.item-severity.critical { background: var(--color-error-bg); color: var(--color-error); }
.item-severity.high { background: var(--chart-orange-bg); color: var(--chart-orange); }
.item-severity.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.item-severity.low { background: var(--color-success-bg); color: var(--color-success); }

.item-description {
  color: var(--text-primary);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-1-5);
}

.item-location {
  color: var(--text-secondary);
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
  color: var(--text-tertiary);
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
