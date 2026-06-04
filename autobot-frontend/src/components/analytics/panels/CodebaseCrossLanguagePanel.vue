<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Cross-Language Pattern Analysis (#244) -->
<template>
  <div class="cross-language-section analytics-section">
    <h3>
      <Icon name="language" /> {{ $t('analytics.codebase.crossLanguage.title') }}
      <span v-if="analysis" class="total-count">({{ analysis.total_patterns }} patterns)</span>
      <button
        @click="emit('refresh')"
        :disabled="loading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
      </button>
      <button
        @click="emit('run-full-scan')"
        :disabled="loading"
        class="btn-scan"
        style="margin-left: 5px;"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'search'"></i>
        {{ loading ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.crossLanguage.fullScan') }}
      </button>
      <div class="section-export-buttons">
        <button
          @click="emit('export', 'md')"
          class="export-btn"
          :disabled="!analysis"
          :title="$t('analytics.codebase.actions.exportMarkdown')"
        >
          <Icon name="file-alt" /> MD
        </button>
        <button
          @click="emit('export', 'json')"
          class="export-btn"
          :disabled="!analysis"
          :title="$t('analytics.codebase.actions.exportJson')"
        >
          <Icon name="file-code" /> JSON
        </button>
      </div>
    </h3>

    <div v-if="loading" class="loading-state">
      <Icon name="spinner" class="animate-spin" />
      {{ $t('analytics.codebase.crossLanguage.analyzing') }}
    </div>

    <div v-else-if="error" class="error-state">
      <Icon name="exclamation-triangle" /> {{ error }}
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
          <Icon name="code" /> {{ analysis.python_files_analyzed }} Python
        </span>
        <span class="language-badge typescript">
          <Icon name="code" /> {{ analysis.typescript_files_analyzed }} TypeScript
        </span>
        <span class="language-badge vue">
          <Icon name="code" /> {{ analysis.vue_files_analyzed }} Vue
        </span>
      </div>

      <div class="accordion-groups">
        <!-- DTO Mismatches -->
        <div v-if="analysis.dto_mismatches?.length > 0" class="accordion-group">
          <div
            class="accordion-header critical"
            @click="toggle('dtoMismatches')"
          >
            <div class="header-info">
              <Icon :name="isExpanded('dtoMismatches') ? 'chevron-down' : 'chevron-right'" />
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
            <div v-if="isExpanded('dtoMismatches')" class="accordion-items">
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
            @click="toggle('apiMismatches')"
          >
            <div class="header-info">
              <Icon :name="isExpanded('apiMismatches') ? 'chevron-down' : 'chevron-right'" />
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
            <div v-if="isExpanded('apiMismatches')" class="accordion-items">
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
            @click="toggle('validationDups')"
          >
            <div class="header-info">
              <Icon :name="isExpanded('validationDups') ? 'chevron-down' : 'chevron-right'" />
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
            <div v-if="isExpanded('validationDups')" class="accordion-items">
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
            @click="toggle('semanticMatches')"
          >
            <div class="header-info">
              <Icon :name="isExpanded('semanticMatches') ? 'chevron-down' : 'chevron-right'" />
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
            <div v-if="isExpanded('semanticMatches')" class="accordion-items">
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
        <Icon name="clock" /> {{ $t('analytics.codebase.actions.lastScan') }}:
        {{ formatTimestamp(analysis.scan_timestamp) }}
        <span v-if="analysis.analysis_time_ms" class="analysis-time">
          ({{ (analysis.analysis_time_ms / 1000).toFixed(1) }}s)
        </span>
      </div>
    </div>

    <EmptyState
      v-else
      icon="language"
      :message="$t('analytics.codebase.crossLanguage.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useExpansion } from '@/composables/useExpansion'

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
  error: string | null
}>()

const emit = defineEmits<{
  refresh: []
  'run-full-scan': []
  export: [format: 'md' | 'json']
}>()

type Section = 'dtoMismatches' | 'apiMismatches' | 'validationDups' | 'semanticMatches'
const { isExpanded, toggle } = useExpansion<Section>()

function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) return 'Unknown'
  try {
    return new Date(timestamp).toLocaleString()
  } catch {
    return String(timestamp)
  }
}
</script>

