<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Stats and Charts section -->
<template>
  <div>
    <!-- Codebase Statistics -->
    <div class="stats-section">
      <h3>
        <i class="fas fa-chart-pie"></i> {{ $t('analytics.codebase.stats.title') }}
        <div class="section-export-buttons">
          <button
            @click="emit('export-section', 'statistics', 'md')"
            class="export-btn"
            :disabled="!codebaseStats"
            :title="$t('analytics.codebase.actions.exportMarkdown')"
          >
            <i class="fas fa-file-alt"></i> MD
          </button>
          <button
            @click="emit('export-section', 'statistics', 'json')"
            class="export-btn"
            :disabled="!codebaseStats"
            :title="$t('analytics.codebase.actions.exportJson')"
          >
            <i class="fas fa-file-code"></i> JSON
          </button>
        </div>
      </h3>
      <div v-if="codebaseStats" class="stats-grid">
        <BasePanel variant="elevated" size="small">
          <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.totalFiles') }}</div>
        </BasePanel>
        <BasePanel variant="elevated" size="small">
          <div class="stat-value">{{ codebaseStats.total_lines || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.linesOfCode') }}</div>
        </BasePanel>
        <BasePanel variant="elevated" size="small">
          <div class="stat-value">{{ codebaseStats.total_functions || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.functions') }}</div>
        </BasePanel>
        <BasePanel variant="elevated" size="small">
          <div class="stat-value">{{ codebaseStats.total_classes || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.classes') }}</div>
        </BasePanel>
      </div>
      <EmptyState
        v-else
        icon="fas fa-chart-bar"
        :message="$t('analytics.codebase.stats.noData')"
      />
    </div>

    <!-- Analytics Charts Section -->
    <div class="charts-section">
      <div class="section-header">
        <h3><i class="fas fa-chart-bar"></i> {{ $t('analytics.codebase.problems.title') }}</h3>
        <div class="section-header-actions">
          <button
            @click="emit('load-unified-report')"
            class="refresh-btn"
            :disabled="unifiedReportLoading"
            :title="$t('analytics.codebase.problems.loadReport')"
          >
            <i :class="unifiedReportLoading ? 'fas fa-spinner fa-spin' : 'fas fa-layer-group'"></i>
          </button>
          <button
            @click="emit('load-chart-data')"
            class="refresh-btn"
            :disabled="chartDataLoading"
            :title="$t('analytics.codebase.actions.refreshCharts')"
          >
            <i :class="chartDataLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>
      </div>

      <!-- Category Filter Tabs -->
      <div class="category-tabs" v-if="availableCategories.length > 0 || chartData">
        <button
          @click="emit('update:selected-category', 'all')"
          class="category-tab"
          :class="{ active: selectedCategory === 'all' }"
        >
          <i class="fas fa-th-large"></i>
          {{ $t('analytics.codebase.problems.allIssues') }}
          <span class="tab-count" v-if="chartData?.summary?.total_problems">
            {{ chartData.summary.total_problems.toLocaleString() }}
          </span>
        </button>
        <button
          v-for="cat in availableCategories"
          :key="cat.id"
          @click="emit('update:selected-category', cat.id)"
          class="category-tab"
          :class="{ active: selectedCategory === cat.id }"
        >
          <i :class="getCategoryIcon(cat.id)"></i>
          {{ cat.name }}
          <span class="tab-count">{{ cat.count }}</span>
        </button>
      </div>

      <!-- Unified Report Error -->
      <div v-if="unifiedReportError" class="charts-error">
        <i class="fas fa-exclamation-triangle"></i>
        <span>{{ unifiedReportError }}</span>
        <button @click="emit('load-unified-report')" class="btn-link">
          {{ $t('analytics.codebase.actions.retry') }}
        </button>
      </div>

      <div v-if="chartDataLoading" class="charts-loading">
        <i class="fas fa-spinner fa-spin"></i>
        <span>{{ $t('analytics.codebase.problems.loadingChartData') }}</span>
      </div>

      <div v-else-if="chartDataError" class="charts-error">
        <i class="fas fa-exclamation-triangle"></i>
        <span>{{ chartDataError }}</span>
        <button @click="emit('load-chart-data')" class="btn-link">
          {{ $t('analytics.codebase.actions.retry') }}
        </button>
      </div>

      <div v-else-if="chartData" class="charts-grid">
        <!-- Summary Stats -->
        <div v-if="chartData.summary" class="chart-summary">
          <div class="summary-stat">
            <span class="summary-value">
              {{ chartData.summary.total_problems?.toLocaleString() || 0 }}
            </span>
            <span class="summary-label">{{ $t('analytics.codebase.problems.totalProblems') }}</span>
          </div>
          <div class="summary-stat">
            <span class="summary-value">{{ chartData.summary.unique_problem_types || 0 }}</span>
            <span class="summary-label">{{ $t('analytics.codebase.problems.problemTypes') }}</span>
          </div>
          <div class="summary-stat">
            <span class="summary-value">{{ chartData.summary.files_with_problems || 0 }}</span>
            <span class="summary-label">{{ $t('analytics.codebase.problems.filesAffected') }}</span>
          </div>
          <div class="summary-stat race-highlight">
            <span class="summary-value">{{ chartData.summary.race_condition_count || 0 }}</span>
            <span class="summary-label">{{ $t('analytics.codebase.problems.raceConditions') }}</span>
          </div>
        </div>

        <!-- Charts Row 1: Problem Types + Severity -->
        <div class="charts-row">
          <ProblemTypesChart
            v-if="filteredChartData?.problem_types && filteredChartData.problem_types.length > 0"
            :data="filteredChartData.problem_types"
            :title="
              selectedCategory === 'all'
                ? 'Problem Types Distribution'
                : `${selectedCategory.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())} Issues`
            "
            :height="320"
            class="chart-item"
          />
          <div v-else class="chart-empty-slot">
            <EmptyState
              icon="fas fa-chart-pie"
              :message="
                selectedCategory === 'all'
                  ? 'No problem type data'
                  : `No issues in ${selectedCategory.replace(/_/g, ' ')} category`
              "
            />
          </div>
          <SeverityBarChart
            v-if="chartData.severity_counts && chartData.severity_counts.length > 0"
            :data="chartData.severity_counts"
            :title="$t('analytics.codebase.charts.problemsBySeverity')"
            :height="320"
            class="chart-item"
          />
          <div v-else class="chart-empty-slot">
            <EmptyState icon="fas fa-signal" message="No severity data" />
          </div>
        </div>

        <!-- Charts Row 2: Race Conditions + Top Files -->
        <div class="charts-row">
          <RaceConditionsDonut
            v-if="chartData.race_conditions && chartData.race_conditions.length > 0"
            :data="chartData.race_conditions"
            :title="$t('analytics.codebase.charts.raceConditionsByCategory')"
            :height="320"
            class="chart-item"
          />
          <div v-else class="chart-empty-slot">
            <EmptyState icon="fas fa-exclamation-circle" message="No race condition data" />
          </div>
          <TopFilesChart
            v-if="chartData.top_files && chartData.top_files.length > 0"
            :data="chartData.top_files"
            :title="$t('analytics.codebase.charts.topFilesWithProblems')"
            :height="400"
            :maxFiles="10"
            class="chart-item"
          />
          <div v-else class="chart-empty-slot">
            <EmptyState icon="fas fa-file-code" message="No file data" />
          </div>
        </div>
      </div>

      <EmptyState
        v-else
        icon="fas fa-chart-area"
        :message="$t('analytics.codebase.problems.noChartData')"
      >
        <template #actions>
          <button @click="emit('index-codebase')" class="btn-primary" :disabled="analyzing">
            <i class="fas fa-database"></i> {{ $t('analytics.codebase.buttons.indexCodebase') }}
          </button>
        </template>
      </EmptyState>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import {
  ProblemTypesChart,
  SeverityBarChart,
  RaceConditionsDonut,
  TopFilesChart,
} from '@/components/charts'

interface ChartDataItem {
  name: string
  value: number
  type?: string
  [key: string]: unknown
}

interface ChartDataSummary {
  total_problems?: number
  unique_problem_types?: number
  files_with_problems?: number
  race_condition_count?: number
}

interface ChartData {
  summary?: ChartDataSummary
  problem_types?: ChartDataItem[]
  severity_counts?: ChartDataItem[]
  race_conditions?: ChartDataItem[]
  top_files?: ChartDataItem[]
  [key: string]: unknown
}

interface AvailableCategory {
  id: string
  name: string
  count: number
}

const props = defineProps<{
  codebaseStats: Record<string, unknown> | null
  chartData: ChartData | null
  chartDataLoading: boolean
  chartDataError: string
  unifiedReportLoading: boolean
  unifiedReportError: string
  selectedCategory: string
  availableCategories: AvailableCategory[]
  analyzing: boolean
}>()

const emit = defineEmits<{
  'export-section': [section: string, format: string]
  'load-unified-report': []
  'load-chart-data': []
  'update:selected-category': [value: string]
  'index-codebase': []
}>()

const filteredChartData = computed((): ChartData | null => {
  if (!props.chartData) return null
  if (props.selectedCategory === 'all') return props.chartData

  const filtered: ChartData = { ...props.chartData }

  if (filtered.problem_types) {
    filtered.problem_types = filtered.problem_types.filter((pt: ChartDataItem) => {
      const type = pt.type?.toLowerCase() || ''
      const category = props.selectedCategory.toLowerCase()
      return type.includes(category) || category.includes(type)
    })
  }

  return filtered
})

function getCategoryIcon(categoryId: string): string {
  const iconMap: Record<string, string> = {
    race_conditions: 'fas fa-random',
    debug_code: 'fas fa-bug',
    complexity: 'fas fa-project-diagram',
    code_smells: 'fas fa-exclamation-circle',
    performance: 'fas fa-tachometer-alt',
    security: 'fas fa-shield-alt',
    long_functions: 'fas fa-scroll',
    duplicate_code: 'fas fa-clone',
    hardcoded_values: 'fas fa-lock',
    missing_types: 'fas fa-question-circle',
    unused_imports: 'fas fa-unlink',
    default: 'fas fa-tag',
  }
  return iconMap[categoryId] || iconMap.default
}
</script>

<style scoped>
.charts-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.charts-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.charts-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.charts-section .section-header h3 i {
  color: var(--chart-blue);
}

.section-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* Category Filter Tabs */
.category-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
  padding: 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.category-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(51, 65, 85, 0.5);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.category-tab:hover {
  background: rgba(71, 85, 105, 0.5);
  color: var(--text-secondary);
  border-color: rgba(100, 116, 139, 0.5);
}

.category-tab.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary);
}

.category-tab i {
  font-size: 0.875rem;
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}

.category-tab.active .tab-count {
  background: rgba(255, 255, 255, 0.2);
}

.charts-loading,
.charts-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 12px;
  color: var(--text-muted);
}

.charts-loading i {
  font-size: 32px;
  color: var(--chart-blue);
}

.charts-error i {
  font-size: 32px;
  color: var(--color-error);
}

.charts-error {
  color: var(--color-error-light);
}

.charts-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.chart-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.summary-stat {
  background: rgba(51, 65, 85, 0.5);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid rgba(71, 85, 105, 0.5);
  transition: all 0.2s ease;
}

.summary-stat:hover {
  background: rgba(51, 65, 85, 0.7);
  border-color: rgba(59, 130, 246, 0.5);
}

.summary-stat.race-highlight {
  background: rgba(249, 115, 22, 0.2);
  border-color: rgba(249, 115, 22, 0.5);
}

.summary-stat.race-highlight:hover {
  background: rgba(249, 115, 22, 0.3);
}

.summary-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-secondary);
  line-height: 1;
}

.summary-stat.race-highlight .summary-value {
  color: var(--chart-orange);
}

.summary-label {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 4px;
  display: block;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

/* Chart items (BaseChart components) - minimal layout adjustment */
.chart-item {
  min-height: 350px;
}

/* Empty state placeholder (when chart has no data) */
.chart-empty-slot {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  min-height: 350px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Responsive charts */
@media (max-width: 1200px) {
  .chart-summary {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .chart-summary {
    grid-template-columns: 1fr;
  }

  .summary-value {
    font-size: 1.5rem;
  }
}

/* Dependency Section Styles */
.dependency-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dependency-section .section-header h3 i {
  color: var(--chart-purple);
}

.dependency-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Circular Dependencies Warning */
.circular-deps-warning {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 16px;
}

.circular-deps-warning .warning-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--color-error-light);
  margin-bottom: 12px;
}

.circular-deps-warning .warning-header i {
  color: var(--color-error);
}

.circular-deps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.circular-dep-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.circular-dep-item i {
  color: var(--color-warning);
}

/* External Dependencies Table */
.external-deps-table {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.external-deps-table h4 {
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.external-deps-table h4 i {
  color: var(--chart-teal);
}

.deps-table-content {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.dep-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(51, 65, 85, 0.4);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dep-row:hover {
  background: rgba(51, 65, 85, 0.6);
}

.dep-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.dep-count {
  font-size: 0.8rem;
  color: var(--text-muted);
  background: rgba(59, 130, 246, 0.2);
  padding: 2px 8px;
  border-radius: 4px;
}

/* Import Tree Section */
.import-tree-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.import-tree-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.import-tree-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-tree-section .section-header h3 i {
  color: var(--chart-teal);
}

.import-tree-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--color-error-light);
}

.import-tree-section .section-error i {
  color: var(--color-error);
}

.import-tree-content {
  margin-top: 16px;
}

/* Call Graph Section */
.call-graph-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.call-graph-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.call-graph-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.call-graph-section .section-header h3 i {
  color: var(--chart-purple);
}

.call-graph-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--color-error-light);
}

.call-graph-section .section-error i {
  color: var(--color-error);
}

.call-graph-content {
  margin-top: 16px;
}

/* Issue #527: API Endpoint Checker Section */

</style>
