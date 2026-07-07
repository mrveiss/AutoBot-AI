<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Environment Analysis section (#538) -->
<template>
  <div class="environment-analysis-section analytics-section">
    <h3>
      <Icon name="leaf" /> {{ $t('analytics.codebase.environment.title') }}
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

    <!-- AI Filtering Toggle (#633) -->
    <div
      class="ai-filter-controls"
      style="margin-bottom: var(--spacing-4); padding: 10px; background: rgba(0,0,0,0.2);
             border-radius: 6px; display: flex; align-items: center; gap: var(--spacing-4); flex-wrap: wrap;"
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
          <Icon name="robot" /> {{ $t('analytics.codebase.environment.useAiFiltering') }}
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
        <Icon name="check-circle" />
        {{ llmFilteringResult.original_count }} → {{ llmFilteringResult.filtered_count }}
        ({{ llmFilteringResult.reduction_percent }}% reduced)
      </span>
    </div>

    <div v-if="loading" class="loading-state">
      <Icon name="spinner" :spin="true" />
      {{ useAiFiltering ? 'Scanning with AI filtering...' : 'Scanning for hardcoded values...' }}
    </div>

    <div v-else-if="error" class="error-state">
      <Icon name="exclamation-triangle" /> {{ error }}
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
            <Icon name="lightbulb" /> Use: <code>{{ hv.suggested_env_var }}</code>
          </div>
        </div>
      </div>

      <div class="scan-timestamp">
        <Icon name="clock" />
        Analysis completed in {{ analysis.analysis_time_seconds.toFixed(2) }}s
      </div>
    </div>

    <div
      v-else-if="analysis && analysis.total_hardcoded_values === 0"
      class="success-state"
    >
      <Icon name="check-circle" />
      {{ $t('analytics.codebase.environment.noHardcodedValues') }}
    </div>

    <EmptyState
      v-else
      icon="leaf"
      :message="$t('analytics.codebase.environment.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'
// #5311: canonical HardcodedValue from analyticsTypes — was inline-duplicated here.
import type { HardcodedValue } from '@/composables/analytics/analyticsTypes'
import Icon from '@/components/ui/Icon.vue'

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

defineProps<{
  analysis: EnvironmentAnalysisResult | null
  loading: boolean
  error: string | null
  useAiFiltering: boolean
  aiFilteringModel: string
  aiFilteringPriority: string
  llmFilteringResult: LLMFilteringResult | null
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: 'md' | 'json']
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

<style scoped>
.environment-analysis-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  contain: layout style;}

.environment-analysis-section h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
  font-size: 1.2em;
  font-weight: 600;
}

.environment-analysis-section h3 i {
  color: var(--chart-green);
}

.environment-analysis-section .loading-state,
.environment-analysis-section .error-state,
.environment-analysis-section .success-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
}

.environment-analysis-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.environment-analysis-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.environment-analysis-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.environment-analysis-section .success-state i {
  color: var(--chart-green);
}

/* Categories Breakdown */
.environment-analysis-section .categories-breakdown {
  margin-top: var(--spacing-5);
}

.environment-analysis-section .categories-breakdown h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: var(--spacing-3);
}

.environment-analysis-section .category-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.environment-analysis-section .category-badge {
  padding: var(--spacing-1) var(--spacing-2-5);
  background: rgba(71, 85, 105, 0.4);
  border-radius: var(--radius-default);
  font-size: 0.85em;
  color: var(--text-muted);
}

/* Recommendations List */
.environment-analysis-section .recommendations-list {
  margin-top: var(--spacing-5);
}

.environment-analysis-section .recommendations-list h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: var(--spacing-3);
}

.environment-analysis-section .recommendation-item {
  padding: var(--spacing-3-5);
  background: rgba(17, 24, 39, 0.5);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-2-5);
  border-left: 4px solid var(--text-tertiary);
}

.environment-analysis-section .recommendation-item.priority-high {
  border-left-color: var(--color-error);
}

.environment-analysis-section .recommendation-item.priority-medium {
  border-left-color: var(--color-warning);
}

.environment-analysis-section .recommendation-item.priority-low {
  border-left-color: var(--chart-green);
}

.environment-analysis-section .rec-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-2);
}

.environment-analysis-section .env-var-name {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.9em;
}

.environment-analysis-section .priority-badge {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: 0.7em;
  text-transform: uppercase;
  font-weight: 600;
}

.environment-analysis-section .priority-badge.high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.environment-analysis-section .priority-badge.medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.environment-analysis-section .priority-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.environment-analysis-section .rec-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  margin-bottom: var(--spacing-1-5);
}

.environment-analysis-section .rec-default {
  color: var(--text-muted);
  font-size: 0.85em;
}

.environment-analysis-section .rec-default code {
  background: rgba(30, 41, 59, 0.8);
  padding: 1px 5px;
  border-radius: var(--radius-default);
}

/* Hardcoded Values Preview */
.environment-analysis-section .hardcoded-preview {
  margin-top: var(--spacing-5);
}

.environment-analysis-section .hardcoded-preview h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: var(--spacing-3);
}

/* Issue #631: Truncation warning style */
.environment-analysis-section .truncation-warning {
  font-size: 0.85em;
  color: var(--color-warning);
  font-weight: normal;
  margin-left: var(--spacing-2);
}

.environment-analysis-section .hardcoded-item {
  padding: var(--spacing-3);
  background: rgba(17, 24, 39, 0.5);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-2);
  border-left: 3px solid var(--text-tertiary);
}

.environment-analysis-section .hardcoded-item.severity-high {
  border-left-color: var(--color-error);
}

.environment-analysis-section .hardcoded-item.severity-medium {
  border-left-color: var(--color-warning);
}

.environment-analysis-section .hardcoded-item.severity-low {
  border-left-color: var(--chart-green);
}

.environment-analysis-section .hv-location {
  margin-bottom: var(--spacing-1-5);
}

.environment-analysis-section .file-path {
  color: var(--color-info-light);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.85em;
}

.environment-analysis-section .line-number {
  color: var(--text-tertiary);
  font-size: 0.85em;
}

.environment-analysis-section .hv-value {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1-5);
}

.environment-analysis-section .hv-value code {
  background: rgba(245, 158, 11, 0.1);
  color: var(--color-warning-light);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: 0.85em;
}

.environment-analysis-section .value-type {
  color: var(--text-tertiary);
  font-size: 0.75em;
  text-transform: uppercase;
}

.environment-analysis-section .hv-suggestion {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-2-5);
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-default);
  font-size: 0.85em;
}

.environment-analysis-section .hv-suggestion i {
  color: var(--color-warning-light);
}

.environment-analysis-section .hv-suggestion code {
  color: var(--color-success-light);
  background: transparent;
}

/* Issue #248: Code Ownership and Expertise Map Section */

</style>