<style scoped>
.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.accordion-group {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--bg-tertiary);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3-5) var(--spacing-4);
  cursor: pointer;
  background: var(--bg-secondary);
  transition: background var(--duration-200) var(--ease-out);
}

.accordion-header:hover {
  background: var(--bg-tertiary);
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-info i {
  color: var(--text-muted);
  font-size: 0.75em;
  transition: transform var(--duration-200) var(--ease-out);
}

.header-name {
  font-weight: 600;
  color: var(--text-secondary);
}

.header-count {
  color: var(--text-muted);
  font-size: 0.9em;
}

.header-badges {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

/* Unified Severity Badges */
.severity-badge {
  font-size: 0.7em;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xl);
  font-weight: 500;
}

.severity-badge.critical { background: var(--color-error-bg); color: var(--color-error-light); }
.severity-badge.high { background: var(--color-warning-bg); color: var(--chart-orange-light); }
.severity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.severity-badge.low { background: var(--color-success-bg); color: var(--color-success-light); }



/* Accordion Items Container */
.accordion-items {
  padding: var(--spacing-3);
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2-5);
}

/* Accordion Transition */
.accordion-enter-active,
.accordion-leave-active {
  transition: all var(--duration-300) var(--ease-out);
  overflow: hidden;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}

.accordion-enter-to,
.accordion-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* Unified List Items */
.list-item {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5) var(--spacing-4);
  border-left: 4px solid var(--text-tertiary);
  transition: all var(--duration-200) var(--ease-out);
}

.list-item:hover {
  transform: translateX(4px);
  background: var(--bg-secondary);
}

/* List Item Severity Variants */
.list-item.item-critical { border-left-color: var(--color-error); }
.list-item.item-high { border-left-color: var(--chart-orange); }
.list-item.item-medium { border-left-color: var(--color-warning); }
.list-item.item-low { border-left-color: var(--chart-green); }
.list-item.item-info { border-left-color: var(--chart-blue); }

/* Show More / Muted Utilities */
.show-more {
  text-align: center;
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-top: var(--spacing-2);
}

.muted {
  color: var(--text-tertiary);
  font-style: italic;
}

/* Item Header */
.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.item-name {
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

.item-severity {
  font-size: 0.75em;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-weight: 600;
  text-transform: uppercase;
}

.item-severity.critical { background: var(--color-error-bg); color: var(--color-error-light); }
.item-severity.high { background: var(--color-warning-bg); color: var(--chart-orange-light); }
.item-severity.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.item-severity.low { background: var(--color-success-bg); color: var(--color-success-light); }
.item-severity.info { background: var(--color-info-dark); color: var(--color-info-light); }

/* Item Content */
.item-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  margin-bottom: var(--spacing-2);
}

.item-location {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
  margin-bottom: var(--spacing-1);
}

.item-suggestion {
  color: var(--chart-green);
  font-size: 0.85em;
  padding: var(--spacing-2);
  background: rgba(34, 197, 94, 0.1);
  border-radius: var(--radius-default);
  margin-top: var(--spacing-2);
}

/* Duplicate-specific Styles */
.item-similarity {
  font-size: 0.75em;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-weight: 600;
}

.item-similarity.high { background: var(--color-error-bg); color: var(--color-error-light); }
.item-similarity.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.item-similarity.low { background: var(--color-success-bg); color: var(--color-success-light); }

.item-lines {
  color: var(--text-muted);
  font-size: 0.8em;
}

