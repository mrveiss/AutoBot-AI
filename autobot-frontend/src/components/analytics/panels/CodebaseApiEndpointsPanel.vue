<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — API Endpoint Coverage section (#527) -->
<template>
  <div class="api-endpoints-section analytics-section">
    <h3>
      <i class="fas fa-plug"></i> {{ $t('analytics.codebase.apiCoverage.title') }}
      <span v-if="analysis" class="total-count">
        ({{ analysis.coverage_percentage?.toFixed(1) || 0 }}% coverage)
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
      <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.apiCoverage.scanning') }}
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
          <div class="summary-value">{{ analysis.backend_endpoints || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.backendEndpoints') }}</div>
        </div>
        <div class="summary-card info">
          <div class="summary-value">{{ analysis.frontend_calls || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.frontendCalls') }}</div>
        </div>
        <div class="summary-card success">
          <div class="summary-value">{{ analysis.used_endpoints || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.usedEndpoints') }}</div>
        </div>
        <div class="summary-card warning">
          <div class="summary-value">{{ analysis.orphaned_endpoints || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.orphaned') }}</div>
        </div>
        <div class="summary-card critical">
          <div class="summary-value">{{ analysis.missing_endpoints || 0 }}</div>
          <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.missing') }}</div>
        </div>
      </div>

      <div class="coverage-bar-container">
        <div class="coverage-label">
          <span>{{ $t('analytics.codebase.apiCoverage.coverageLabel') }}</span>
          <span
            class="coverage-value"
            :class="getCoverageClass(analysis.coverage_percentage)"
          >
            {{ analysis.coverage_percentage?.toFixed(1) || 0 }}%
          </span>
        </div>
        <div class="coverage-bar">
          <div
            class="coverage-fill"
            :style="{ width: (analysis.coverage_percentage || 0) + '%' }"
            :class="getCoverageClass(analysis.coverage_percentage)"
          ></div>
        </div>
      </div>

      <div class="accordion-groups">
        <!-- Orphaned Endpoints -->
        <div v-if="analysis.orphaned?.length > 0" class="accordion-group">
          <div
            class="accordion-header warning"
            @click="expanded.orphaned = !expanded.orphaned"
          >
            <div class="header-info">
              <i :class="expanded.orphaned ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">
                {{ $t('analytics.codebase.apiCoverage.orphanedEndpoints') }}
              </span>
              <span class="header-count">({{ analysis.orphaned.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge warning">
                {{ $t('analytics.codebase.apiCoverage.unusedCode') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.orphaned" class="accordion-items">
              <div
                v-for="(ep, index) in analysis.orphaned.slice(0, 30)"
                :key="'orphan-' + index"
                class="list-item item-warning"
              >
                <div class="item-header">
                  <span class="method-badge" :class="ep.method?.toLowerCase()">{{ ep.method }}</span>
                  <span class="item-path">{{ ep.path }}</span>
                </div>
                <div class="item-location">📁 {{ ep.file_path }}:{{ ep.line_number }}</div>
              </div>
              <div v-if="analysis.orphaned.length > 30" class="show-more">
                <span class="muted">
                  Showing 30 of {{ analysis.orphaned.length }} orphaned endpoints
                </span>
              </div>
            </div>
          </transition>
        </div>

        <!-- Missing Endpoints -->
        <div v-if="analysis.missing?.length > 0" class="accordion-group">
          <div
            class="accordion-header critical"
            @click="expanded.missing = !expanded.missing"
          >
            <div class="header-info">
              <i :class="expanded.missing ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">
                {{ $t('analytics.codebase.apiCoverage.missingEndpoints') }}
              </span>
              <span class="header-count">({{ analysis.missing.length }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge critical">
                {{ $t('analytics.codebase.apiCoverage.potentialBugs') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.missing" class="accordion-items">
              <div
                v-for="(ep, index) in analysis.missing.slice(0, 30)"
                :key="'missing-' + index"
                class="list-item item-critical"
              >
                <div class="item-header">
                  <span class="method-badge" :class="ep.method?.toLowerCase()">{{ ep.method }}</span>
                  <span class="item-path">{{ ep.path }}</span>
                </div>
                <div class="item-location">📁 {{ ep.file_path }}:{{ ep.line_number }}</div>
                <div v-if="ep.details" class="item-details">{{ ep.details }}</div>
              </div>
              <div v-if="analysis.missing.length > 30" class="show-more">
                <span class="muted">
                  Showing 30 of {{ analysis.missing.length }} missing endpoints
                </span>
              </div>
            </div>
          </transition>
        </div>

        <!-- Used Endpoints -->
        <div v-if="(analysis.used?.length ?? 0) > 0" class="accordion-group">
          <div
            class="accordion-header success"
            @click="expanded.used = !expanded.used"
          >
            <div class="header-info">
              <i :class="expanded.used ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
              <span class="header-name">
                {{ $t('analytics.codebase.apiCoverage.usedEndpointsHeader') }}
              </span>
              <span class="header-count">({{ analysis.used?.length ?? 0 }})</span>
            </div>
            <div class="header-badges">
              <span class="severity-badge success">
                {{ $t('analytics.codebase.apiCoverage.active') }}
              </span>
            </div>
          </div>
          <transition name="accordion">
            <div v-if="expanded.used" class="accordion-items">
              <div
                v-for="(usage, index) in analysis.used?.slice(0, 30)"
                :key="'used-' + index"
                class="list-item item-success"
              >
                <div class="item-header">
                  <span
                    class="method-badge"
                    :class="usage.endpoint?.method?.toLowerCase()"
                  >{{ usage.endpoint?.method }}</span>
                  <span class="item-path">{{ usage.endpoint?.path }}</span>
                  <span class="call-count-badge">{{ usage.call_count }} calls</span>
                </div>
                <div class="item-location">
                  📁 {{ usage.endpoint?.file_path }}:{{ usage.endpoint?.line_number }}
                </div>
              </div>
              <div v-if="(analysis.used?.length ?? 0) > 30" class="show-more">
                <span class="muted">
                  Showing 30 of {{ analysis.used?.length ?? 0 }} used endpoints
                </span>
              </div>
            </div>
          </transition>
        </div>
      </div>

      <div v-if="analysis.scan_timestamp" class="scan-timestamp">
        <i class="fas fa-clock"></i> {{ $t('analytics.codebase.actions.lastScan') }}:
        {{ formatTimestamp(analysis.scan_timestamp) }}
      </div>
    </div>

    <EmptyState
      v-else
      icon="fas fa-plug"
      :message="$t('analytics.codebase.apiCoverage.noData')"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface ApiEndpointInfo {
  path: string
  method?: string
  function_name?: string
  file_path?: string
  line_number?: number
  details?: string
  [key: string]: unknown
}

interface ApiUsageInfo {
  endpoint?: ApiEndpointInfo
  call_count?: number
  [key: string]: unknown
}

interface ApiEndpointAnalysisResult {
  coverage_percentage: number
  backend_endpoints: number
  frontend_calls: number
  used_endpoints: number
  orphaned_endpoints: number
  missing_endpoints: number
  orphaned: ApiEndpointInfo[]
  missing: ApiEndpointInfo[]
  used?: ApiUsageInfo[]
  scan_timestamp?: string | number | Date
  [key: string]: unknown
}

const props = defineProps<{
  analysis: ApiEndpointAnalysisResult | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
  export: [format: string]
}>()

const expanded = reactive({ orphaned: false, missing: false, used: false })

function getCoverageClass(percentage: number): string {
  if (!percentage || percentage < 50) return 'critical'
  if (percentage < 75) return 'warning'
  if (percentage < 90) return 'info'
  return 'success'
}

function formatTimestamp(timestamp: string | number | Date | undefined): string {
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
  gap: 8px;
}

.accordion-group {
  background: var(--bg-card);
  border-radius: 8px;
  border: 1px solid var(--bg-tertiary);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  cursor: pointer;
  background: var(--bg-secondary);
  transition: background 0.2s ease;
}

.accordion-header:hover {
  background: var(--bg-tertiary);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-info i {
  color: var(--text-muted);
  font-size: 0.75em;
  transition: transform 0.2s ease;
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
  gap: 8px;
  flex-wrap: wrap;
}

/* Unified Severity Badges */
.severity-badge {
  font-size: 0.7em;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.severity-badge.critical { background: var(--color-error-bg); color: var(--color-error-light); }
.severity-badge.high { background: var(--color-warning-bg); color: var(--chart-orange-light); }
.severity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.severity-badge.low { background: var(--color-success-bg); color: var(--color-success-light); }



/* Accordion Items Container */
.accordion-items {
  padding: 12px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Accordion Transition */
.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease;
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
  border-radius: 8px;
  padding: 14px 16px;
  border-left: 4px solid var(--text-tertiary);
  transition: all 0.2s ease;
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
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  margin-top: 8px;
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
  margin-bottom: 8px;
}

.item-name {
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

.item-severity {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 4px;
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
  margin-bottom: 8px;
}

.item-location {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
  margin-bottom: 4px;
}

.item-suggestion {
  color: var(--chart-green);
  font-size: 0.85em;
  padding: 8px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 4px;
  margin-top: 8px;
}

/* Duplicate-specific Styles */
.item-similarity {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 4px;
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
  gap: 4px;
}

.item-file {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

/* Responsive Design */
@media (max-width: 768px) {
  .codebase-analytics {
    padding: 12px;
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
    gap: 8px;
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
    gap: 12px;
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
    gap: 4px;
  }
}

/* Charts Section Styles */

.api-endpoints-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.api-endpoints-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 20px 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
}

.api-endpoints-section h3 i {
  color: var(--chart-blue);
}

.api-endpoints-section .loading-state,
.api-endpoints-section .error-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.api-endpoints-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.api-endpoints-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

/* Coverage Bar */
.coverage-bar-container {
  margin: 20px 0;
  padding: 16px;
  background: rgba(30, 41, 59, 0.8);
  border-radius: 8px;
}

.coverage-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.coverage-value {
  font-weight: 600;
  font-size: 1rem;
}

.coverage-value.success { color: var(--chart-green); }
.coverage-value.info { color: var(--chart-blue); }
.coverage-value.warning { color: var(--color-warning); }
.coverage-value.critical { color: var(--color-error); }

.coverage-bar {
  height: 12px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  overflow: hidden;
}

.coverage-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.3s ease;
}

.coverage-fill.success { background: var(--color-success); }
.coverage-fill.info { background: var(--color-primary); }
.coverage-fill.warning { background: var(--color-warning); }
.coverage-fill.critical { background: var(--color-error); }

/* HTTP Method Badges */
.method-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  margin-right: 8px;
}

.method-badge.get { background: var(--chart-green)20; color: var(--chart-green); border: 1px solid var(--chart-green)40; }
.method-badge.post { background: var(--chart-blue)20; color: var(--chart-blue); border: 1px solid var(--chart-blue)40; }
.method-badge.put { background: var(--color-warning)20; color: var(--color-warning); border: 1px solid var(--color-warning)40; }
.method-badge.patch { background: var(--chart-purple)20; color: var(--chart-purple); border: 1px solid var(--chart-purple)40; }
.method-badge.delete { background: var(--color-error)20; color: var(--color-error); border: 1px solid var(--color-error)40; }
.method-badge.unknown { background: var(--text-tertiary)20; color: var(--text-tertiary); border: 1px solid var(--text-tertiary)40; }

/* API Path Display */
.item-path {
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* Call Count Badge */
.call-count-badge {
  display: inline-block;
  padding: 2px 8px;
  margin-left: auto;
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 500;
}

/* Item Details */
.item-details {
  margin-top: 4px;
  padding: 6px 10px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-style: italic;
}

/* Item Variants for API Endpoints */
.list-item.item-success {
  border-left: 3px solid var(--chart-green);
  background: rgba(34, 197, 94, 0.05);
}

.list-item.item-warning {
  border-left: 3px solid var(--color-warning);
  background: rgba(245, 158, 11, 0.05);
}

.list-item.item-critical {
  border-left: 3px solid var(--color-error);
  background: rgba(239, 68, 68, 0.05);
}

/* Accordion Header Variants */
.accordion-header.success {
  border-left: 3px solid var(--chart-green);
}

.accordion-header.warning {
  border-left: 3px solid var(--color-warning);
}

.accordion-header.critical {
  border-left: 3px solid var(--color-error);
}

/* Severity Badge Variants for API Endpoints */
.severity-badge.success {
  background: rgba(34, 197, 94, 0.2);
  color: var(--chart-green);
}

.severity-badge.warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning);
}

/* Summary Card Variants */
.summary-card.success {
  border-color: var(--chart-green);
}

.summary-card.success .summary-value {
  color: var(--chart-green);
}

.summary-card.info {
  border-color: var(--chart-blue);
}

.summary-card.info .summary-value {
  color: var(--chart-blue);
}

/* Scan Timestamp */
.scan-timestamp {
  margin-top: 16px;
  padding: 8px 12px;
  background: rgba(30, 41, 59, 0.8);
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.scan-timestamp i {
  color: var(--text-muted);
}

/* Issue #244: Cross-Language Pattern Analysis Section */

</style>
