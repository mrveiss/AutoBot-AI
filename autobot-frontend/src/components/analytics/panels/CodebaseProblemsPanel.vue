<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Problems Report Section -->
<template>
  <div class="problems-section analytics-section">
    <h3>
      <i class="fas fa-exclamation-triangle"></i>
      {{ $t('analytics.codebase.problems.codeProblems') }}
      <span v-if="problemsReport && problemsReport.length > 0" class="total-count">
        ({{ problemsReport.length.toLocaleString() }} total)
      </span>
      <!-- Issue #609: Section Export Buttons -->
      <div class="section-export-buttons">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :disabled="!problemsReport || problemsReport.length === 0"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
        >
          <i class="fas fa-file-alt"></i> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :disabled="!problemsReport || problemsReport.length === 0"
          :title="$t('analytics.codebase.actions.exportJson')"
        >
          <i class="fas fa-file-code"></i> JSON
        </button>
      </div>
    </h3>
    <div v-if="problemsReport && problemsReport.length > 0" class="section-content">
      <!-- Severity Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ problemsReport.length.toLocaleString() }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.stats.total') }}</div>
        </div>
        <div
          v-for="(problems, severity) in problemsBySeverity"
          :key="severity"
          class="summary-card"
          :class="severity"
        >
          <div class="summary-value">{{ problems.length.toLocaleString() }}</div>
          <div class="summary-label">
            {{ String(severity).charAt(0).toUpperCase() + String(severity).slice(1) }}
          </div>
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
              <i
                :class="expandedProblemTypes[type]
                  ? 'fas fa-chevron-down'
                  : 'fas fa-chevron-right'"
              ></i>
              <span class="header-name">{{ formatProblemType(String(type)) }}</span>
              <span class="header-count">
                ({{ typeData.problems.length.toLocaleString() }})
              </span>
            </div>
            <div class="header-badges">
              <span
                v-if="typeData.severityCounts.critical"
                class="severity-badge critical"
              >
                {{ typeData.severityCounts.critical }}
                {{ $t('analytics.codebase.severity.critical') }}
              </span>
              <span
                v-if="typeData.severityCounts.high"
                class="severity-badge high"
              >
                {{ typeData.severityCounts.high }}
                {{ $t('analytics.codebase.severity.high') }}
              </span>
              <span
                v-if="typeData.severityCounts.medium"
                class="severity-badge medium"
              >
                {{ typeData.severityCounts.medium }}
                {{ $t('analytics.codebase.severity.medium') }}
              </span>
              <span
                v-if="typeData.severityCounts.low"
                class="severity-badge low"
              >
                {{ typeData.severityCounts.low }}
                {{ $t('analytics.codebase.severity.low') }}
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
                  <span
                    class="item-severity"
                    :class="problem.severity?.toLowerCase()"
                  >
                    {{ problem.severity || 'unknown' }}
                  </span>
                </div>
                <div class="item-description">{{ problem.description }}</div>
                <div class="item-location">
                  {{ problem.file_path }}{{ problem.line_number ? ':' + problem.line_number : '' }}
                </div>
                <div v-if="problem.suggestion" class="item-suggestion">
                  {{ problem.suggestion }}
                </div>
              </div>
              <div v-if="typeData.problems.length > 20" class="show-more">
                <span class="muted">
                  Showing 20 of {{ typeData.problems.length.toLocaleString() }}
                  {{ formatProblemType(String(type)) }} issues
                </span>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <EmptyState
      v-else
      icon="fas fa-check-circle"
      :message="$t('analytics.codebase.problems.noProblems')"
      variant="success"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface Problem {
  severity: string
  type: string
  message: string
  description?: string
  file_path: string
  line?: number
  line_number?: number
  category?: string
  suggestion?: string
}

interface ProblemGroup {
  problems: Problem[]
  severityCounts: {
    critical: number
    high: number
    medium: number
    low: number
  }
}

const props = defineProps<{
  problemsReport: Problem[]
}>()

const emit = defineEmits<{
  export: [format: string]
}>()

const expandedProblemTypes = ref<Record<string, boolean>>({})

const problemsBySeverity = computed((): Record<string, Problem[]> => {
  if (!props.problemsReport || props.problemsReport.length === 0) return {}
  const grouped: Record<string, Problem[]> = {}
  const severityOrder = ['critical', 'high', 'medium', 'low']

  for (const problem of props.problemsReport) {
    const severity = problem.severity?.toLowerCase() || 'low'
    if (!grouped[severity]) {
      grouped[severity] = []
    }
    grouped[severity].push(problem)
  }

  const ordered: Record<string, Problem[]> = {}
  for (const sev of severityOrder) {
    if (grouped[sev]) {
      ordered[sev] = grouped[sev]
    }
  }
  return ordered
})