.item-files {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.item-file {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

/* Responsive Design */
@media (max-width: 768px) {
  .codebase-analytics {
    padding: var(--spacing-3);
  }

  .header-controls {
    flex-direction: column;
    align-items: stretch;
  }

  .path-input {
    min-width: unset;
    width: 100%;
  }

  .debug-controls {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .btn-debug {
    width: 100%;
    justify-content: center;
  }

  .enhanced-analytics-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .real-time-controls {
    flex-direction: column;
    gap: var(--spacing-3);
    align-items: stretch;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .problem-header, .duplicate-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-1);
  }
}

/* Charts Section Styles */

.cross-language-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  contain: layout style;}

.cross-language-section h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-5) var(--spacing-0);
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
}

.cross-language-section h3 i {
  color: var(--chart-purple);
}

.cross-language-section .loading-state,
.cross-language-section .error-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
}

.cross-language-section .loading-state {
  background: rgba(139, 92, 246, 0.1);
  border: 1px solid rgba(139, 92, 246, 0.3);
  color: var(--chart-purple-light);
}

.cross-language-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

/* Language Breakdown */
.language-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  margin: var(--spacing-4) var(--spacing-0);
  padding: var(--spacing-3);
  background: rgba(30, 41, 59, 0.8);
  border-radius: var(--radius-lg);
}

.language-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: 0.85rem;
  font-weight: 500;
}

.language-badge.python {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.language-badge.typescript {
  background: rgba(49, 120, 198, 0.2);
  color: var(--chart-blue-light);
  border: 1px solid rgba(49, 120, 198, 0.3);
}

.language-badge.vue {
  background: rgba(66, 184, 131, 0.2);
  color: var(--chart-green);
  border: 1px solid rgba(66, 184, 131, 0.3);
}

/* Cross-language Type Badges */
.type-badge {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: 500;
  text-transform: uppercase;
  margin-right: var(--spacing-2);
  background: rgba(139, 92, 246, 0.2);
  color: var(--chart-purple-light);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

.type-badge.missing {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.type-badge.orphaned {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

/* Validation Type Badge */
.validation-type-badge {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: 500;
  margin-right: var(--spacing-2);
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

/* Similarity Score */
.similarity-score {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: 600;
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.similarity-score.highlight {
  background: rgba(139, 92, 246, 0.2);
  color: var(--chart-purple-light);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

/* Match Type */
.match-type {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  margin-left: var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: 500;
  background: rgba(100, 116, 139, 0.2);
  color: var(--text-muted);
  border: 1px solid rgba(100, 116, 139, 0.3);
}

/* Item Locations for cross-language */
.item-locations {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  margin-top: var(--spacing-1-5);
  align-items: center;
}

.item-locations .location {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.item-locations .location.python {
  color: var(--color-info);
}

.item-locations .location.typescript {
  color: var(--chart-blue-light);
}

.item-locations .arrow {
  color: var(--text-tertiary);
  font-weight: bold;
}

/* Item Field */
.item-field {
  margin-top: var(--spacing-1);
  font-size: 0.85rem;
  color: var(--text-muted);
}

.item-field code {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  background: rgba(0, 0, 0, 0.3);
  border-radius: var(--radius-default);
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

/* Item Name */
.item-name {
  color: var(--text-secondary);
  font-weight: 500;
}

/* Item Recommendation */
.item-recommendation {
  margin-top: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-3);
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-md);
  color: var(--color-info-light);
  font-size: 0.8rem;
  border-left: 2px solid var(--chart-blue);
}

/* Analysis Time */
.analysis-time {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  margin-left: var(--spacing-1);
}

/* Scan Button */
.btn-scan {
  padding: var(--spacing-1) var(--spacing-2-5);
  background: var(--chart-purple);
  color: white;
  border: none;
  border-radius: var(--radius-default);
  font-size: 0.8rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  transition: background var(--duration-200);
}

.btn-scan:hover:not(:disabled) {
  background: var(--chart-purple-dark);
}

.btn-scan:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Issue #538: Config Duplicates Section */

</style>
