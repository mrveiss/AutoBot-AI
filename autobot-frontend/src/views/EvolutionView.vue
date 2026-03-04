<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  EvolutionView.vue - Code Evolution Mining Dashboard (Issue #243 - Phase 2, #247 - Timeline Visualization)
-->
<template>
  <div class="evolution-view">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ $t('analytics.evolution.title') }}</h1>
        <p class="page-subtitle">
          {{ $t('analytics.evolution.subtitle') }}
        </p>
      </div>
      <button
        @click="showAnalysisModal = true"
        class="btn-action-primary"
        :disabled="evolution.loading.value"
      >
        <i class="fas fa-play-circle"></i>
        {{ $t('analytics.evolution.analyzeRepository') }}
      </button>
    </div>

    <!-- Analysis Results Summary -->
    <div v-if="evolution.hasAnalysisResult.value" class="analysis-summary">
      <div class="summary-card">
        <div class="summary-icon success">
          <i class="fas fa-check-circle"></i>
        </div>
        <div class="summary-content">
          <div class="summary-value">{{ evolution.analysisResult.value?.commits_analyzed || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.evolution.commitsAnalyzed') }}</div>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-icon emerging">
          <i class="fas fa-arrow-trend-up"></i>
        </div>
        <div class="summary-content">
          <div class="summary-value">
            {{ evolution.analysisResult.value?.emerging_patterns?.length || 0 }}
          </div>
          <div class="summary-label">{{ $t('analytics.evolution.emergingPatterns') }}</div>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-icon declining">
          <i class="fas fa-arrow-trend-down"></i>
        </div>
        <div class="summary-content">
          <div class="summary-value">
            {{ evolution.analysisResult.value?.declining_patterns?.length || 0 }}
          </div>
          <div class="summary-label">{{ $t('analytics.evolution.decliningPatterns') }}</div>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-icon refactor">
          <i class="fas fa-code-branch"></i>
        </div>
        <div class="summary-content">
          <div class="summary-value">
            {{ evolution.analysisResult.value?.refactorings_detected || 0 }}
          </div>
          <div class="summary-label">{{ $t('analytics.evolution.refactoringsDetected') }}</div>
        </div>
      </div>
    </div>

    <!-- Filter Controls (Issue #247) -->
    <div class="filter-panel">
      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">{{ $t('analytics.evolution.filters.startDate') }}</label>
          <input v-model="filters.startDate" type="date" class="field-input filter-input" />
        </div>
        <div class="filter-group">
          <label class="filter-label">{{ $t('analytics.evolution.filters.endDate') }}</label>
          <input v-model="filters.endDate" type="date" class="field-input filter-input" />
        </div>
        <div class="filter-group">
          <label class="filter-label">{{ $t('analytics.evolution.filters.granularity') }}</label>
          <select v-model="filters.granularity" class="field-input filter-input">
            <option value="hourly">{{ $t('analytics.evolution.filters.hourly') }}</option>
            <option value="daily">{{ $t('analytics.evolution.filters.daily') }}</option>
            <option value="weekly">{{ $t('analytics.evolution.filters.weekly') }}</option>
            <option value="monthly">{{ $t('analytics.evolution.filters.monthly') }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">{{ $t('analytics.evolution.filters.trendPeriod') }}</label>
          <select v-model="filters.trendDays" class="field-input filter-input">
            <option :value="7">{{ $t('analytics.evolution.filters.days7') }}</option>
            <option :value="30">{{ $t('analytics.evolution.filters.days30') }}</option>
            <option :value="90">{{ $t('analytics.evolution.filters.days90') }}</option>
            <option :value="180">{{ $t('analytics.evolution.filters.days180') }}</option>
            <option :value="365">{{ $t('analytics.evolution.filters.year1') }}</option>
          </select>
        </div>
        <div class="filter-actions">
          <button
            @click="applyFilters"
            class="btn-action-primary"
            :disabled="evolution.loading.value"
          >
            <i class="fas fa-filter"></i>
            {{ $t('analytics.evolution.applyFilters') }}
          </button>
          <div class="export-group">
            <button
              @click="evolution.exportData('json', filters.startDate, filters.endDate)"
              class="btn-action-secondary"
              :title="$t('analytics.evolution.exportJson')"
            >
              <i class="fas fa-file-code"></i>
              JSON
            </button>
            <button
              @click="evolution.exportData('csv', filters.startDate, filters.endDate)"
              class="btn-action-secondary"
              :title="$t('analytics.evolution.exportCsv')"
            >
              <i class="fas fa-file-csv"></i>
              CSV
            </button>
          </div>
        </div>
      </div>
      <!-- Metric Selector -->
      <div class="metric-selector">
        <span class="filter-label">{{ $t('analytics.evolution.filters.metrics') }}:</span>
        <label v-for="m in availableMetrics" :key="m.value" class="metric-checkbox">
          <input type="checkbox" :value="m.value" v-model="filters.selectedMetrics" />
          {{ m.label }}
        </label>
      </div>
    </div>

    <!-- Quality Trends (Issue #247) -->
    <div v-if="evolution.hasTrendsData.value" class="trends-section">
      <h2 class="section-title">{{ $t('analytics.evolution.qualityTrends') }} ({{ filters.trendDays }} {{ $t('analytics.evolution.days') }})</h2>
      <div class="trends-grid">
        <div
          v-for="(trend, metric) in evolution.trendsData.value"
          :key="metric"
          class="trend-card"
        >
          <div class="trend-metric">{{ formatMetricName(String(metric)) }}</div>
          <div class="trend-value" :class="trend.direction">
            {{ trend.last_value.toFixed(1) }}
          </div>
          <div class="trend-change" :class="trend.direction">
            <i
              :class="
                trend.direction === 'improving'
                  ? 'fas fa-arrow-up'
                  : trend.direction === 'declining'
                    ? 'fas fa-arrow-down'
                    : 'fas fa-minus'
              "
            ></i>
            {{ trend.percent_change > 0 ? '+' : '' }}{{ trend.percent_change.toFixed(1) }}%
          </div>
          <div class="trend-label">{{ trend.direction }}</div>
        </div>
      </div>
    </div>

    <!-- Charts Section -->
    <div class="charts-section">
      <!-- Timeline Chart -->
      <div class="chart-container">
        <EvolutionTimelineChart
          :data="evolution.timelineData.value"
          :loading="evolution.loading.value"
          :error="evolution.error.value || undefined"
          :metrics="filters.selectedMetrics"
        />
      </div>

      <!-- Pattern Evolution Chart -->
      <div class="chart-container">
        <PatternEvolutionChart
          :data="evolution.patternData.value"
          :loading="evolution.loading.value"
          :error="evolution.error.value || undefined"
        />
      </div>
    </div>

    <!-- Pattern Details Table -->
    <div v-if="evolution.hasAnalysisResult.value" class="patterns-section">
      <h2 class="section-title">{{ $t('analytics.evolution.patternDetails') }}</h2>

      <!-- Emerging Patterns -->
      <div v-if="evolution.analysisResult.value?.emerging_patterns.length" class="pattern-table">
        <h3 class="table-title">
          <i class="fas fa-arrow-trend-up icon-success"></i>
          {{ $t('analytics.evolution.emergingPatterns') }}
        </h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ $t('analytics.evolution.table.patternType') }}</th>
              <th>{{ $t('analytics.evolution.table.count') }}</th>
              <th>{{ $t('analytics.evolution.table.firstSeen') }}</th>
              <th>{{ $t('analytics.evolution.table.lastSeen') }}</th>
              <th>{{ $t('analytics.evolution.table.trend') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pattern in evolution.analysisResult.value?.emerging_patterns" :key="pattern.pattern_type">
              <td class="cell-primary">{{ formatPatternName(pattern.pattern_type) }}</td>
              <td>{{ pattern.count }}</td>
              <td>{{ formatDate(pattern.first_seen) }}</td>
              <td>{{ formatDate(pattern.last_seen) }}</td>
              <td>
                <span class="badge badge-success">{{ pattern.trend }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Declining Patterns -->
      <div v-if="evolution.analysisResult.value?.declining_patterns.length" class="pattern-table">
        <h3 class="table-title">
          <i class="fas fa-arrow-trend-down icon-info"></i>
          {{ $t('analytics.evolution.decliningPatterns') }}
        </h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ $t('analytics.evolution.table.patternType') }}</th>
              <th>{{ $t('analytics.evolution.table.count') }}</th>
              <th>{{ $t('analytics.evolution.table.firstSeen') }}</th>
              <th>{{ $t('analytics.evolution.table.lastSeen') }}</th>
              <th>{{ $t('analytics.evolution.table.trend') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pattern in evolution.analysisResult.value?.declining_patterns" :key="pattern.pattern_type">
              <td class="cell-primary">{{ formatPatternName(pattern.pattern_type) }}</td>
              <td>{{ pattern.count }}</td>
              <td>{{ formatDate(pattern.first_seen) }}</td>
              <td>{{ formatDate(pattern.last_seen) }}</td>
              <td>
                <span class="badge badge-info">{{ pattern.trend }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!evolution.loading.value && !evolution.hasAnalysisResult.value" class="empty-state">
      <i class="fas fa-chart-line"></i>
      <p>{{ $t('analytics.evolution.noData') }}</p>
      <p class="empty-detail">
        {{ $t('analytics.evolution.noDataHint') }}
      </p>
    </div>

    <!-- Analysis Modal -->
    <div v-if="showAnalysisModal" class="modal-overlay" @click.self="showAnalysisModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">{{ $t('analytics.evolution.analyzeRepository') }}</h3>
          <button @click="showAnalysisModal = false" class="modal-close">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="field-group">
            <label>{{ $t('analytics.evolution.modal.repoPath') }}</label>
            <input
              v-model="analysisForm.repo_path"
              type="text"
              class="field-input"
              placeholder="/opt/autobot"
            />
          </div>

          <div class="form-row">
            <div class="field-group">
              <label>{{ $t('analytics.evolution.modal.startDateOptional') }}</label>
              <input
                v-model="analysisForm.start_date"
                type="date"
                class="field-input"
              />
            </div>

            <div class="field-group">
              <label>{{ $t('analytics.evolution.modal.endDateOptional') }}</label>
              <input
                v-model="analysisForm.end_date"
                type="date"
                class="field-input"
              />
            </div>
          </div>

          <div class="field-group">
            <label>{{ $t('analytics.evolution.modal.commitLimit') }}</label>
            <input
              v-model.number="analysisForm.commit_limit"
              type="number"
              min="1"
              max="1000"
              class="field-input"
            />
            <p class="form-help">{{ $t('analytics.evolution.modal.commitLimitHelp') }}</p>
          </div>

          <div v-if="evolution.error.value" class="error-message">
            <i class="fas fa-exclamation-triangle"></i>
            {{ evolution.error.value }}
          </div>
        </div>

        <div class="modal-footer">
          <button @click="showAnalysisModal = false" class="btn-action-secondary">
            {{ $t('analytics.evolution.modal.cancel') }}
          </button>
          <button
            @click="runAnalysis"
            class="btn-action-primary"
            :disabled="!analysisForm.repo_path || evolution.loading.value"
          >
            <i class="fas fa-spinner fa-spin" v-if="evolution.loading.value"></i>
            <i class="fas fa-play-circle" v-else></i>
            {{ evolution.loading.value ? $t('analytics.evolution.modal.analyzing') : $t('analytics.evolution.modal.startAnalysis') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEvolution } from '@/composables/useEvolution'
import EvolutionTimelineChart from '@/components/charts/EvolutionTimelineChart.vue'
import PatternEvolutionChart from '@/components/charts/PatternEvolutionChart.vue'

const evolution = useEvolution()
const { t } = useI18n()
const showAnalysisModal = ref(false)

// Filter state (Issue #247)
const filters = ref({
  startDate: '',
  endDate: '',
  granularity: 'daily',
  trendDays: 30,
  selectedMetrics: ['overall_score', 'maintainability', 'complexity'],
})

const availableMetrics = computed(() => [
  { value: 'overall_score', label: t('analytics.evolution.metrics.overall') },
  { value: 'maintainability', label: t('analytics.evolution.metrics.maintainability') },
  { value: 'complexity', label: t('analytics.evolution.metrics.complexity') },
  { value: 'testability', label: t('analytics.evolution.metrics.testability') },
  { value: 'documentation', label: t('analytics.evolution.metrics.documentation') },
  { value: 'security', label: t('analytics.evolution.metrics.security') },
  { value: 'performance', label: t('analytics.evolution.metrics.performance') },
])

const analysisForm = ref({
  repo_path: '/opt/autobot',
  start_date: '',
  end_date: '',
  commit_limit: 100,
})

async function applyFilters() {
  const metrics = filters.value.selectedMetrics.join(',')
  await Promise.all([
    evolution.fetchTimeline(
      filters.value.startDate || undefined,
      filters.value.endDate || undefined,
      filters.value.granularity,
      metrics
    ),
    evolution.fetchPatternEvolution(
      undefined,
      filters.value.startDate || undefined,
      filters.value.endDate || undefined
    ),
    evolution.fetchTrends(filters.value.trendDays),
  ])
}

async function runAnalysis() {
  const request: any = {
    repo_path: analysisForm.value.repo_path,
    commit_limit: analysisForm.value.commit_limit,
  }

  if (analysisForm.value.start_date) {
    request.start_date = new Date(analysisForm.value.start_date).toISOString()
  }

  if (analysisForm.value.end_date) {
    request.end_date = new Date(analysisForm.value.end_date).toISOString()
  }

  const success = await evolution.analyzeEvolution(request)

  if (success) {
    showAnalysisModal.value = false
  }
}

function formatPatternName(pattern: string): string {
  return pattern
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatMetricName(metric: string): string {
  return metric
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatDate(dateString: string): string {
  if (!dateString) return 'N/A'
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateString
  }
}

// Load all data on mount
onMounted(async () => {
  await Promise.all([
    evolution.fetchTimeline(),
    evolution.fetchPatternEvolution(),
    evolution.fetchTrends(filters.value.trendDays),
    evolution.fetchSummary(),
  ])
})
</script>

<style scoped>
.evolution-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--spacing-6);
  background: var(--bg-primary);
  overflow-y: auto;
}

/* Analysis Summary */
.analysis-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.summary-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  flex-shrink: 0;
}

.summary-icon.success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.summary-icon.emerging {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.summary-icon.declining {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.summary-icon.refactor {
  background: var(--color-purple-bg, rgba(139, 92, 246, 0.1));
  color: var(--color-purple, #8b5cf6);
}

.summary-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  line-height: var(--leading-none);
}

.summary-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

/* Filter Panel */
.filter-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.filter-row {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  min-width: 140px;
}

.filter-label {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-input {
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
}

.filter-actions {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-2);
  margin-left: auto;
  flex-wrap: wrap;
}

.export-group {
  display: flex;
  gap: var(--spacing-2);
}

.metric-selector {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
  flex-wrap: wrap;
}

.metric-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
  user-select: none;
}

.metric-checkbox input[type='checkbox'] {
  cursor: pointer;
  accent-color: var(--color-primary);
}

/* Trends Section */
.trends-section {
  margin-bottom: var(--spacing-6);
}

.trends-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--spacing-4);
}

.trend-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  padding: var(--spacing-4);
  text-align: center;
}

.trend-metric {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-2);
}

.trend-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  line-height: var(--leading-none);
  margin-bottom: var(--spacing-2);
}

.trend-value.improving { color: var(--color-success); }
.trend-value.declining { color: var(--color-error); }
.trend-value.stable { color: var(--text-primary); }

.trend-change {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1);
  margin-bottom: var(--spacing-1);
}

.trend-change.improving { color: var(--color-success); }
.trend-change.declining { color: var(--color-error); }
.trend-change.stable { color: var(--text-secondary); }

.trend-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: capitalize;
}

/* Charts Section */
.charts-section {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-6);
}

.chart-container {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  padding: var(--spacing-4);
}

/* Patterns Section */
.patterns-section {
  margin-top: var(--spacing-6);
}

.section-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-5);
}

.pattern-table {
  margin-bottom: var(--spacing-6);
}

.table-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.icon-success { color: var(--color-success); }
.icon-info { color: var(--color-info); }

.cell-primary {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

/* Empty state detail text */
.empty-detail {
  color: var(--text-secondary);
  max-width: 500px;
  margin: 0 auto;
  font-size: var(--text-sm);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow: auto;
  box-shadow: var(--shadow-2xl);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.modal-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--text-lg);
  cursor: pointer;
  padding: var(--spacing-1);
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-5);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

/* Form Styles */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
}

.field-group label {
  display: block;
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
  font-size: var(--text-sm);
}

.form-help {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.error-message {
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

@media (max-width: 768px) {
  .filter-row { flex-direction: column; }
  .filter-actions { margin-left: 0; width: 100%; }
  .form-row { grid-template-columns: 1fr; }
  .analysis-summary { grid-template-columns: 1fr 1fr; }
}
</style>
