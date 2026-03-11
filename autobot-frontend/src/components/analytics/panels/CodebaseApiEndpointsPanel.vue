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
