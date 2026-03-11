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
