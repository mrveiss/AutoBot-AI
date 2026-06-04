<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Bug Prediction section (#538) -->
<template>
  <div class="bug-prediction-section analytics-section">
    <h3>
      <Icon name="bug" /> {{ $t('analytics.codebase.bugPrediction.title') }}
      <span v-if="analysis" class="total-count">
        ({{ atRiskCount }} files need attention)
      </span>
      <button
        @click="emit('refresh')"
        :disabled="loading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
      </button>
      <div class="section-export-buttons" v-if="analysis">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
        >
          <Icon name="file-alt" /> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportJson')"
        >
          <Icon name="file-code" /> JSON
        </button>
      </div>
    </h3>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <Icon name="spinner" class="animate-spin" />
      <span v-if="taskCurrentStep">{{ taskCurrentStep }}</span>
      <span v-else>{{ $t('analytics.codebase.bugPrediction.analyzing') }}</span>
      <div v-if="taskProgress" class="mini-progress">
        <div class="mini-progress-bar" :style="{ width: taskProgress + '%' }"></div>
      </div>
    </div>

    <!-- Interrupted State -->
    <div v-if="!loading && wasInterrupted" class="interrupted-state">
      <Icon name="info-circle" />
      {{ $t('analytics.codebase.bugPrediction.interrupted') }}
      <button @click="emit('refresh')" class="rerun-btn">
        <Icon name="redo" /> {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <!-- Error State -->
    <div v-else-if="!loading && error" class="error-state">
      <Icon name="exclamation-triangle" /> {{ error }}
      <button @click="emit('refresh')" class="btn-link">
        {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <!-- Analysis Results -->
    <div v-else-if="analysis && analysis.files.length > 0" class="section-content">
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ analysis.analyzed_files }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.filesAnalyzed') }}</div>
        </div>
        <div
          class="summary-card critical"
          :class="{ clickable: analysis.high_risk_count > 0 }"
          @click="analysis.high_risk_count > 0 && setFilter('high')"
        >
          <div class="summary-value">{{ analysis.high_risk_count }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.highRisk') }}</div>
        </div>
        <div class="summary-card warning clickable" @click="setFilter('medium')">
          <div class="summary-value">{{ mediumRiskCount }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.mediumRisk') }}</div>
        </div>
        <div class="summary-card success clickable" @click="setFilter('low')">
          <div class="summary-value">{{ lowRiskCount }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.lowRisk') }}</div>
        </div>
      </div>

      <!-- Top Risk Factors Summary -->
      <div v-if="topRiskFactors.length > 0" class="top-risk-factors-summary">
        <h4>
          <Icon name="exclamation-circle" />
          {{ $t('analytics.codebase.bugPrediction.topIssues') }}
        </h4>
        <div class="risk-factors-grid">
          <div
            v-for="factor in topRiskFactors"
            :key="factor.name"
            class="risk-factor-card"
            :class="factor.severity"
          >
            <div class="factor-icon">
              <Icon :name="getRiskFactorIcon(factor.name)" />
            </div>
            <div class="factor-details">
              <div class="factor-name">{{ formatFactorName(factor.name) }}</div>
              <div class="factor-count">{{ factor.count }} files affected</div>
              <div class="factor-description">{{ getRiskFactorDescription(factor.name) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Risk Filter Tabs -->
      <div class="risk-filter-tabs">
        <button
          :class="{ active: activeFilter === 'all' }"
          @click="activeFilter = 'all'; visibleCount = PAGE_SIZE"
        >
          All ({{ analysis.files.length }})
        </button>
        <button
          :class="{ active: activeFilter === 'high' }"
          @click="activeFilter = 'high'; visibleCount = PAGE_SIZE"
          :disabled="analysis.high_risk_count === 0"
        >
          High ({{ analysis.high_risk_count }})
        </button>
        <button
          :class="{ active: activeFilter === 'medium' }"
          @click="activeFilter = 'medium'; visibleCount = PAGE_SIZE"
        >
          Medium ({{ mediumRiskCount }})
        </button>
        <button
          :class="{ active: activeFilter === 'low' }"
          @click="activeFilter = 'low'; visibleCount = PAGE_SIZE"
        >
          Low ({{ lowRiskCount }})
        </button>
      </div>

      <!-- Files List with Detailed Info -->
      <div class="risk-files-list detailed">
        <h4>
          <Icon name="file-code" />
          {{
            activeFilter === 'all'
              ? 'Analyzed Files'
              : `${activeFilter.charAt(0).toUpperCase() + activeFilter.slice(1)} Risk Files`
          }}
          <span class="file-count">({{ filteredFiles.length }} files)</span>
        </h4>

        <div v-if="filteredFiles.length === 0" class="no-files-message">
          <Icon name="check-circle" />
          {{ $t('analytics.codebase.bugPrediction.noFilesInCategory') }}
        </div>

        <div
          v-for="(file, index) in filteredFiles.slice(0, visibleCount)"
          :key="'risk-file-' + index"
          class="risk-file-item"
          :class="[getRiskClass(file.risk_score), { expanded: expandedFiles.has(file.file_path) }]"
        >
          <div class="file-header" @click="toggleFileExpand(file.file_path)">
            <div class="file-info">
              <span class="risk-score-badge" :class="getRiskClass(file.risk_score)">
                {{ file.risk_score.toFixed(0) }}
              </span>
              <span class="file-path">{{ file.file_path }}</span>
              <span class="risk-level-tag" :class="file.risk_level">{{ file.risk_level }}</span>
            </div>
            <div class="expand-icon">
              <Icon :name="expandedFiles.has(file.file_path) ? 'chevron-up' : 'chevron-down'" />
            </div>
          </div>

          <div class="quick-risk-indicators">
            <span
              v-if="file.factors?.complexity >= 80"
              class="indicator high"
              :title="$t('analytics.codebase.risk.highComplexity')"
            >
              <Icon name="project-diagram" />
              {{ $t('analytics.codebase.risk.complex') }}
            </span>
            <span
              v-if="file.factors?.change_frequency >= 80"
              class="indicator warning"
              :title="$t('analytics.codebase.risk.frequentlyChanged')"
            >
              <Icon name="history" />
              {{ $t('analytics.codebase.risk.unstable') }}
            </span>
            <span
              v-if="file.factors?.file_size >= 70"
              class="indicator info"
              :title="$t('analytics.codebase.risk.largeFile')"
            >
              <Icon name="file-alt" />
              {{ $t('analytics.codebase.risk.large') }}
            </span>
            <span
              v-if="file.factors?.bug_history > 0"
              class="indicator critical"
              :title="$t('analytics.codebase.risk.hasBugHistory')"
            >
              <Icon name="bug" />
              {{ $t('analytics.codebase.risk.bugHistory') }}
            </span>
            <span
              v-if="file.factors?.test_coverage === 50"
              class="indicator muted"
              :title="$t('analytics.codebase.risk.noTestsDetected')"
            >
              <Icon name="vial" />
              {{ $t('analytics.codebase.risk.noTests') }}
            </span>
          </div>

          <div v-if="expandedFiles.has(file.file_path)" class="file-details">
            <div class="detail-section">
              <h5>
                <Icon name="chart-bar" />
                {{ $t('analytics.codebase.bugPrediction.riskFactorBreakdown') }}
              </h5>
              <div class="factors-breakdown">
                <div
                  v-for="(value, factor) in file.factors"
                  :key="factor"
                  class="factor-row"
                  :class="{
                    'high-value': value >= 80,
                    'medium-value': value >= 50 && value < 80,
                  }"
                >
                  <div class="factor-label">
                    <i :class="getRiskFactorIcon(String(factor))"></i>
                    {{ formatFactorName(String(factor)) }}
                  </div>
                  <div class="factor-bar-container">
                    <div
                      class="factor-bar"
                      :style="{ width: value + '%' }"
                      :class="getFactorBarClass(value)"
                    ></div>
                  </div>
                  <div class="factor-value">
                    {{ typeof value === 'number' ? value.toFixed(0) : value }}
                  </div>
                </div>
              </div>
            </div>

            <div v-if="file.prevention_tips && file.prevention_tips.length > 0" class="detail-section">
              <h5>
                <Icon name="lightbulb" />
                {{ $t('analytics.codebase.bugPrediction.recommendedFixes') }}
              </h5>
              <ul class="tips-list">
                <li v-for="(tip, tipIndex) in file.prevention_tips" :key="tipIndex">
                  <Icon name="wrench" /> {{ tip }}
                </li>
              </ul>
            </div>

            <div v-if="file.suggested_tests && file.suggested_tests.length > 0" class="detail-section">
              <h5>
                <Icon name="vial" />
                {{ $t('analytics.codebase.bugPrediction.suggestedTests') }}
              </h5>
              <ul class="tests-list">
                <li v-for="(test, testIndex) in file.suggested_tests" :key="testIndex">
                  <Icon name="vial" /> {{ test }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div v-if="filteredFiles.length > visibleCount" class="show-more-container">
          <button @click="visibleCount += PAGE_SIZE" class="show-more-btn">
            <Icon name="chevron-down" />
            Show More
            ({{ Math.min(PAGE_SIZE, filteredFiles.length - visibleCount) }} of
            {{ filteredFiles.length - visibleCount }} remaining)
          </button>
        </div>
      </div>

      <div v-if="analysis.timestamp" class="scan-timestamp">
        <Icon name="clock" />
        {{ $t('analytics.codebase.bugPrediction.lastAnalysis') }}:
        {{ formatTimestamp(analysis.timestamp) }}
      </div>
    </div>

    <div
      v-else-if="analysis && analysis.files.length === 0"
      class="success-state"
    >
      <Icon name="check-circle" />
      {{ $t('analytics.codebase.bugPrediction.noFilesAnalyzed') }}
    </div>

    <EmptyState
      v-else
      icon="bug"
      :message="$t('analytics.codebase.bugPrediction.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'

const { t } = useI18n()

interface BugPredictionFile {
  file_path: string
  risk_score: number
  risk_level: string
  factors: Record<string, number>
  prevention_tips?: string[]
  suggested_tests?: string[]
}

interface BugPredictionResult {
  timestamp: string
  total_files: number
  analyzed_files: number
  high_risk_count: number
  files: BugPredictionFile[]
}

const props = defineProps<{
  analysis: BugPredictionResult | null
  loading: boolean
  error: string | null
  wasInterrupted: boolean
  taskCurrentStep?: string | null
  taskProgress?: number
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: 'md' | 'json']
}>()

const PAGE_SIZE = 50
const activeFilter = ref<'all' | 'high' | 'medium' | 'low'>('all')
const visibleCount = ref(PAGE_SIZE)
const fileExpansion = useExpansion<string>()
const expandedFiles = fileExpansion.expanded

// Single pass over the file list to derive all three risk-bucket counts.
// Replaces three separate .filter() traversals that each iterated the full
// array independently on every reactive update.
const riskCounts = computed((): { high: number; medium: number; low: number } => {
  if (!props.analysis) return { high: 0, medium: 0, low: 0 }
  let high = 0, medium = 0, low = 0
  for (const f of props.analysis.files) {
    if (f.risk_score >= 60) high++
    else if (f.risk_score >= 40) medium++
    else low++
  }
  return { high, medium, low }
})

const mediumRiskCount = computed(() => riskCounts.value.medium)
const lowRiskCount = computed(() => riskCounts.value.low)
const atRiskCount = computed(() => riskCounts.value.high + riskCounts.value.medium)

const filteredFiles = computed((): BugPredictionFile[] => {
  if (!props.analysis) return []
  const files = props.analysis.files
  let filtered: BugPredictionFile[]

  switch (activeFilter.value) {
    case 'high':
      filtered = files.filter((f) => f.risk_score >= 60)
      break
    case 'medium':
      filtered = files.filter((f) => f.risk_score >= 40 && f.risk_score < 60)
      break
    case 'low':
      filtered = files.filter((f) => f.risk_score < 40)
      break
    default:
      filtered = [...files]
  }
  return filtered.sort((a, b) => b.risk_score - a.risk_score)
})

interface TopRiskFactor {
  name: string
  count: number
  severity: 'critical' | 'high' | 'medium' | 'low'
}

const topRiskFactors = computed((): TopRiskFactor[] => {
  if (!props.analysis) return []
  const counts: Record<string, number> = {
    complexity: 0, change_frequency: 0, file_size: 0, bug_history: 0, test_coverage: 0,
  }
  for (const file of props.analysis.files) {
    if (!file.factors) continue
    if (file.factors.complexity >= 80) counts.complexity++
    if (file.factors.change_frequency >= 80) counts.change_frequency++
    if (file.factors.file_size >= 70) counts.file_size++
    if (file.factors.bug_history > 0) counts.bug_history++
    if (file.factors.test_coverage === 50) counts.test_coverage++
  }
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => ({
      name,
      count,
      severity: getSeverityForFactor(name, count),
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 4)
})

function setFilter(filter: 'high' | 'medium' | 'low'): void {
  activeFilter.value = activeFilter.value === filter ? 'all' : filter
  visibleCount.value = PAGE_SIZE
}

function toggleFileExpand(filePath: string): void {
  fileExpansion.toggle(filePath)
}

function getSeverityForFactor(
  factor: string,
  count: number
): 'critical' | 'high' | 'medium' | 'low' {
  if (factor === 'bug_history' && count > 0) return 'critical'
  if (count > 50) return 'high'
  if (count > 20) return 'medium'
  return 'low'
}

function getRiskFactorIcon(factor: string): string {
  const icons: Record<string, string> = {
    complexity: 'project-diagram',
    change_frequency: 'history',
    file_size: 'file-alt',
    bug_history: 'bug',
    test_coverage: 'vial',
    dependency_count: 'sitemap',
  }
  return icons[factor] || 'exclamation-circle'
}

function getRiskFactorDescription(factor: string): string {
  const descriptions: Record<string, string> = {
    complexity: t('analytics.codebase.bugPrediction.factors.complexity'),
    change_frequency: t('analytics.codebase.bugPrediction.factors.changeFrequency'),
    file_size: t('analytics.codebase.bugPrediction.factors.fileSize'),
    bug_history: t('analytics.codebase.bugPrediction.factors.bugHistory'),
    test_coverage: t('analytics.codebase.bugPrediction.factors.testCoverage'),
    dependency_count: t('analytics.codebase.bugPrediction.factors.dependencyCount'),
  }
  return descriptions[factor] || t('analytics.codebase.bugPrediction.factors.default')
}

function getRiskClass(riskScore: number): string {
  if (riskScore >= 80) return 'item-critical'
  if (riskScore >= 60) return 'item-warning'
  if (riskScore >= 40) return 'item-info'
  return 'item-success'
}

function getFactorBarClass(value: number): string {
  if (value >= 80) return 'bar-critical'
  if (value >= 50) return 'bar-warning'
  return 'bar-ok'
}

function formatFactorName(factor: string): string {
  return factor.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
}

function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) return 'Unknown'
  try {
    return new Date(timestamp).toLocaleString()
  } catch {
    return String(timestamp)
  }
}
</script>

<style scoped>
.bug-prediction-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  contain: layout style;}

.bug-prediction-section h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
  font-size: 1.2em;
  font-weight: 600;
}

.bug-prediction-section h3 i {
  color: var(--color-error);
}

.bug-prediction-section .loading-state,
.bug-prediction-section .error-state,
.bug-prediction-section .success-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
}

.bug-prediction-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.bug-prediction-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.bug-prediction-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.bug-prediction-section .success-state i {
  color: var(--chart-green);
}

/* Risk Files List */
.bug-prediction-section .risk-files-list {
  margin-top: var(--spacing-5);
}

.bug-prediction-section .risk-files-list h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: var(--spacing-3);
  font-weight: 600;
}

.bug-prediction-section .list-item {
  padding: var(--spacing-4);
  background: rgba(17, 24, 39, 0.5);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-3);
  border-left: 4px solid var(--text-tertiary);
  transition: all var(--duration-200) var(--ease-out);
}

