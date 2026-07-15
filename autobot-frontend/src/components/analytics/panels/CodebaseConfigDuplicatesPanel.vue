<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Config Duplicates Detection (#538) -->
<template>
  <div class="config-duplicates-section analytics-section">
    <h3>
      <Icon name="clone" /> {{ $t('analytics.codebase.duplicates.configTitle') }}
      <span v-if="analysis" class="total-count">
        ({{ analysis.duplicates_found }} duplicates)
      </span>
      <button
        @click="emit('refresh')"
        :disabled="loading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
      </button>
      <div class="section-export-buttons">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
          :disabled="!analysis"
        >
          <Icon name="file-alt" /> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportJson')"
          :disabled="!analysis"
        >
          <Icon name="file-code" /> JSON
        </button>
      </div>
    </h3>

    <div v-if="loading" class="loading-state">
      <Icon name="spinner" :spin="true" />
      {{ $t('analytics.codebase.duplicates.scanningConfig') }}
    </div>

    <div v-else-if="error" class="error-state">
      <Icon name="exclamation-triangle" /> {{ error }}
      <button @click="emit('refresh')" class="btn-link">
        {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <div
      v-else-if="analysis && analysis.duplicates_found > 0"
      class="section-content"
    >
      <div class="summary-cards">
        <div class="summary-card warning">
          <div class="summary-value">{{ analysis.duplicates_found }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.duplicates.duplicateValues') }}</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ analysis.duplicates?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.duplicates.uniquePatterns') }}</div>
        </div>
      </div>

      <div class="duplicates-list">
        <div
          v-for="(dup, index) in analysis.duplicates?.slice(0, 20)"
          :key="'config-dup-' + index"
          class="list-item item-warning"
        >
          <div class="item-header">
            <span class="config-value-badge">{{ truncateValue(dup.value) }}</span>
            <span class="location-count">{{ dup.locations?.length || 0 }} locations</span>
          </div>
          <div class="item-locations">
            <div
              v-for="(loc, locIdx) in dup.locations?.slice(0, 5)"
              :key="'loc-' + locIdx"
              class="location-item"
            >
              📁 {{ loc.file }}:{{ loc.line }}
            </div>
            <div v-if="dup.locations?.length > 5" class="more-locations">
              ... and {{ dup.locations.length - 5 }} more locations
            </div>
          </div>
        </div>
        <div v-if="analysis.duplicates?.length > 20" class="show-more">
          <span class="muted">
            Showing 20 of {{ analysis.duplicates.length }} duplicate patterns
          </span>
        </div>
      </div>

      <div class="recommendation-box">
        <Icon name="lightbulb" />
        <span>{{ $t('analytics.codebase.duplicates.recommendation') }}</span>
      </div>
    </div>

    <div
      v-else-if="analysis && analysis.duplicates_found === 0"
      class="success-state"
    >
      <Icon name="check-circle" />
      {{ $t('analytics.codebase.duplicates.noDuplicatesFound') }}
    </div>

    <EmptyState
      v-else
      icon="clone"
      :message="$t('analytics.codebase.duplicates.noConfigData')"
    />
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'
import Icon from '@/components/ui/Icon.vue'

interface ConfigDuplicatesResult {
  duplicates_found: number
  duplicates: Array<{ value: string; locations: Array<{ file: string; line: number }> }>
  report: string
}

defineProps<{
  analysis: ConfigDuplicatesResult | null
  loading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: 'md' | 'json']
}>()

function truncateValue(value: string, maxLength = 50): string {
  if (!value) return 'Unknown'
  const str = String(value)
  if (str.length <= maxLength) return str
  return str.substring(0, maxLength) + '...'
}
</script>

<style scoped>
.config-duplicates-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  contain: layout style;}

.config-duplicates-section h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
  font-size: 1.2em;
  font-weight: 600;
}

.config-duplicates-section h3 i {
  color: var(--color-warning);
}

.config-duplicates-section .loading-state,
.config-duplicates-section .error-state,
.config-duplicates-section .success-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
}

.config-duplicates-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.config-duplicates-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.config-duplicates-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.config-duplicates-section .success-state i {
  color: var(--chart-green);
}

.config-duplicates-section .duplicates-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
}

.config-duplicates-section .item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2);
}

.config-duplicates-section .config-value-badge {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-default);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.85em;
}

.config-duplicates-section .location-count {
  color: var(--text-muted);
  font-size: 0.85em;
}

.config-duplicates-section .item-locations {
  padding-left: var(--spacing-3);
  border-left: 2px solid rgba(245, 158, 11, 0.3);
}

.config-duplicates-section .location-item {
  color: var(--text-muted);
  font-size: 0.85em;
  padding: var(--spacing-0-5) var(--spacing-0);
}

.config-duplicates-section .more-locations {
  color: var(--text-tertiary);
  font-size: 0.8em;
  font-style: italic;
  padding-top: var(--spacing-1);
}

.config-duplicates-section .recommendation-box {
  margin-top: var(--spacing-5);
  padding: var(--spacing-3) var(--spacing-4);
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: var(--radius-lg);
  color: var(--color-info-light);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.config-duplicates-section .recommendation-box i {
  color: var(--color-warning-light);
}

.config-duplicates-section .recommendation-box code {
  background: rgba(30, 41, 59, 0.8);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: 0.9em;
}

/* Issue #538: Bug Prediction Section */

</style>
