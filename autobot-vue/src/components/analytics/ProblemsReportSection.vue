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
.problems-section {
  margin-bottom: 24px;
}

.problems-section h3 {
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
.summary-card.critical { background: rgba(244, 67, 54, 0.2); }
.summary-card.high { background: rgba(255, 152, 0, 0.2); }
.summary-card.medium { background: rgba(255, 193, 7, 0.2); }
.summary-card.low { background: rgba(76, 175, 80, 0.2); }

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

.header-badges {
  display: flex;
  gap: 8px;
}

.severity-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.severity-badge.critical { background: rgba(244, 67, 54, 0.3); color: #f44336; }
.severity-badge.high { background: rgba(255, 152, 0, 0.3); color: #ff9800; }
.severity-badge.medium { background: rgba(255, 193, 7, 0.3); color: #ffc107; }
.severity-badge.low { background: rgba(76, 175, 80, 0.3); color: #4caf50; }

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

.list-item.item-critical { border-left-color: #f44336; }
.list-item.item-high { border-left-color: #ff9800; }
.list-item.item-medium { border-left-color: #ffc107; }
.list-item.item-low { border-left-color: #4caf50; }

.item-header {
  margin-bottom: 8px;
}

.item-severity {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.item-severity.critical { background: rgba(244, 67, 54, 0.3); color: #f44336; }
.item-severity.high { background: rgba(255, 152, 0, 0.3); color: #ff9800; }
.item-severity.medium { background: rgba(255, 193, 7, 0.3); color: #ffc107; }
.item-severity.low { background: rgba(76, 175, 80, 0.3); color: #4caf50; }

.item-description {
  color: white;
  font-size: 13px;
  margin-bottom: 6px;
}

.item-location {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  font-family: monospace;
}

.item-suggestion {
  color: #00d4ff;
  font-size: 12px;
  margin-top: 6px;
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