.bug-prediction-section .list-item:hover {
  background: rgba(17, 24, 39, 0.7);
}

.bug-prediction-section .list-item.item-critical {
  border-left-color: var(--color-error);
}

.bug-prediction-section .list-item.item-warning {
  border-left-color: var(--color-warning);
}

.bug-prediction-section .list-item.item-info {
  border-left-color: var(--chart-blue);
}

.bug-prediction-section .list-item.item-success {
  border-left-color: var(--chart-green);
}

.bug-prediction-section .item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2-5);
  flex-wrap: wrap;
}

.bug-prediction-section .risk-badge {
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-default);
  font-weight: 600;
  font-size: 0.85em;
  min-width: 50px;
  text-align: center;
}

.bug-prediction-section .risk-badge.item-critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.bug-prediction-section .risk-badge.item-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.bug-prediction-section .risk-badge.item-info {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
}

.bug-prediction-section .risk-badge.item-success {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.bug-prediction-section .item-path {
  color: var(--text-secondary);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.9em;
  flex: 1;
  word-break: break-all;
}

.bug-prediction-section .risk-level-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.75em;
  text-transform: uppercase;
  font-weight: 600;
}

.bug-prediction-section .risk-level-badge.critical,
.bug-prediction-section .risk-level-badge.high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.bug-prediction-section .risk-level-badge.medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.bug-prediction-section .risk-level-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