const problemsByType = computed((): Record<string, ProblemGroup> => {
  if (!props.problemsReport || props.problemsReport.length === 0) return {}
  const grouped: Record<string, ProblemGroup> = {}

  for (const problem of props.problemsReport) {
    const type = problem.type || 'unknown'
    if (!grouped[type]) {
      grouped[type] = {
        problems: [],
        severityCounts: { critical: 0, high: 0, medium: 0, low: 0 },
      }
    }
    grouped[type].problems.push(problem)
    const sev = problem.severity?.toLowerCase() || 'low'
    if (sev in grouped[type].severityCounts) {
      grouped[type].severityCounts[
        sev as keyof typeof grouped[typeof type]['severityCounts']
      ]++
    }
  }

  return Object.fromEntries(
    Object.entries(grouped).sort(
      (a, b) => b[1].problems.length - a[1].problems.length,
    ),
  )
})

function toggleProblemType(type: string): void {
  expandedProblemTypes.value[type] = !expandedProblemTypes.value[type]
}

function formatProblemType(type: string | undefined): string {
  return (
    type
      ?.replace(/_/g, ' ')
      .replace(/\b\w/g, (l: string) => l.toUpperCase()) || 'Unknown'
  )
}

function getItemSeverityClass(severity: string | undefined): string {
  switch (severity?.toLowerCase()) {
    case 'critical':
      return 'item-critical'
    case 'high':
      return 'item-high'
    case 'medium':
      return 'item-medium'
    case 'low':
      return 'item-low'
    case 'info':
      return 'item-info'
    default:
      return 'item-unknown'
  }
}
</script>

<style scoped>
.problems-section {
  margin-bottom: 32px;
}

.problems-section h3 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 1.1em;
  flex-wrap: wrap;
}

.total-count {
  font-size: 0.85em;
  color: var(--text-muted);
  font-weight: normal;
}

/* Issue #609: Section Export Buttons */
.section-export-buttons {
  display: inline-flex;
  gap: 4px;
  margin-left: 10px;
}

.export-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--bg-tertiary);
  color: var(--text-muted);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.export-btn:hover {
  background: var(--bg-tertiary);
  color: var(--color-info);
  border-color: var(--color-info);
}

.export-btn i {
  font-size: 0.7rem;
}

.section-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
}

.summary-card {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid var(--bg-tertiary);
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.summary-card:hover {
  transform: translateY(-2px);
}

.summary-value {
  font-size: 1.8em;
  font-weight: 700;
  color: var(--text-on-primary);
}

.summary-label {
  font-size: 0.75em;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-top: 4px;
}

.summary-card.total { border-color: var(--chart-indigo); }
.summary-card.total .summary-value { color: var(--chart-indigo-light); }
.summary-card.critical { border-color: var(--color-error); }
.summary-card.critical .summary-value { color: var(--color-error); }
.summary-card.high { border-color: var(--chart-orange); }
.summary-card.high .summary-value { color: var(--chart-orange); }
.summary-card.medium { border-color: var(--color-warning); }
.summary-card.medium .summary-value { color: var(--color-warning); }
.summary-card.low { border-color: var(--chart-green); }
.summary-card.low .summary-value { color: var(--chart-green); }

/* Accordion */
.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accordion-group {
  background: var(--bg-card);
  border-radius: 8px;
  border: 1px solid var(--bg-tertiary);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.accordion-header:hover {
  background: var(--bg-tertiary);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-name {
  font-weight: 600;
  color: var(--text-secondary);
}

.header-count {
  color: var(--text-muted);
  font-size: 0.9em;
}

.header-badges {
  display: flex;
  gap: 6px;
}

.severity-badge {
  font-size: 0.7em;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.severity-badge.critical { background: var(--color-error-bg); color: var(--color-error); }
.severity-badge.high { background: var(--color-warning-bg); color: var(--color-warning); }
.severity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.severity-badge.low { background: var(--color-success-bg); color: var(--color-success); }

.accordion-items {
  padding: 8px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-item {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
  border-left: 3px solid var(--text-tertiary);
}

.list-item.item-critical { border-left-color: var(--color-error); }
.list-item.item-high { border-left-color: var(--chart-orange); }
.list-item.item-medium { border-left-color: var(--color-warning); }
.list-item.item-low { border-left-color: var(--color-success); }
.list-item.item-info { border-left-color: var(--chart-blue); }

.item-header {
  margin-bottom: 8px;
}

.item-severity {
  font-size: 0.7em;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.item-severity.critical { background: var(--color-error-bg); color: var(--color-error); }
.item-severity.high { background: var(--color-warning-bg); color: var(--color-warning); }
.item-severity.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.item-severity.low { background: var(--color-success-bg); color: var(--color-success); }

.item-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  margin-bottom: 4px;
}

.item-location {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.8em;
}

.item-suggestion {
  color: var(--color-warning-light);
  font-size: 0.8em;
  margin-top: 6px;
  font-style: italic;
}

.show-more {
  text-align: center;
  padding: 8px;
}

.muted {
  color: var(--text-tertiary);
  font-style: italic;
  font-size: 0.9em;
}

.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease-in-out;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
