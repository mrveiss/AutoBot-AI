<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Environment Analysis section (#538) -->
<template>
  <div class="environment-analysis-section analytics-section">
    <h3>
      <i class="fas fa-leaf"></i> {{ $t('analytics.codebase.environment.title') }}
      <span v-if="analysis" class="total-count">
        ({{ analysis.total_hardcoded_values }} hardcoded values)
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

    <!-- AI Filtering Toggle (#633) -->
    <div
      class="ai-filter-controls"
      style="margin-bottom: 15px; padding: 10px; background: rgba(0,0,0,0.2);
             border-radius: 6px; display: flex; align-items: center; gap: 15px; flex-wrap: wrap;"
    >
      <label
        class="toggle-label"
        style="display: flex; align-items: center; gap: 8px; cursor: pointer;"
      >
        <input
          type="checkbox"
          :checked="useAiFiltering"
          @change="emit('update:use-ai-filtering', ($event.target as HTMLInputElement).checked)"
          style="width: 18px; height: 18px; cursor: pointer;"
        />
        <span style="font-weight: 500;">
          <i class="fas fa-robot"></i> {{ $t('analytics.codebase.environment.useAiFiltering') }}
        </span>
      </label>
      <span
        v-if="useAiFiltering"
        class="ai-filter-options"
        style="display: flex; align-items: center; gap: 10px;"
      >
        <select
          :value="aiFilteringPriority"
          @change="emit('update:ai-filtering-priority', ($event.target as HTMLSelectElement).value)"
          class="ai-filter-select"
        >
          <option value="high">{{ $t('analytics.codebase.environment.highPriorityOnly') }}</option>
          <option value="medium">{{ $t('analytics.codebase.environment.mediumPriority') }}</option>
          <option value="low">{{ $t('analytics.codebase.environment.lowPriority') }}</option>
          <option value="all">{{ $t('analytics.codebase.environment.allPriorities') }}</option>
        </select>
        <span class="ai-filter-model-hint">Model: {{ aiFilteringModel }}</span>
      </span>
      <span v-if="llmFilteringResult" class="llm-result-badge">
        <i class="fas fa-check-circle"></i>
        {{ llmFilteringResult.original_count }} → {{ llmFilteringResult.filtered_count }}
        ({{ llmFilteringResult.reduction_percent }}% reduced)
      </span>
    </div>

    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      {{ useAiFiltering ? 'Scanning with AI filtering...' : 'Scanning for hardcoded values...' }}
    </div>

    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i> {{ error }}
      <button @click="emit('refresh')" class="btn-link">
        {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <div
      v-else-if="analysis && analysis.total_hardcoded_values > 0"
      class="section-content"
    >
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">{{ analysis.total_hardcoded_values }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.environment.hardcodedValues') }}</div>
        </div>
        <div class="summary-card critical">
          <div class="summary-value">{{ analysis.high_priority_count }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.environment.highPriority') }}</div>
        </div>
        <div class="summary-card warning">
          <div class="summary-value">{{ analysis.recommendations_count }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.environment.recommendations') }}</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ Object.keys(analysis.categories).length }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.environment.categories') }}</div>
        </div>
      </div>

      <div
        v-if="Object.keys(analysis.categories).length > 0"
        class="categories-breakdown"
      >
        <h4>{{ $t('analytics.codebase.environment.categories') }}</h4>
        <div class="category-badges">
          <span
            v-for="(count, category) in analysis.categories"
            :key="category"
            class="category-badge"
          >
            {{ formatFactorName(String(category)) }}: {{ count }}
          </span>
        </div>
      </div>

      <div v-if="analysis.recommendations.length > 0" class="recommendations-list">
        <h4>{{ $t('analytics.codebase.environment.envVarRecommendations') }}</h4>
        <div
          v-for="(rec, index) in analysis.recommendations.slice(0, 10)"
          :key="'rec-' + index"
          class="recommendation-item"
          :class="'priority-' + rec.priority"
        >
          <div class="rec-header">
            <code class="env-var-name">{{ rec.env_var_name }}</code>
            <span class="priority-badge" :class="rec.priority">{{ rec.priority }}</span>
          </div>
          <div class="rec-description">{{ rec.description }}</div>
          <div class="rec-default">
            Default: <code>{{ truncateValue(rec.default_value, 50) }}</code>
          </div>
        </div>
        <div v-if="analysis.recommendations.length > 10" class="show-more">
          <span class="muted">
            Showing 10 of {{ analysis.recommendations.length }} recommendations
          </span>
        </div>
      </div>

      <div v-if="analysis.hardcoded_values.length > 0" class="hardcoded-preview">
        <h4>
          {{ $t('analytics.codebase.environment.sampleHardcodedValues') }}
          <span
            v-if="
              analysis.is_truncated ||
              analysis.hardcoded_values.length < analysis.total_hardcoded_values
            "
            class="truncation-warning"
          >
            (showing {{ analysis.hardcoded_values.length }} of
            {{ analysis.total_hardcoded_values.toLocaleString() }} - use Export for full data)
          </span>
        </h4>
        <div
          v-for="(hv, index) in analysis.hardcoded_values.slice(0, 8)"
          :key="'hv-' + index"
          class="hardcoded-item"
          :class="'severity-' + hv.severity"
        >
          <div class="hv-location">
            <span class="file-path">{{ hv.file }}</span>
            <span class="line-number">:{{ hv.line }}</span>
          </div>
          <div class="hv-value">
            <code>{{ truncateValue(hv.value, 60) }}</code>
            <span class="value-type">{{ hv.type }}</span>
          </div>
          <div v-if="hv.suggested_env_var" class="hv-suggestion">
            <i class="fas fa-lightbulb"></i> Use: <code>{{ hv.suggested_env_var }}</code>
          </div>
        </div>
      </div>

      <div class="scan-timestamp">
        <i class="fas fa-clock"></i>
        Analysis completed in {{ analysis.analysis_time_seconds.toFixed(2) }}s
      </div>
    </div>

    <div
      v-else-if="analysis && analysis.total_hardcoded_values === 0"
      class="success-state"
    >
      <i class="fas fa-check-circle"></i>
      {{ $t('analytics.codebase.environment.noHardcodedValues') }}
    </div>

    <EmptyState
      v-else
      icon="fas fa-leaf"
      :message="$t('analytics.codebase.environment.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'

interface HardcodedValue {
  file: string
  line: number
  variable_name?: string
  value: string
  type: string
  severity: string
  suggested_env_var: string
}

interface EnvRecommendation {
  env_var_name: string
  default_value: string
  description: string
  category: string
  priority: string
}

interface EnvironmentAnalysisResult {
  total_hardcoded_values: number
  high_priority_count: number
  recommendations_count: number
  categories: Record<string, number>
  analysis_time_seconds: number
  hardcoded_values: HardcodedValue[]
  recommendations: EnvRecommendation[]
  is_truncated?: boolean
}

interface LLMFilteringResult {
  enabled: boolean
  model: string
  original_count: number
  filtered_count: number
  reduction_percent: number
  filter_priority: string | null
}

const props = defineProps<{
  analysis: EnvironmentAnalysisResult | null
  loading: boolean
  error: string
  useAiFiltering: boolean
  aiFilteringModel: string
  aiFilteringPriority: string
  llmFilteringResult: LLMFilteringResult | null
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: string]
  'update:use-ai-filtering': [value: boolean]
  'update:ai-filtering-priority': [value: string]
}>()

function truncateValue(value: string, maxLength = 50): string {
  if (!value) return 'Unknown'
  const str = String(value)
  if (str.length <= maxLength) return str
  return str.substring(0, maxLength) + '...'
}

function formatFactorName(factor: string): string {
  return factor.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
}
</script>
