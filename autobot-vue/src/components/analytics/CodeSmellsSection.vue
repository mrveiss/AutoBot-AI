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
.code-smells-section {
  margin-bottom: 24px;
}

.code-smells-section h3 {
  color: #00d4ff;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.health-badge {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
}

.grade-a { background: rgba(76, 175, 80, 0.3); color: #4caf50; }
.grade-b { background: rgba(139, 195, 74, 0.3); color: #8bc34a; }
.grade-c { background: rgba(255, 193, 7, 0.3); color: #ffc107; }
.grade-d { background: rgba(255, 152, 0, 0.3); color: #ff9800; }
.grade-f { background: rgba(244, 67, 54, 0.3); color: #f44336; }

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
  flex-wrap: wrap;
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
