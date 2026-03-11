<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Config Duplicates Detection (#538) -->
<template>
  <div class="config-duplicates-section analytics-section">
    <h3>
      <i class="fas fa-clone"></i> {{ $t('analytics.codebase.duplicates.configTitle') }}
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
          <i class="fas fa-file-alt"></i> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :title="$t('analytics.codebase.actions.exportJson')"
          :disabled="!analysis"
        >
          <i class="fas fa-file-code"></i> JSON
        </button>
      </div>
    </h3>

    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      {{ $t('analytics.codebase.duplicates.scanningConfig') }}
    </div>

    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i> {{ error }}
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
        <i class="fas fa-lightbulb"></i>
        <span>{{ $t('analytics.codebase.duplicates.recommendation') }}</span>
      </div>
    </div>

    <div
      v-else-if="analysis && analysis.duplicates_found === 0"
      class="success-state"
    >
      <i class="fas fa-check-circle"></i>
      {{ $t('analytics.codebase.duplicates.noDuplicatesFound') }}
    </div>

    <EmptyState
      v-else
      icon="fas fa-clone"
      :message="$t('analytics.codebase.duplicates.noConfigData')"
    />
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'

interface ConfigDuplicatesResult {
  duplicates_found: number
  duplicates: Array<{ value: string; locations: Array<{ file: string; line: number }> }>
  report: string
}

const props = defineProps<{
  analysis: ConfigDuplicatesResult | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: string]
}>()

function truncateValue(value: string, maxLength = 50): string {
  if (!value) return 'Unknown'
  const str = String(value)
  if (str.length <= maxLength) return str
  return str.substring(0, maxLength) + '...'
}
</script>
