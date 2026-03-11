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
