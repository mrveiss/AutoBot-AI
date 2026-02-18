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
        <h1 class="page-title">Code Evolution</h1>
        <p class="page-subtitle">
          Track how code patterns and quality metrics evolve over time
        </p>
      </div>
      <button
        @click="showAnalysisModal = true"
        class="btn btn-primary"
        :disabled="evolution.loading.value"
      >
        <i class="fas fa-play-circle"></i>
        Analyze Repository
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
          <div class="summary-label">Commits Analyzed</div>
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
          <div class="summary-label">Emerging Patterns</div>
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
          <div class="summary-label">Declining Patterns</div>
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
          <div class="summary-label">Refactorings Detected</div>
        </div>
      </div>
    </div>

    <!-- Filter Controls (Issue #247) -->
    <div class="filter-panel">
      <div class="filter-row">
        <div class="filter-group">
          <label class="filter-label">Start Date</label>
          <input v-model="filters.startDate" type="date" class="form-input filter-input" />
        </div>
        <div class="filter-group">
          <label class="filter-label">End Date</label>
          <input v-model="filters.endDate" type="date" class="form-input filter-input" />
        </div>
        <div class="filter-group">
          <label class="filter-label">Granularity</label>
          <select v-model="filters.granularity" class="form-input filter-input">
            <option value="hourly">Hourly</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Trend Period</label>
          <select v-model="filters.trendDays" class="form-input filter-input">
            <option :value="7">7 days</option>
            <option :value="30">30 days</option>
            <option :value="90">90 days</option>
            <option :value="180">180 days</option>
            <option :value="365">1 year</option>
          </select>
        </div>
        <div class="filter-actions">
          <button
            @click="applyFilters"
            class="btn btn-primary"
            :disabled="evolution.loading.value"
          >
            <i class="fas fa-filter"></i>
            Apply Filters
          </button>
          <div class="export-group">
            <button
              @click="evolution.exportData('json', filters.startDate, filters.endDate)"
              class="btn btn-secondary"
              title="Export as JSON"
            >
              <i class="fas fa-file-code"></i>
              JSON
            </button>
            <button
              @click="evolution.exportData('csv', filters.startDate, filters.endDate)"
              class="btn btn-secondary"
              title="Export as CSV"
            >
              <i class="fas fa-file-csv"></i>
              CSV
            </button>
          </div>
        </div>
      </div>
      <!-- Metric Selector -->
      <div class="metric-selector">
        <span class="filter-label">Metrics:</span>
        <label v-for="m in availableMetrics" :key="m.value" class="metric-checkbox">
          <input type="checkbox" :value="m.value" v-model="filters.selectedMetrics" />
          {{ m.label }}
        </label>
      </div>
    </div>

    <!-- Quality Trends (Issue #247) -->
    <div v-if="evolution.hasTrendsData.value" class="trends-section">
      <h2 class="section-title">Quality Trends ({{ filters.trendDays }} days)</h2>
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
      <h2 class="section-title">Pattern Details</h2>

      <!-- Emerging Patterns -->
      <div v-if="evolution.analysisResult.value?.emerging_patterns.length" class="pattern-table">
        <h3 class="table-title">
          <i class="fas fa-arrow-trend-up text-green-500"></i>
          Emerging Patterns
        </h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>Pattern Type</th>
              <th>Count</th>
              <th>First Seen</th>
              <th>Last Seen</th>
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pattern in evolution.analysisResult.value?.emerging_patterns" :key="pattern.pattern_type">
              <td class="font-medium">{{ formatPatternName(pattern.pattern_type) }}</td>
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
          <i class="fas fa-arrow-trend-down text-autobot-info"></i>
          Declining Patterns
        </h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>Pattern Type</th>
              <th>Count</th>
              <th>First Seen</th>
              <th>Last Seen</th>
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pattern in evolution.analysisResult.value?.declining_patterns" :key="pattern.pattern_type">
              <td class="font-medium">{{ formatPatternName(pattern.pattern_type) }}</td>
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
      <i class="fas fa-chart-line fa-3x text-autobot-text-muted"></i>
      <h3 class="empty-title">No Evolution Data</h3>
      <p class="empty-text">
        Click "Analyze Repository" to start analyzing git history and track code evolution
      </p>
    </div>

    <!-- Analysis Modal -->
    <div v-if="showAnalysisModal" class="modal-overlay" @click.self="showAnalysisModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">Analyze Repository</h3>
          <button @click="showAnalysisModal = false" class="modal-close">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label>Repository Path</label>
            <input
              v-model="analysisForm.repo_path"
              type="text"
              class="form-input"
              placeholder="/opt/autobot"
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Start Date (Optional)</label>
              <input
                v-model="analysisForm.start_date"
                type="date"
                class="form-input"
              />
            </div>

            <div class="form-group">
              <label>End Date (Optional)</label>
              <input
                v-model="analysisForm.end_date"
                type="date"
                class="form-input"
              />
            </div>
          </div>

          <div class="form-group">
            <label>Commit Limit</label>
            <input
              v-model.number="analysisForm.commit_limit"
              type="number"
              min="1"
              max="1000"
              class="form-input"
            />
            <p class="form-help">Maximum number of commits to analyze (1-1000)</p>
          </div>

          <div v-if="evolution.error.value" class="error-message">
            <i class="fas fa-exclamation-triangle"></i>
            {{ evolution.error.value }}
          </div>
        </div>

        <div class="modal-footer">
          <button @click="showAnalysisModal = false" class="btn btn-secondary">
            Cancel
          </button>
          <button
            @click="runAnalysis"
            class="btn btn-primary"
            :disabled="!analysisForm.repo_path || evolution.loading.value"
          >
            <i class="fas fa-spinner fa-spin" v-if="evolution.loading.value"></i>
            <i class="fas fa-play-circle" v-else></i>
            {{ evolution.loading.value ? 'Analyzing...' : 'Start Analysis' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useEvolution } from '@/composables/useEvolution'
import EvolutionTimelineChart from '@/components/charts/EvolutionTimelineChart.vue'
import PatternEvolutionChart from '@/components/charts/PatternEvolutionChart.vue'

const evolution = useEvolution()
const showAnalysisModal = ref(false)

// Filter state (Issue #247)
const filters = ref({
  startDate: '',
  endDate: '',
  granularity: 'daily',
  trendDays: 30,
  selectedMetrics: ['overall_score', 'maintainability', 'complexity'],
})

const availableMetrics = [
  { value: 'overall_score', label: 'Overall' },
  { value: 'maintainability', label: 'Maintainability' },
  { value: 'complexity', label: 'Complexity' },
  { value: 'testability', label: 'Testability' },
  { value: 'documentation', label: 'Documentation' },
  { value: 'security', label: 'Security' },
  { value: 'performance', label: 'Performance' },
]

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
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
}

.page-title {
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 0.5rem;
}

.page-subtitle {
  color: var(--color-text-secondary);
  font-size: 1rem;
}

/* Analysis Summary */
.analysis-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.summary-icon.success {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.summary-icon.emerging {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.summary-icon.declining {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.summary-icon.refactor {
  background: rgba(139, 92, 246, 0.1);
  color: #8b5cf6;
}

.summary-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1;
}

.summary-label {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin-top: 0.25rem;
}

/* Filter Panel (Issue #247) */
.filter-panel {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.filter-row {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 140px;
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-input {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
}

.filter-actions {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  margin-left: auto;
  flex-wrap: wrap;
}

.export-group {
  display: flex;
  gap: 0.5rem;
}

.metric-selector {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
  flex-wrap: wrap;
}

.metric-checkbox {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
  color: var(--color-text);
  cursor: pointer;
  user-select: none;
}

.metric-checkbox input[type='checkbox'] {
  cursor: pointer;
  accent-color: var(--color-primary);
}

/* Trends Section (Issue #247) */
.trends-section {
  margin-bottom: 2rem;
}

.trends-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1rem;
}

.trend-card {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  padding: 1.25rem;
  text-align: center;
}

.trend-metric {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.trend-value {
  font-size: 2rem;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 0.5rem;
}

.trend-value.improving {
  color: #10b981;
}
.trend-value.declining {
  color: #ef4444;
}
.trend-value.stable {
  color: var(--color-text);
}

.trend-change {
  font-size: 0.875rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  margin-bottom: 0.25rem;
}

.trend-change.improving {
  color: #10b981;
}
.trend-change.declining {
  color: #ef4444;
}
.trend-change.stable {
  color: var(--color-text-secondary);
}

.trend-label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  text-transform: capitalize;
}

/* Charts Section */
.charts-section {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.chart-container {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  padding: 1rem;
}

/* Patterns Section */
.patterns-section {
  margin-top: 2rem;
}

.section-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 1.5rem;
}

.pattern-table {
  margin-bottom: 2rem;
}

.table-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.data-table {
  width: 100%;
  background: var(--bg-secondary);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.data-table thead {
  background: var(--bg-tertiary);
}

.data-table th,
.data-table td {
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.data-table th {
  font-weight: 600;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
  text-transform: uppercase;
}

.data-table td {
  color: var(--color-text);
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: capitalize;
}

.badge-success {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.badge-info {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.empty-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text);
  margin: 1rem 0 0.5rem;
}

.empty-text {
  color: var(--color-text-secondary);
  max-width: 500px;
  margin: 0 auto;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow: auto;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid var(--color-border);
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text);
}

.modal-close {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0.25rem;
}

.modal-close:hover {
  color: var(--color-text);
}

.modal-body {
  padding: 1.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid var(--color-border);
}

/* Form Styles */
.form-group {
  margin-bottom: 1.5rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-group label {
  display: block;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
}

.form-input {
  width: 100%;
  padding: 0.75rem;
  background: var(--bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  font-size: 1rem;
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-help {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-top: 0.25rem;
}

.error-message {
  padding: 0.75rem 1rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

/* Button Styles */
.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-secondary);
}
</style>
