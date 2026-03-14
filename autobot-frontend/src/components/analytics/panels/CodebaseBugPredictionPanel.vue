<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Bug Prediction section (#538) -->
<template>
  <div class="bug-prediction-section analytics-section">
    <h3>
      <i class="fas fa-bug"></i> {{ $t('analytics.codebase.bugPrediction.title') }}
      <span v-if="analysis" class="total-count">
        ({{ atRiskCount }} files need attention)
      </span>
      <button
        @click="emit('refresh')"
        :disabled="loading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
      </button>
      <div class="section-export-buttons" v-if="analysis">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
        >
          <i class="fas fa-file-alt"></i> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportJson')"
        >
          <i class="fas fa-file-code"></i> JSON
        </button>
      </div>
    </h3>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span v-if="taskCurrentStep">{{ taskCurrentStep }}</span>
      <span v-else>{{ $t('analytics.codebase.bugPrediction.analyzing') }}</span>
      <div v-if="taskProgress" class="mini-progress">
        <div class="mini-progress-bar" :style="{ width: taskProgress + '%' }"></div>
      </div>
    </div>

    <!-- Interrupted State -->
    <div v-if="!loading && wasInterrupted" class="interrupted-state">
      <i class="fas fa-info-circle"></i>
      {{ $t('analytics.codebase.bugPrediction.interrupted') }}
      <button @click="emit('refresh')" class="rerun-btn">
        <i class="fas fa-redo"></i> {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <!-- Error State -->
    <div v-else-if="!loading && error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i> {{ error }}
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
          <i class="fas fa-exclamation-circle"></i>
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
              <i :class="getRiskFactorIcon(factor.name)"></i>
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
          <i class="fas fa-file-code"></i>
          {{
            activeFilter === 'all'
              ? 'Analyzed Files'
              : `${activeFilter.charAt(0).toUpperCase() + activeFilter.slice(1)} Risk Files`
          }}
          <span class="file-count">({{ filteredFiles.length }} files)</span>
        </h4>

        <div v-if="filteredFiles.length === 0" class="no-files-message">
          <i class="fas fa-check-circle"></i>
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
              <i
                :class="expandedFiles.has(file.file_path) ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"
              ></i>
            </div>
          </div>

          <div class="quick-risk-indicators">
            <span
              v-if="file.factors?.complexity >= 80"
              class="indicator high"
              :title="$t('analytics.codebase.risk.highComplexity')"
            >
              <i class="fas fa-project-diagram"></i>
              {{ $t('analytics.codebase.risk.complex') }}
            </span>
            <span
              v-if="file.factors?.change_frequency >= 80"
              class="indicator warning"
              :title="$t('analytics.codebase.risk.frequentlyChanged')"
            >
              <i class="fas fa-history"></i>
              {{ $t('analytics.codebase.risk.unstable') }}
            </span>
            <span
              v-if="file.factors?.file_size >= 70"
              class="indicator info"
              :title="$t('analytics.codebase.risk.largeFile')"
            >
              <i class="fas fa-file-alt"></i>
              {{ $t('analytics.codebase.risk.large') }}
            </span>
            <span
              v-if="file.factors?.bug_history > 0"
              class="indicator critical"
              :title="$t('analytics.codebase.risk.hasBugHistory')"
            >
              <i class="fas fa-bug"></i>
              {{ $t('analytics.codebase.risk.bugHistory') }}
            </span>
            <span
              v-if="file.factors?.test_coverage === 50"
              class="indicator muted"
              :title="$t('analytics.codebase.risk.noTestsDetected')"
            >
              <i class="fas fa-vial"></i>
              {{ $t('analytics.codebase.risk.noTests') }}
            </span>
          </div>

          <div v-if="expandedFiles.has(file.file_path)" class="file-details">
            <div class="detail-section">
              <h5>
                <i class="fas fa-chart-bar"></i>
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
                <i class="fas fa-lightbulb"></i>
                {{ $t('analytics.codebase.bugPrediction.recommendedFixes') }}
              </h5>
              <ul class="tips-list">
                <li v-for="(tip, tipIndex) in file.prevention_tips" :key="tipIndex">
                  <i class="fas fa-wrench"></i> {{ tip }}
                </li>
              </ul>
            </div>

            <div v-if="file.suggested_tests && file.suggested_tests.length > 0" class="detail-section">
              <h5>
                <i class="fas fa-vial"></i>
                {{ $t('analytics.codebase.bugPrediction.suggestedTests') }}
              </h5>
              <ul class="tests-list">
                <li v-for="(test, testIndex) in file.suggested_tests" :key="testIndex">
                  <i class="fas fa-flask"></i> {{ test }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div v-if="filteredFiles.length > visibleCount" class="show-more-container">
          <button @click="visibleCount += PAGE_SIZE" class="show-more-btn">
            <i class="fas fa-chevron-down"></i>
            Show More
            ({{ Math.min(PAGE_SIZE, filteredFiles.length - visibleCount) }} of
            {{ filteredFiles.length - visibleCount }} remaining)
          </button>
        </div>
      </div>

      <div v-if="analysis.timestamp" class="scan-timestamp">
        <i class="fas fa-clock"></i>
        {{ $t('analytics.codebase.bugPrediction.lastAnalysis') }}:
        {{ formatTimestamp(analysis.timestamp) }}
      </div>
    </div>

    <div
      v-else-if="analysis && analysis.files.length === 0"
      class="success-state"
    >
      <i class="fas fa-check-circle"></i>
      {{ $t('analytics.codebase.bugPrediction.noFilesAnalyzed') }}
    </div>

    <EmptyState
      v-else
      icon="fas fa-bug"
      :message="$t('analytics.codebase.bugPrediction.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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
  error: string
  wasInterrupted: boolean
  taskCurrentStep?: string
  taskProgress?: number
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: string]
}>()

const PAGE_SIZE = 50
const activeFilter = ref<'all' | 'high' | 'medium' | 'low'>('all')
const visibleCount = ref(PAGE_SIZE)
const expandedFiles = ref<Set<string>>(new Set())

const mediumRiskCount = computed(() =>
  props.analysis?.files.filter((f) => f.risk_score >= 40 && f.risk_score < 60).length ?? 0
)

const lowRiskCount = computed(() =>
  props.analysis?.files.filter((f) => f.risk_score < 40).length ?? 0
)

const atRiskCount = computed(() =>
  props.analysis?.files.filter((f) => f.risk_score >= 40).length ?? 0
)

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
  if (expandedFiles.value.has(filePath)) {
    expandedFiles.value.delete(filePath)
  } else {
    expandedFiles.value.add(filePath)
  }
  expandedFiles.value = new Set(expandedFiles.value)
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
    complexity: 'fas fa-project-diagram',
    change_frequency: 'fas fa-history',
    file_size: 'fas fa-file-alt',
    bug_history: 'fas fa-bug',
    test_coverage: 'fas fa-vial',
    dependency_count: 'fas fa-sitemap',
  }
  return icons[factor] || 'fas fa-exclamation-circle'
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
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.bug-prediction-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 16px;
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
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
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
  margin-top: 20px;
}

