<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Stats and Charts section -->
<template>
  <div>
    <!-- Codebase Statistics -->
    <div class="stats-section">
      <h3>
        <Icon name="chart-pie" /> {{ $t('analytics.codebase.stats.title') }}
        <div class="section-export-buttons">
          <button
            @click="emit('export-section', 'statistics', 'md')"
            class="export-btn"
            :disabled="!codebaseStats"
            :title="$t('analytics.codebase.actions.exportMarkdown')"
          >
            <Icon name="file-alt" /> MD
          </button>
          <button
            @click="emit('export-section', 'statistics', 'json')"
            class="export-btn"
            :disabled="!codebaseStats"
            :title="$t('analytics.codebase.actions.exportJson')"
          >
            <Icon name="file-code" /> JSON
          </button>
        </div>
      </h3>
      <div v-if="codebaseStats" class="stats-grid">
        <BasePanel variant="elevated" size="sm">
          <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.totalFiles') }}</div>
        </BasePanel>
        <BasePanel variant="elevated" size="sm">
          <div class="stat-value">{{ codebaseStats.total_lines || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.linesOfCode') }}</div>
        </BasePanel>
        <BasePanel variant="elevated" size="sm">
          <div class="stat-value">{{ codebaseStats.total_functions || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.functions') }}</div>
        </BasePanel>
        <BasePanel variant="elevated" size="sm">
          <div class="stat-value">{{ codebaseStats.total_classes || 0 }}</div>
          <div class="stat-label">{{ $t('analytics.codebase.stats.classes') }}</div>
        </BasePanel>
      </div>
      <EmptyState
        v-else
        icon="chart-bar"
        :message="$t('analytics.codebase.stats.noData')"
      />
    </div>

    <!-- Analytics Charts Section -->
    <div class="charts-section">
      <div class="section-header">
        <h3><Icon name="chart-bar" /> {{ $t('analytics.codebase.problems.title') }}</h3>
        <div class="section-header-actions">
          <button
            @click="emit('load-unified-report')"
            class="refresh-btn"
            :disabled="unifiedReportLoading"
            :title="$t('analytics.codebase.problems.loadReport')"
          >
            <i :class="unifiedReportLoading ? 'fas fa-spinner fa-spin' : 'layer-group'"></i>
          </button>
          <button
            @click="emit('load-chart-data')"
            class="refresh-btn"
            :disabled="chartDataLoading"
            :title="$t('analytics.codebase.actions.refreshCharts')"
          >
            <i :class="chartDataLoading ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
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
          <Icon name="th-large" />
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
          <Icon :name="getCategoryIcon(cat.id)" />
          {{ cat.name }}
          <span class="tab-count">{{ cat.count }}</span>
        </button>
      </div>

      <!-- Unified Report Error -->
      <div v-if="unifiedReportError" class="charts-error">
        <Icon name="exclamation-triangle" />
        <span>{{ unifiedReportError }}</span>
        <button @click="emit('load-unified-report')" class="btn-link">
          {{ $t('analytics.codebase.actions.retry') }}
        </button>
      </div>

      <div v-if="chartDataLoading" class="charts-loading">
        <Icon name="spinner" class="animate-spin" />
        <span>{{ $t('analytics.codebase.problems.loadingChartData') }}</span>
      </div>

      <div v-else-if="chartDataError" class="charts-error">
        <Icon name="exclamation-triangle" />
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
              icon="chart-pie"
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
            <EmptyState icon="signal" message="No severity data" />
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
            <EmptyState icon="exclamation-circle" message="No race condition data" />
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
            <EmptyState icon="file-code" message="No file data" />
          </div>
        </div>
      </div>

      <EmptyState
        v-else
        icon="chart-area"
        :message="$t('analytics.codebase.problems.noChartData')"
      >
        <template #actions>
          <button @click="emit('index-codebase')" class="btn-primary" :disabled="analyzing">
            <Icon name="database" /> {{ $t('analytics.codebase.buttons.indexCodebase') }}
          </button>
        </template>
      </EmptyState>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
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
  'export-section': [section: string, format: 'md' | 'json']
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
    race_conditions: 'random',
    debug_code: 'bug',
    complexity: 'project-diagram',
    code_smells: 'exclamation-circle',
    performance: 'tachometer-alt',
    security: 'shield-alt',
    long_functions: 'scroll',
    duplicate_code: 'clone',
    hardcoded_values: 'lock',
    missing_types: 'question-circle',
    unused_imports: 'unlink',
    default: 'tag',
  }
  return iconMap[categoryId] || iconMap.default
}
</script>

<style scoped>
/* Codebase Statistics Section (#4063: Fix rendering gaps) */
.stats-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  contain: layout style;}

.stats-section h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-5) var(--spacing-0);
  color: var(--text-secondary);
  font-size: var(--text-xl);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-2);
}