/* Risk Factors */
.bug-prediction-section .risk-factors {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2-5);
}

.bug-prediction-section .factor-badge {
  padding: 3px 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: var(--radius-default);
  font-size: 0.8em;
  color: var(--text-muted);
}

/* Prevention Tips */
.bug-prediction-section .prevention-tips {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-3);
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-md);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.bug-prediction-section .prevention-tips i {
  color: var(--color-warning-light);
  margin-top: var(--spacing-0-5);
}

.bug-prediction-section .prevention-tips span {
  color: var(--color-info-light);
  font-size: 0.85em;
  line-height: 1.4;
}

.bug-prediction-section .show-more {
  text-align: center;
  padding: var(--spacing-2-5);
}

.bug-prediction-section .show-more .muted {
  color: var(--text-tertiary);
  font-size: 0.85em;
}

/* Enhanced Bug Prediction Styles */
.summary-card.clickable { cursor: pointer; transition: transform 0.2s; }
.summary-card.clickable:hover { transform: translateY(-2px); }
.top-risk-factors-summary { margin: var(--spacing-5) var(--spacing-0); padding: var(--spacing-4); background: rgba(17, 24, 39, 0.6); border-radius: var(--radius-xl); border: 1px solid rgba(239, 68, 68, 0.2); }
.top-risk-factors-summary h4 { color: var(--color-error-light); font-size: 1em; margin-bottom: var(--spacing-4); display: flex; align-items: center; gap: var(--spacing-2); }
.top-risk-factors-summary h4 i { color: var(--color-error); }
.risk-factors-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--spacing-3); }
.risk-factor-card { display: flex; align-items: flex-start; gap: var(--spacing-3); padding: var(--spacing-3-5); background: rgba(30, 41, 59, 0.5); border-radius: var(--radius-lg); border-left: 3px solid var(--text-tertiary); }
.risk-factor-card.critical { border-left-color: var(--color-error); background: rgba(239, 68, 68, 0.1); }
.risk-factor-card.high { border-left-color: var(--chart-orange); background: rgba(249, 115, 22, 0.1); }
.risk-factor-card.medium { border-left-color: var(--color-warning); background: rgba(234, 179, 8, 0.1); }
.risk-factor-card .factor-icon { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; background: rgba(71, 85, 105, 0.4); border-radius: var(--radius-lg); }
.risk-factor-card .factor-icon i { font-size: 1.1em; color: var(--text-muted); }
.risk-factor-card.critical .factor-icon i { color: var(--color-error-light); }
.risk-factor-card.high .factor-icon i { color: var(--chart-orange-light); }
.risk-factor-card .factor-details { flex: 1; }
.risk-factor-card .factor-name { color: var(--text-primary); font-weight: 600; font-size: 0.95em; margin-bottom: var(--spacing-1); }
.risk-factor-card .factor-count { color: var(--color-warning-light); font-size: 0.85em; font-weight: 500; margin-bottom: var(--spacing-1); }
.risk-factor-card .factor-description { color: var(--text-muted); font-size: 0.8em; line-height: 1.4; }
.risk-filter-tabs { display: flex; gap: var(--spacing-2); margin: var(--spacing-5) var(--spacing-0) var(--spacing-4); flex-wrap: wrap; }
.risk-filter-tabs button { padding: var(--spacing-2) var(--spacing-4); border: 1px solid rgba(71, 85, 105, 0.5); background: rgba(30, 41, 59, 0.5); color: var(--text-muted); border-radius: var(--radius-md); font-size: 0.85em; cursor: pointer; transition: all 0.2s; }
.risk-filter-tabs button:hover:not(:disabled) { background: rgba(71, 85, 105, 0.5); color: var(--text-secondary); }
.risk-filter-tabs button.active { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.5); color: var(--color-info-light); }
.risk-filter-tabs button:disabled { opacity: 0.5; cursor: not-allowed; }
.risk-files-list.detailed h4 { display: flex; align-items: center; gap: var(--spacing-2); color: var(--text-secondary); margin-bottom: var(--spacing-3); }
.risk-files-list.detailed h4 .file-count { color: var(--text-tertiary); font-weight: normal; font-size: 0.9em; }
.risk-files-list .no-files-message { padding: var(--spacing-5); text-align: center; color: var(--color-success-light); background: rgba(34, 197, 94, 0.1); border-radius: var(--radius-lg); }
.risk-file-item { background: rgba(17, 24, 39, 0.5); border-radius: var(--radius-lg); margin-bottom: var(--spacing-2-5); border-left: 4px solid var(--text-tertiary); overflow: hidden; transition: all 0.2s; }
.risk-file-item.item-critical { border-left-color: var(--color-error); }
.risk-file-item.item-warning { border-left-color: var(--color-warning); }
.risk-file-item.item-info { border-left-color: var(--chart-blue); }
.risk-file-item.item-success { border-left-color: var(--chart-green); }
.risk-file-item.expanded { background: rgba(17, 24, 39, 0.8); }
.risk-file-item .file-header { display: flex; align-items: center; justify-content: space-between; padding: var(--spacing-3) var(--spacing-4); cursor: pointer; transition: background 0.2s; }
.risk-file-item .file-header:hover { background: rgba(71, 85, 105, 0.2); }
.risk-file-item .file-info { display: flex; align-items: center; gap: var(--spacing-2-5); flex: 1; flex-wrap: wrap; }
.risk-file-item .risk-score-badge { padding: var(--spacing-1) var(--spacing-2-5); border-radius: var(--radius-default); font-weight: 700; font-size: 0.85em; min-width: 40px; text-align: center; }
.risk-file-item .risk-score-badge.item-critical { background: rgba(239, 68, 68, 0.3); color: var(--color-error-light); }
.risk-file-item .risk-score-badge.item-warning { background: rgba(245, 158, 11, 0.3); color: var(--color-warning-light); }
.risk-file-item .risk-score-badge.item-info { background: rgba(59, 130, 246, 0.3); color: var(--color-info-light); }
.risk-file-item .risk-score-badge.item-success { background: rgba(34, 197, 94, 0.3); color: var(--color-success-light); }
.risk-file-item .file-path { color: var(--text-secondary); font-family: monospace; font-size: 0.85em; flex: 1; word-break: break-all; }
.risk-file-item .risk-level-tag { padding: var(--spacing-0-5) var(--spacing-2); border-radius: var(--radius-default); font-size: 0.7em; text-transform: uppercase; font-weight: 600; }
.risk-file-item .risk-level-tag.high, .risk-file-item .risk-level-tag.critical { background: rgba(239, 68, 68, 0.2); color: var(--color-error-light); }
.risk-file-item .risk-level-tag.medium { background: rgba(245, 158, 11, 0.2); color: var(--color-warning-light); }
.risk-file-item .risk-level-tag.low, .risk-file-item .risk-level-tag.minimal { background: rgba(34, 197, 94, 0.2); color: var(--color-success-light); }
.risk-file-item .expand-icon { color: var(--text-tertiary); padding: var(--spacing-1) var(--spacing-2); }
.quick-risk-indicators { display: flex; flex-wrap: wrap; gap: var(--spacing-1-5); padding: var(--spacing-0) var(--spacing-4) var(--spacing-3); }
.quick-risk-indicators .indicator { display: flex; align-items: center; gap: var(--spacing-1); padding: 3px 8px; border-radius: var(--radius-default); font-size: 0.75em; font-weight: 500; }
.quick-risk-indicators .indicator.critical { background: rgba(239, 68, 68, 0.2); color: var(--color-error-light); }
.quick-risk-indicators .indicator.high { background: rgba(249, 115, 22, 0.2); color: var(--chart-orange-light); }
.quick-risk-indicators .indicator.warning { background: rgba(234, 179, 8, 0.2); color: var(--color-warning-light); }
.quick-risk-indicators .indicator.info { background: rgba(59, 130, 246, 0.2); color: var(--color-info-light); }
.quick-risk-indicators .indicator.muted { background: rgba(100, 116, 139, 0.2); color: var(--text-muted); }
.file-details { padding: var(--spacing-4); background: rgba(15, 23, 42, 0.5); border-top: 1px solid rgba(71, 85, 105, 0.3); }
.file-details .detail-section { margin-bottom: var(--spacing-4); }
.file-details .detail-section:last-child { margin-bottom: var(--spacing-0); }
.file-details h5 { color: var(--text-secondary); font-size: 0.9em; margin-bottom: var(--spacing-2-5); display: flex; align-items: center; gap: var(--spacing-1-5); }
.file-details h5 i { color: var(--text-tertiary); }
.factors-breakdown { display: flex; flex-direction: column; gap: var(--spacing-2); }
.factor-row { display: flex; align-items: center; gap: var(--spacing-3); }
.factor-row .factor-label { width: 140px; color: var(--text-muted); font-size: 0.85em; display: flex; align-items: center; gap: var(--spacing-1-5); }
.factor-row .factor-label i { width: 16px; text-align: center; color: var(--text-tertiary); }
.factor-row.high-value .factor-label { color: var(--color-error-light); }
.factor-row.high-value .factor-label i { color: var(--color-error); }
.factor-row.medium-value .factor-label { color: var(--color-warning-light); }
.factor-row .factor-bar-container { flex: 1; height: 8px; background: rgba(71, 85, 105, 0.3); border-radius: var(--radius-default); overflow: hidden; }
.factor-row .factor-bar { height: 100%; border-radius: var(--radius-default); transition: width 0.3s; }
.factor-row .factor-bar.bar-critical { background: var(--color-error); }
.factor-row .factor-bar.bar-warning { background: var(--color-warning); }
.factor-row .factor-bar.bar-ok { background: var(--color-success); }
.factor-row .factor-value { width: 40px; text-align: right; font-weight: 600; font-size: 0.85em; color: var(--text-secondary); }
.factor-row.high-value .factor-value { color: var(--color-error-light); }
.factor-row.medium-value .factor-value { color: var(--color-warning-light); }
.tips-list, .tests-list { list-style: none; padding: var(--spacing-0); margin: var(--spacing-0); }
.tips-list li, .tests-list li { display: flex; align-items: flex-start; gap: var(--spacing-2-5); padding: var(--spacing-2-5) var(--spacing-3); background: rgba(30, 41, 59, 0.5); border-radius: var(--radius-md); margin-bottom: var(--spacing-1-5); font-size: 0.85em; line-height: 1.4; }
.tips-list li i { color: var(--color-warning-light); margin-top: var(--spacing-0-5); }
.tips-list li { color: var(--text-secondary); border-left: 3px solid var(--color-warning-light); }
.tests-list li i { color: var(--chart-purple-light); margin-top: var(--spacing-0-5); }
.tests-list li { color: var(--chart-purple-light); border-left: 3px solid var(--chart-purple-light); }
.show-more-container { text-align: center; margin-top: var(--spacing-4); }
.show-more-btn { padding: var(--spacing-2-5) var(--spacing-6); background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.4); color: var(--color-info-light); border-radius: var(--radius-md); cursor: pointer; font-size: 0.9em; display: inline-flex; align-items: center; gap: var(--spacing-2); transition: all 0.2s; }
.show-more-btn:hover { background: rgba(59, 130, 246, 0.3); }

/* Issue #538: Code Intelligence Scores Section */

</style>