.bug-prediction-section .risk-files-list h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  font-weight: 600;
}

.bug-prediction-section .list-item {
  padding: 16px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 4px solid var(--text-tertiary);
  transition: all 0.2s ease;
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
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.bug-prediction-section .risk-badge {
  padding: 4px 10px;
  border-radius: 4px;
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
  padding: 2px 8px;
  border-radius: 4px;
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
  gap: 8px;
  margin-bottom: 10px;
}

.bug-prediction-section .factor-badge {
  padding: 3px 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  font-size: 0.8em;
  color: var(--text-muted);
}

/* Prevention Tips */
.bug-prediction-section .prevention-tips {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 6px;
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.bug-prediction-section .prevention-tips i {
  color: var(--color-warning-light);
  margin-top: 2px;
}

.bug-prediction-section .prevention-tips span {
  color: var(--color-info-light);
  font-size: 0.85em;
  line-height: 1.4;
}

.bug-prediction-section .show-more {
  text-align: center;
  padding: 10px;
}

.bug-prediction-section .show-more .muted {
  color: var(--text-tertiary);
  font-size: 0.85em;
}

/* Enhanced Bug Prediction Styles */
.summary-card.clickable { cursor: pointer; transition: transform 0.2s; }
.summary-card.clickable:hover { transform: translateY(-2px); }
.top-risk-factors-summary { margin: 20px 0; padding: 16px; background: rgba(17, 24, 39, 0.6); border-radius: 10px; border: 1px solid rgba(239, 68, 68, 0.2); }
.top-risk-factors-summary h4 { color: var(--color-error-light); font-size: 1em; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
.top-risk-factors-summary h4 i { color: var(--color-error); }
.risk-factors-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.risk-factor-card { display: flex; align-items: flex-start; gap: 12px; padding: 14px; background: rgba(30, 41, 59, 0.5); border-radius: 8px; border-left: 3px solid var(--text-tertiary); }
.risk-factor-card.critical { border-left-color: var(--color-error); background: rgba(239, 68, 68, 0.1); }
.risk-factor-card.high { border-left-color: var(--chart-orange); background: rgba(249, 115, 22, 0.1); }
.risk-factor-card.medium { border-left-color: var(--color-warning); background: rgba(234, 179, 8, 0.1); }
.risk-factor-card .factor-icon { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; background: rgba(71, 85, 105, 0.4); border-radius: 8px; }
.risk-factor-card .factor-icon i { font-size: 1.1em; color: var(--text-muted); }
.risk-factor-card.critical .factor-icon i { color: var(--color-error-light); }
.risk-factor-card.high .factor-icon i { color: var(--chart-orange-light); }
.risk-factor-card .factor-details { flex: 1; }
.risk-factor-card .factor-name { color: var(--text-primary); font-weight: 600; font-size: 0.95em; margin-bottom: 4px; }
.risk-factor-card .factor-count { color: var(--color-warning-light); font-size: 0.85em; font-weight: 500; margin-bottom: 4px; }
.risk-factor-card .factor-description { color: var(--text-muted); font-size: 0.8em; line-height: 1.4; }
.risk-filter-tabs { display: flex; gap: 8px; margin: 20px 0 16px; flex-wrap: wrap; }
.risk-filter-tabs button { padding: 8px 16px; border: 1px solid rgba(71, 85, 105, 0.5); background: rgba(30, 41, 59, 0.5); color: var(--text-muted); border-radius: 6px; font-size: 0.85em; cursor: pointer; transition: all 0.2s; }
.risk-filter-tabs button:hover:not(:disabled) { background: rgba(71, 85, 105, 0.5); color: var(--text-secondary); }
.risk-filter-tabs button.active { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.5); color: var(--color-info-light); }
.risk-filter-tabs button:disabled { opacity: 0.5; cursor: not-allowed; }
.risk-files-list.detailed h4 { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); margin-bottom: 12px; }
.risk-files-list.detailed h4 .file-count { color: var(--text-tertiary); font-weight: normal; font-size: 0.9em; }
.risk-files-list .no-files-message { padding: 20px; text-align: center; color: var(--color-success-light); background: rgba(34, 197, 94, 0.1); border-radius: 8px; }
.risk-file-item { background: rgba(17, 24, 39, 0.5); border-radius: 8px; margin-bottom: 10px; border-left: 4px solid var(--text-tertiary); overflow: hidden; transition: all 0.2s; }
.risk-file-item.item-critical { border-left-color: var(--color-error); }
.risk-file-item.item-warning { border-left-color: var(--color-warning); }
.risk-file-item.item-info { border-left-color: var(--chart-blue); }
.risk-file-item.item-success { border-left-color: var(--chart-green); }
.risk-file-item.expanded { background: rgba(17, 24, 39, 0.8); }
.risk-file-item .file-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; cursor: pointer; transition: background 0.2s; }
.risk-file-item .file-header:hover { background: rgba(71, 85, 105, 0.2); }
.risk-file-item .file-info { display: flex; align-items: center; gap: 10px; flex: 1; flex-wrap: wrap; }
.risk-file-item .risk-score-badge { padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 0.85em; min-width: 40px; text-align: center; }
.risk-file-item .risk-score-badge.item-critical { background: rgba(239, 68, 68, 0.3); color: var(--color-error-light); }
.risk-file-item .risk-score-badge.item-warning { background: rgba(245, 158, 11, 0.3); color: var(--color-warning-light); }
.risk-file-item .risk-score-badge.item-info { background: rgba(59, 130, 246, 0.3); color: var(--color-info-light); }
.risk-file-item .risk-score-badge.item-success { background: rgba(34, 197, 94, 0.3); color: var(--color-success-light); }
.risk-file-item .file-path { color: var(--text-secondary); font-family: monospace; font-size: 0.85em; flex: 1; word-break: break-all; }
.risk-file-item .risk-level-tag { padding: 2px 8px; border-radius: 4px; font-size: 0.7em; text-transform: uppercase; font-weight: 600; }
.risk-file-item .risk-level-tag.high, .risk-file-item .risk-level-tag.critical { background: rgba(239, 68, 68, 0.2); color: var(--color-error-light); }
.risk-file-item .risk-level-tag.medium { background: rgba(245, 158, 11, 0.2); color: var(--color-warning-light); }
.risk-file-item .risk-level-tag.low, .risk-file-item .risk-level-tag.minimal { background: rgba(34, 197, 94, 0.2); color: var(--color-success-light); }
.risk-file-item .expand-icon { color: var(--text-tertiary); padding: 4px 8px; }
.quick-risk-indicators { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 12px; }
.quick-risk-indicators .indicator { display: flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 500; }
.quick-risk-indicators .indicator.critical { background: rgba(239, 68, 68, 0.2); color: var(--color-error-light); }
.quick-risk-indicators .indicator.high { background: rgba(249, 115, 22, 0.2); color: var(--chart-orange-light); }
.quick-risk-indicators .indicator.warning { background: rgba(234, 179, 8, 0.2); color: var(--color-warning-light); }
.quick-risk-indicators .indicator.info { background: rgba(59, 130, 246, 0.2); color: var(--color-info-light); }
.quick-risk-indicators .indicator.muted { background: rgba(100, 116, 139, 0.2); color: var(--text-muted); }
.file-details { padding: 16px; background: rgba(15, 23, 42, 0.5); border-top: 1px solid rgba(71, 85, 105, 0.3); }
.file-details .detail-section { margin-bottom: 16px; }
.file-details .detail-section:last-child { margin-bottom: 0; }
.file-details h5 { color: var(--text-secondary); font-size: 0.9em; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.file-details h5 i { color: var(--text-tertiary); }
.factors-breakdown { display: flex; flex-direction: column; gap: 8px; }
.factor-row { display: flex; align-items: center; gap: 12px; }
.factor-row .factor-label { width: 140px; color: var(--text-muted); font-size: 0.85em; display: flex; align-items: center; gap: 6px; }
.factor-row .factor-label i { width: 16px; text-align: center; color: var(--text-tertiary); }
.factor-row.high-value .factor-label { color: var(--color-error-light); }
.factor-row.high-value .factor-label i { color: var(--color-error); }
.factor-row.medium-value .factor-label { color: var(--color-warning-light); }
.factor-row .factor-bar-container { flex: 1; height: 8px; background: rgba(71, 85, 105, 0.3); border-radius: 4px; overflow: hidden; }
.factor-row .factor-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.factor-row .factor-bar.bar-critical { background: var(--color-error); }
.factor-row .factor-bar.bar-warning { background: var(--color-warning); }
.factor-row .factor-bar.bar-ok { background: var(--color-success); }
.factor-row .factor-value { width: 40px; text-align: right; font-weight: 600; font-size: 0.85em; color: var(--text-secondary); }
.factor-row.high-value .factor-value { color: var(--color-error-light); }
.factor-row.medium-value .factor-value { color: var(--color-warning-light); }
.tips-list, .tests-list { list-style: none; padding: 0; margin: 0; }
.tips-list li, .tests-list li { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: rgba(30, 41, 59, 0.5); border-radius: 6px; margin-bottom: 6px; font-size: 0.85em; line-height: 1.4; }
.tips-list li i { color: var(--color-warning-light); margin-top: 2px; }
.tips-list li { color: var(--text-secondary); border-left: 3px solid var(--color-warning-light); }
.tests-list li i { color: var(--chart-purple-light); margin-top: 2px; }
.tests-list li { color: var(--chart-purple-light); border-left: 3px solid var(--chart-purple-light); }
.show-more-container { text-align: center; margin-top: 16px; }
.show-more-btn { padding: 10px 24px; background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.4); color: var(--color-info-light); border-radius: 6px; cursor: pointer; font-size: 0.9em; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s; }
.show-more-btn:hover { background: rgba(59, 130, 246, 0.3); }

/* Issue #538: Code Intelligence Scores Section */

</style>
