<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Cross-Language Pattern Analysis (#244) -->
<template>
  <div class="cross-language-section analytics-section">
    <h3>
      <i class="fas fa-language"></i> {{ $t('analytics.codebase.crossLanguage.title') }}
      <span v-if="analysis" class="total-count">({{ analysis.total_patterns }} patterns)</span>
      <button
        @click="emit('refresh')"
        :disabled="loading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
      </button>
      <button
        @click="emit('run-full-scan')"
        :disabled="loading"
        class="btn-scan"
        style="margin-left: 5px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
        {{ loading ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.crossLanguage.fullScan') }}
      </button>
      <div class="section-export-buttons">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :disabled="!analysis"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
        >
          <i class="fas fa-file-alt"></i> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :disabled="!analysis"
          :title="$t('analytics.codebase.actions.exportJson')"
        >
          <i class="fas fa-file-code"></i> JSON
        </button>
      </div>
    </h3>

    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      {{ $t('analytics.codebase.crossLanguage.analyzing') }}
    </div>

    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i> {{ error }}
      <button @click="emit('refresh')" class="btn-link">
        {{ $t('analytics.codebase.actions.retry') }}
      </button>
    </div>

    <div v-else-if="analysis" class="section-content">
      <div class="summary-cards">
        <div class="summary-card total">
          <div class="summary-value">
            {{ analysis.python_files_analyzed + analysis.typescript_files_analyzed + analysis.vue_files_analyzed }}
          </div>
          <div class="summary-label">{{ $t('analytics.codebase.crossLanguage.filesAnalyzed') }}</div>
        </div>
        <div class="summary-card critical">
          <div class="summary-value">{{ analysis.critical_issues }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.severity.critical') }}</div>
        </div>
        <div class="summary-card warning">
          <div class="summary-value">{{ analysis.high_issues }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.severity.high') }}</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ analysis.dto_mismatches?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.crossLanguage.dtoMismatches') }}</div>
        </div>
        <div class="summary-card success">
          <div class="summary-value">{{ analysis.pattern_matches?.length || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.crossLanguage.semanticMatches') }}</div>
        </div>
      </div>

      <div class="language-breakdown">
        <span class="language-badge python">
          <i class="fab fa-python"></i> {{ analysis.python_files_analyzed }} Python
        </span>
        <span class="language-badge typescript">
          <i class="fab fa-js-square"></i> {{ analysis.typescript_files_analyzed }} TypeScript
        </span>
        <span class="language-badge vue">
          <i class="fab fa-vuejs"></i> {{ analysis.vue_files_analyzed }} Vue
        </span>
      </div>

      <div class="accordion-groups">
        <!-- DTO Mismatches -->
        <div v-if="analysis.dto_mismatches?.length > 0" class="accordion-group">
          <div
            class="accordion-header critical"
            @click="expanded.dtoMismatches = !expanded.dtoMismatches"
          >
            <div class="header-info">
              <i :class="expanded.dtoMismatches ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">
                {{ $t('analytics.codebase.crossLanguage.dtoTypeMismatches') }}
              </span>
              <span class="header-count">({{ analysis.dto_mismatches.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge critical">
                {{ $t('analytics.codebase.crossLanguage.typeSafety') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.dtoMismatches" class="accordion-items">
              <div
                v-for="(m, index) in analysis.dto_mismatches.slice(0, 20)"
                :key="'dto-' + index"
                class="list-item item-critical"
              >
                <div class="item-header">
                  <span class="type-badge">{{ m.mismatch_type }}</span>
                  <span class="item-name">{{ m.backend_type }} → {{ m.frontend_type || 'Unknown' }}</span>
                </div>
                <div class="item-field">Field: <code>{{ m.field_name }}</code></div>
                <div v-if="m.recommendation" class="item-recommendation">
                  💡 {{ m.recommendation }}
                </div>
              </div>
              <div v-if="analysis.dto_mismatches.length > 20" class="show-more">
                <span class="muted">
                  Showing 20 of {{ analysis.dto_mismatches.length }} DTO mismatches
                </span>
              </div>
            </div>
          </transition>
        </div>

        <!-- API Contract Mismatches -->
        <div v-if="analysis.api_contract_mismatches?.length > 0" class="accordion-group">
          <div
            class="accordion-header warning"
            @click="expanded.apiMismatches = !expanded.apiMismatches"
          >
            <div class="header-info">
              <i :class="expanded.apiMismatches ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">
                {{ $t('analytics.codebase.crossLanguage.apiContractIssues') }}
              </span>
              <span class="header-count">({{ analysis.api_contract_mismatches.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge warning">
                {{ $t('analytics.codebase.crossLanguage.contract') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.apiMismatches" class="accordion-items">
              <div
                v-for="(m, index) in analysis.api_contract_mismatches.slice(0, 20)"
                :key="'api-' + index"
                :class="[
                  'list-item',
                  m.mismatch_type === 'missing_endpoint' ? 'item-critical' : 'item-warning',
                ]"
              >
                <div class="item-header">
                  <span class="method-badge" :class="m.http_method?.toLowerCase()">
                    {{ m.http_method }}
                  </span>
                  <span class="item-path">{{ m.endpoint_path }}</span>
                  <span
                    :class="[
                      'type-badge',
                      m.mismatch_type === 'missing_endpoint' ? 'missing' : 'orphaned',
                    ]"
                  >
                    {{ m.mismatch_type === 'missing_endpoint' ? 'Missing' : 'Orphaned' }}
                  </span>
                </div>
                <div v-if="m.details" class="item-details">{{ m.details }}</div>
              </div>
              <div v-if="analysis.api_contract_mismatches.length > 20" class="show-more">
                <span class="muted">
                  Showing 20 of {{ analysis.api_contract_mismatches.length }} API issues
                </span>
              </div>
            </div>
          </transition>
        </div>

        <!-- Validation Duplications -->
        <div v-if="analysis.validation_duplications?.length > 0" class="accordion-group">
          <div
            class="accordion-header info"
            @click="expanded.validationDups = !expanded.validationDups"
          >
            <div class="header-info">
              <i :class="expanded.validationDups ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">
                {{ $t('analytics.codebase.crossLanguage.validationDuplications') }}
              </span>
              <span class="header-count">({{ analysis.validation_duplications.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge info">
                {{ $t('analytics.codebase.crossLanguage.dryViolation') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.validationDups" class="accordion-items">
              <div
                v-for="(v, index) in analysis.validation_duplications.slice(0, 15)"
                :key="'val-' + index"
                class="list-item item-info"
              >
                <div class="item-header">
                  <span class="validation-type-badge">{{ v.validation_type }}</span>
                  <span class="similarity-score">
                    {{ (v.similarity_score * 100).toFixed(0) }}% similar
                  </span>
                </div>
                <div class="item-locations">
                  <span v-if="v.python_location" class="location python">
                    🐍 {{ v.python_location.file_path }}:{{ v.python_location.line_start }}
                  </span>
                  <span v-if="v.typescript_location" class="location typescript">
                    📜 {{ v.typescript_location.file_path }}:{{ v.typescript_location.line_start }}
                  </span>
                </div>
                <div v-if="v.recommendation" class="item-recommendation">
                  💡 {{ v.recommendation }}
                </div>
              </div>
              <div v-if="analysis.validation_duplications.length > 15" class="show-more">
                <span class="muted">
                  Showing 15 of {{ analysis.validation_duplications.length }} duplications
                </span>
              </div>
            </div>
          </transition>
        </div>

        <!-- Semantic Pattern Matches -->
        <div v-if="analysis.pattern_matches?.length > 0" class="accordion-group">
          <div
            class="accordion-header success"
            @click="expanded.semanticMatches = !expanded.semanticMatches"
          >
            <div class="header-info">
              <i
                :class="expanded.semanticMatches ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"
              ></i>
              <span class="header-name">
                {{ $t('analytics.codebase.crossLanguage.semanticPatternMatches') }}
              </span>
              <span class="header-count">({{ analysis.pattern_matches.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge success">
                {{ $t('analytics.codebase.crossLanguage.aiDetected') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.semanticMatches" class="accordion-items">
              <div
                v-for="(m, index) in analysis.pattern_matches.slice(0, 15)"
                :key="'match-' + index"
                class="list-item item-success"
              >
                <div class="item-header">
                  <span class="similarity-score highlight">
                    {{ (m.similarity_score * 100).toFixed(0) }}% match
                  </span>
                  <span class="match-type">{{ m.match_type }}</span>
                </div>
                <div class="item-locations">
                  <span v-if="m.source_location" class="location">
                    📁 {{ m.source_location.file_path }}:{{ m.source_location.line_start }}
                  </span>
                  <span class="arrow">↔</span>
                  <span v-if="m.target_location" class="location">
                    📁 {{ m.target_location.file_path }}:{{ m.target_location.line_start }}
                  </span>
                </div>
              </div>
              <div v-if="analysis.pattern_matches.length > 15" class="show-more">
                <span class="muted">
                  Showing 15 of {{ analysis.pattern_matches.length }} matches
                </span>
              </div>
            </div>
          </transition>
        </div>
      </div>

      <div v-if="analysis.scan_timestamp" class="scan-timestamp">
        <i class="fas fa-clock"></i> {{ $t('analytics.codebase.actions.lastScan') }}:
        {{ formatTimestamp(analysis.scan_timestamp) }}
        <span v-if="analysis.analysis_time_ms" class="analysis-time">
          ({{ (analysis.analysis_time_ms / 1000).toFixed(1) }}s)
        </span>
      </div>
    </div>

    <EmptyState
      v-else
      icon="fas fa-language"
      :message="$t('analytics.codebase.crossLanguage.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface PatternLocation {
  file_path: string
  line_start: number
  line_end: number
  language: string
}

interface DTOMismatch {
  mismatch_id: string
  backend_type: string
  frontend_type: string
  field_name: string
  mismatch_type: string
  severity: string
  recommendation: string
}

interface ValidationDuplication {
  duplication_id: string
  validation_type: string
  similarity_score: number
  severity: string
  recommendation: string
  python_location?: PatternLocation
  typescript_location?: PatternLocation
}

interface APIContractMismatch {
  mismatch_id: string
  endpoint_path: string
  http_method: string
  mismatch_type: string
  severity: string
  details: string
}

interface PatternMatch {
  pattern_id: string
  similarity_score: number
  match_type: string
  source_location?: PatternLocation
  target_location?: PatternLocation
}

interface CrossLanguageAnalysisResult {
  analysis_id: string
  scan_timestamp: string
  python_files_analyzed: number
  typescript_files_analyzed: number
  vue_files_analyzed: number
  total_patterns: number
  critical_issues: number
  high_issues: number
  dto_mismatches: DTOMismatch[]
  validation_duplications: ValidationDuplication[]
  api_contract_mismatches: APIContractMismatch[]
  pattern_matches: PatternMatch[]
  analysis_time_ms: number
}

const props = defineProps<{
  analysis: CrossLanguageAnalysisResult | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
  'run-full-scan': []
  export: [format: string]
}>()

const expanded = reactive({
  dtoMismatches: false,
  apiMismatches: false,
  validationDups: false,
  semanticMatches: false,
})

function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) return 'Unknown'
  try {
    return new Date(timestamp).toLocaleString()
  } catch {
    return String(timestamp)
  }
}
</script>