.stats-section h3 i {
  color: var(--chart-green);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-4);
}

.section-export-buttons {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

.export-btn {
  background: rgba(51, 65, 85, 0.5);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-out);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.export-btn:hover:not(:disabled) {
  background: rgba(71, 85, 105, 0.5);
  color: var(--text-secondary);
  border-color: rgba(100, 116, 139, 0.5);
}

.export-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Responsive stats grid */
@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

.charts-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.charts-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.charts-section .section-header h3 {
  margin: var(--spacing-0);
  color: var(--text-secondary);
  font-size: var(--text-xl);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.charts-section .section-header h3 i {
  color: var(--chart-blue);
}

.section-header-actions {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

/* Category Filter Tabs */
.category-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-5);
  padding: var(--spacing-3);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.category-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: rgba(51, 65, 85, 0.5);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-out);
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
  font-size: var(--text-sm);
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: var(--spacing-0) var(--spacing-1-5);
  background: rgba(0, 0, 0, 0.2);
  border-radius: var(--radius-xl);
  font-size: var(--text-xs);
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
  gap: var(--spacing-3);
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
  gap: var(--spacing-6);
}

.chart-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.summary-stat {
  background: rgba(51, 65, 85, 0.5);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  text-align: center;
  border: 1px solid rgba(71, 85, 105, 0.5);
  transition: all var(--duration-200) var(--ease-out);
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
  margin-top: var(--spacing-1);
  display: block;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-5);
}

/* Chart items (BaseChart components) - minimal layout adjustment */
.chart-item {
  min-height: 350px;
}

/* Empty state placeholder (when chart has no data) */
.chart-empty-slot {
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
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
    font-size: var(--text-2xl);
  }
}

/* Dependency Section Styles */
.dependency-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header h3 {
  margin: var(--spacing-0);
  color: var(--text-secondary);
  font-size: var(--text-xl);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.dependency-section .section-header h3 i {
  color: var(--chart-purple);
}

.dependency-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* Circular Dependencies Warning */
.circular-deps-warning {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.circular-deps-warning .warning-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: 600;
  color: var(--color-error-light);
  margin-bottom: var(--spacing-3);
}

.circular-deps-warning .warning-header i {
  color: var(--color-error);
}

.circular-deps-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.circular-dep-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-default);
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
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.external-deps-table h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4) var(--spacing-0);
  color: var(--text-secondary);
  font-size: var(--text-base);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.external-deps-table h4 i {
  color: var(--chart-teal);
}

.deps-table-content {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--spacing-2);
}

.dep-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2) var(--spacing-3);
  background: rgba(51, 65, 85, 0.4);
  border-radius: var(--radius-default);
  transition: background var(--duration-200) var(--ease-out);
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
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
}

/* Import Tree Section */
.import-tree-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.import-tree-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
}

.import-tree-section .section-header h3 {
  margin: var(--spacing-0);
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.import-tree-section .section-header h3 i {
  color: var(--chart-teal);
}

.import-tree-section .section-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-3);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-lg);
  color: var(--color-error-light);
}

.import-tree-section .section-error i {
  color: var(--color-error);
}

.import-tree-content {
  margin-top: var(--spacing-4);
}

/* Call Graph Section */
.call-graph-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.call-graph-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
}

.call-graph-section .section-header h3 {
  margin: var(--spacing-0);
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.call-graph-section .section-header h3 i {
  color: var(--chart-purple);
}

.call-graph-section .section-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-3);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-lg);
  color: var(--color-error-light);
}

.call-graph-section .section-error i {
  color: var(--color-error);
}

.call-graph-content {
  margin-top: var(--spacing-4);
}

/* Issue #527: API Endpoint Checker Section */

</style>
