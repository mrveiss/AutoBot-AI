<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  Author: mrveiss

  Error Monitoring Dashboard
  Backed by /api/errors/* and the /api/errors/metrics/* (Prometheus + Redis)
  endpoints: timeline, top-errors, summary, and resolve. (Wired per #9891, #9983.)
-->
<template>
  <div class="error-monitoring-view">
    <!-- Header row -->
    <div class="em-header">
      <div class="em-header-left">
        <h2 class="em-title">{{ $t('errorMonitoring.title') }}</h2>
        <p class="em-subtitle">{{ $t('errorMonitoring.subtitle') }}</p>
      </div>
      <div class="em-header-actions">
        <span v-if="lastUpdate" class="em-last-update">
          {{ $t('errorMonitoring.lastUpdate') }}: {{ lastUpdateFormatted }}
        </span>
        <button class="em-btn-refresh" :disabled="isLoading" @click="refresh()">
          <Icon name="sync-alt" :spin="isLoading" />
          {{ $t('common.refresh') }}
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="em-error-banner" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="em-btn-dismiss" :aria-label="$t('common.dismiss')" @click="error = null">
        <Icon name="times" />
      </button>
    </div>

    <!-- Summary cards -->
    <div class="em-summary-cards">
      <div class="em-card em-card-total" :class="`em-health-${healthStatus}`">
        <div class="em-card-value">{{ totalErrors }}</div>
        <div class="em-card-label">{{ $t('errorMonitoring.cards.totalErrors') }}</div>
        <div class="em-card-status">{{ healthStatus }}</div>
      </div>

      <template v-if="statistics">
        <div
          v-for="(count, sev) in statistics.severities"
          :key="sev"
          class="em-card em-card-severity"
          :class="`em-sev-${sev}`"
        >
          <div class="em-card-value">{{ count }}</div>
          <div class="em-card-label">{{ sev }}</div>
        </div>
      </template>
    </div>

    <!-- Metrics summary strip (#9983) -->
    <div v-if="summary" class="em-summary-strip">
      <div class="em-strip-item">
        <span class="em-strip-value">{{ summary.total_errors }}</span>
        <span class="em-strip-label">{{ $t('errorMonitoring.summary.totalErrors') }}</span>
      </div>
      <div class="em-strip-item">
        <span class="em-strip-value">{{ summary.unique_error_types }}</span>
        <span class="em-strip-label">{{ $t('errorMonitoring.summary.uniqueTypes') }}</span>
      </div>
      <div class="em-strip-item">
        <span class="em-strip-value">{{ summary.alert_thresholds_configured }}</span>
        <span class="em-strip-label">{{ $t('errorMonitoring.summary.thresholds') }}</span>
      </div>
      <div class="em-strip-item em-strip-prom">
        <span
          class="em-prom-dot"
          :class="prometheusAvailable ? 'em-prom-on' : 'em-prom-off'"
          aria-hidden="true"
        />
        <span class="em-strip-label">
          {{
            prometheusAvailable
              ? $t('errorMonitoring.summary.prometheusOn')
              : $t('errorMonitoring.summary.prometheusOff')
          }}
        </span>
      </div>
    </div>

    <!-- Metrics row: timeline + top errors (#9983) -->
    <div class="em-metrics-row">
      <!-- Timeline -->
      <section class="em-section">
        <h3 class="em-section-title">{{ $t('errorMonitoring.sections.timeline') }}</h3>
        <div v-if="!prometheusAvailable" class="em-empty em-empty-quiet">
          {{ $t('errorMonitoring.empty.metricsUnavailable') }}
        </div>
        <div v-else-if="timeline.length === 0" class="em-empty em-empty-quiet">
          {{ $t('errorMonitoring.empty.noData') }}
        </div>
        <div v-else class="em-sparkline-wrap">
          <svg
            class="em-sparkline"
            :viewBox="`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`"
            preserveAspectRatio="none"
            role="img"
            :aria-label="$t('errorMonitoring.sections.timeline')"
          >
            <polyline class="em-sparkline-line" :points="sparklinePoints" />
          </svg>
          <div class="em-sparkline-axis">
            <span>{{ timelineRange.start }}</span>
            <span>{{ $t('errorMonitoring.timeline.peak', { n: timelineMax }) }}</span>
            <span>{{ timelineRange.end }}</span>
          </div>
        </div>
      </section>

      <!-- Top errors -->
      <section class="em-section">
        <h3 class="em-section-title">{{ $t('errorMonitoring.sections.topErrors') }}</h3>
        <div v-if="topErrors.length === 0" class="em-empty em-empty-quiet">
          {{ $t('errorMonitoring.empty.noData') }}
        </div>
        <table v-else class="em-top-table">
          <thead>
            <tr>
              <th>{{ $t('errorMonitoring.topErrors.component') }}</th>
              <th>{{ $t('errorMonitoring.topErrors.errorCode') }}</th>
              <th class="em-top-count-col">{{ $t('errorMonitoring.topErrors.count') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in topErrors" :key="`${row.component}-${row.error_code}-${idx}`">
              <td>{{ row.component }}</td>
              <td><code class="em-code">{{ row.error_code }}</code></td>
              <td class="em-top-count-col">{{ row.count }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <!-- Filter row -->
    <div class="em-filters">
      <label class="em-filter-label" :for="'em-cat-filter'">
        {{ $t('errorMonitoring.filters.category') }}
      </label>
      <select id="em-cat-filter" v-model="categoryFilter" class="em-select">
        <option value="">{{ $t('errorMonitoring.filters.all') }}</option>
        <option
          v-for="cat in availableCategories"
          :key="cat"
          :value="cat"
        >{{ cat }}</option>
      </select>

      <label class="em-filter-label" :for="'em-comp-filter'">
        {{ $t('errorMonitoring.filters.component') }}
      </label>
      <select id="em-comp-filter" v-model="componentFilter" class="em-select">
        <option value="">{{ $t('errorMonitoring.filters.all') }}</option>
        <option
          v-for="comp in availableComponents"
          :key="comp"
          :value="comp"
        >{{ comp }}</option>
      </select>
    </div>

    <div class="em-body">
      <!-- Left column: recent errors -->
      <div class="em-col-left">
        <section class="em-section">
          <h3 class="em-section-title">{{ $t('errorMonitoring.sections.recentErrors') }}</h3>
          <div v-if="filteredRecentErrors.length === 0" class="em-empty">
            {{ $t('errorMonitoring.empty.noErrors') }}
          </div>
          <ul v-else class="em-error-list">
            <li
              v-for="(err, idx) in filteredRecentErrors"
              :key="err.error_id ?? idx"
              class="em-error-item"
              :class="{ 'em-error-resolved': err.resolved }"
            >
              <div class="em-error-meta">
                <span class="em-badge em-badge-category">{{ err.category ?? '—' }}</span>
                <span class="em-badge em-badge-component">{{ err.component ?? '—' }}</span>
                <span class="em-badge" :class="`em-sev-${err.severity ?? 'unknown'}`">
                  {{ err.severity ?? '—' }}
                </span>
                <span v-if="err.resolved" class="em-badge em-badge-resolved">
                  <Icon name="check" />
                  {{ $t('errorMonitoring.resolve.resolved') }}
                </span>
              </div>
              <div class="em-error-message">{{ err.message ?? $t('errorMonitoring.noMessage') }}</div>
              <div class="em-error-footer">
                <span class="em-error-time">{{ formatTimestamp(err.timestamp) }}</span>
                <button
                  v-if="!err.resolved && err.error_id"
                  class="em-btn-resolve"
                  :disabled="resolvingIds.has(err.error_id)"
                  @click="onResolve(err.error_id)"
                >
                  <Icon name="check" :spin="resolvingIds.has(err.error_id)" />
                  {{ $t('errorMonitoring.resolve.action') }}
                </button>
              </div>
            </li>
          </ul>
        </section>
      </div>

      <!-- Right column: categories, components -->
      <div class="em-col-right">
        <!-- Category breakdown -->
        <section class="em-section">
          <h3 class="em-section-title">{{ $t('errorMonitoring.sections.categories') }}</h3>
          <div v-if="!categories || categories.total_errors === 0" class="em-empty">
            {{ $t('errorMonitoring.empty.noData') }}
          </div>
          <ul v-else class="em-breakdown-list">
            <li
              v-for="(stats, cat) in categories.categories"
              :key="cat"
              class="em-breakdown-item"
            >
              <span class="em-breakdown-name">{{ cat }}</span>
              <div class="em-breakdown-bar-wrap">
                <div
                  class="em-breakdown-bar"
                  :style="{ width: `${stats.percentage}%` }"
                />
              </div>
              <span class="em-breakdown-count">{{ stats.count }}</span>
              <span class="em-breakdown-pct">{{ stats.percentage }}%</span>
            </li>
          </ul>
        </section>

        <!-- Component breakdown -->
        <section class="em-section">
          <h3 class="em-section-title">{{ $t('errorMonitoring.sections.components') }}</h3>
          <div v-if="!components || Object.keys(components.components).length === 0" class="em-empty">
            {{ $t('errorMonitoring.empty.noData') }}
          </div>
          <ul v-else class="em-breakdown-list">
            <li
              v-for="(count, comp) in components.components"
              :key="comp"
              class="em-breakdown-item"
            >
              <span class="em-breakdown-name">{{ comp }}</span>
              <div class="em-breakdown-bar-wrap">
                <div
                  class="em-breakdown-bar em-bar-component"
                  :style="{ width: `${componentBarWidth(count as number)}%` }"
                />
              </div>
              <span class="em-breakdown-count">{{ count }}</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import { useErrorMonitoring } from '@/composables/useErrorMonitoring'

const {
  statistics,
  categories,
  components,
  summary,
  timeline,
  topErrors,
  isLoading,
  error,
  lastUpdate,
  categoryFilter,
  componentFilter,
  totalErrors,
  healthStatus,
  filteredRecentErrors,
  prometheusAvailable,
  resolveError,
  refresh,
} = useErrorMonitoring({ autoFetch: true, pollInterval: 60_000 })

// ── Sparkline geometry (viewBox units; scaled by CSS) ───────────────────────
const SPARK_WIDTH = 300
const SPARK_HEIGHT = 48

// In-flight resolve calls, to disable the per-row button while pending
const resolvingIds = ref<Set<string>>(new Set())

// ── Computed helpers ───────────────────────────────────────────────────────

const lastUpdateFormatted = computed(() => {
  if (!lastUpdate.value) return ''
  return lastUpdate.value.toLocaleTimeString()
})

const availableCategories = computed(() => {
  if (!categories.value) return []
  return Object.keys(categories.value.categories)
})

const availableComponents = computed(() => {
  if (!components.value) return []
  return Object.keys(components.value.components)
})

const maxComponentCount = computed(() => {
  if (!components.value) return 1
  const vals = Object.values(components.value.components) as number[]
  return Math.max(...vals, 1)
})

// ── Timeline (sparkline) ────────────────────────────────────────────────────

const timelineMax = computed(() => {
  if (timeline.value.length === 0) return 0
  return Math.max(...timeline.value.map((p) => p.value), 0)
})

const sparklinePoints = computed(() => {
  const pts = timeline.value
  if (pts.length === 0) return ''
  const max = Math.max(timelineMax.value, 1)
  const stepX = pts.length > 1 ? SPARK_WIDTH / (pts.length - 1) : 0
  return pts
    .map((p, i) => {
      const x = i * stepX
      const y = SPARK_HEIGHT - (p.value / max) * SPARK_HEIGHT
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

const timelineRange = computed(() => {
  const pts = timeline.value
  if (pts.length === 0) return { start: '', end: '' }
  return {
    start: formatTimestamp(pts[0].timestamp),
    end: formatTimestamp(pts[pts.length - 1].timestamp),
  }
})

// ── Helper functions ───────────────────────────────────────────────────────

function componentBarWidth(count: number): number {
  return Math.round((count / maxComponentCount.value) * 100)
}

function formatTimestamp(ts: number | string | undefined): string {
  if (ts === undefined || ts === null) return '—'
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts as string)
  if (isNaN(d.getTime())) return String(ts)
  return d.toLocaleString()
}

async function onResolve(errorId: string): Promise<void> {
  const pending = new Set(resolvingIds.value)
  pending.add(errorId)
  resolvingIds.value = pending
  try {
    await resolveError(errorId)
  } finally {
    const next = new Set(resolvingIds.value)
    next.delete(errorId)
    resolvingIds.value = next
  }
}

</script>

<style scoped>
.error-monitoring-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5, 1.25rem);
  padding: var(--spacing-6, 1.5rem) var(--spacing-8, 2rem);
  height: 100%;
  overflow-y: auto;
  background-color: var(--bg-primary);
}

/* Header */
.em-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4, 1rem);
  flex-wrap: wrap;
}

.em-header-left {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1, 0.25rem);
}

.em-title {
  margin: 0;
  font-size: var(--text-xl, 1.25rem);
  font-weight: 600;
  color: var(--text-primary);
}

.em-subtitle {
  margin: 0;
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-secondary);
}

.em-header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-3, 0.75rem);
  flex-wrap: wrap;
}

.em-last-update {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-tertiary, var(--text-secondary));
}

.em-btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
  padding: var(--spacing-2, 0.5rem) var(--spacing-4, 1rem);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 0.375rem);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm, 0.875rem);
  cursor: pointer;
  transition: background 0.15s;
}

.em-btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover, var(--bg-tertiary));
}

.em-btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error banner */
.em-error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
  padding: var(--spacing-3, 0.75rem) var(--spacing-4, 1rem);
  border-radius: var(--radius-md, 0.375rem);
  background: var(--color-error-bg, #fef2f2);
  border: 1px solid var(--color-error-border, #fecaca);
  color: var(--color-error-text, #dc2626);
  font-size: var(--text-sm, 0.875rem);
}

.em-btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 0;
}

/* Summary cards */
.em-summary-cards {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4, 1rem);
}

.em-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-4, 1rem) var(--spacing-5, 1.25rem);
  border-radius: var(--radius-lg, 0.5rem);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  min-width: 7rem;
  text-align: center;
}

.em-card-value {
  font-size: var(--text-2xl, 1.5rem);
  font-weight: 700;
  color: var(--text-primary);
}

.em-card-label {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.em-card-status {
  font-size: var(--text-xs, 0.75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: var(--spacing-1, 0.25rem);
}

/* Health / severity colouring */
.em-health-excellent .em-card-status,
.em-health-healthy .em-card-status { color: var(--color-success, #16a34a); }
.em-health-warning .em-card-status  { color: var(--color-warning, #d97706); }
.em-health-degraded .em-card-status { color: var(--color-warning, #d97706); }
.em-health-critical .em-card-status { color: var(--color-error, #dc2626); }

.em-sev-critical { border-color: var(--color-error, #dc2626); }
.em-sev-critical .em-card-value { color: var(--color-error, #dc2626); }
.em-sev-high .em-card-value { color: var(--color-warning, #d97706); }

/* Metrics summary strip */
.em-summary-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-6, 1.5rem);
  padding: var(--spacing-3, 0.75rem) var(--spacing-5, 1.25rem);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg, 0.5rem);
  background: var(--bg-secondary);
}

.em-strip-item {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-2, 0.5rem);
}

.em-strip-value {
  font-size: var(--text-lg, 1.125rem);
  font-weight: 700;
  color: var(--text-primary);
}

.em-strip-label {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary);
}

.em-strip-prom {
  margin-left: auto;
  align-items: center;
}

.em-prom-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 9999px;
  display: inline-block;
}

.em-prom-on { background: var(--color-success, #16a34a); }
.em-prom-off { background: var(--text-tertiary, #9ca3af); }

/* Metrics row (timeline + top errors) */
.em-metrics-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6, 1.5rem);
}

@media (max-width: 1024px) {
  .em-metrics-row {
    grid-template-columns: 1fr;
  }
}

/* Sparkline */
.em-sparkline-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2, 0.5rem);
}

.em-sparkline {
  width: 100%;
  height: 3rem;
}

.em-sparkline-line {
  fill: none;
  stroke: var(--color-primary, #2563eb);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.em-sparkline-axis {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-tertiary, var(--text-secondary));
}

/* Top-errors table */
.em-top-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm, 0.875rem);
}

.em-top-table th {
  text-align: left;
  font-weight: 600;
  color: var(--text-secondary);
  padding: var(--spacing-1, 0.25rem) var(--spacing-2, 0.5rem);
  border-bottom: 1px solid var(--border-default);
}

.em-top-table td {
  padding: var(--spacing-1, 0.25rem) var(--spacing-2, 0.5rem);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-subtle, var(--border-default));
}

.em-top-count-col {
  text-align: right;
  white-space: nowrap;
}

.em-code {
  font-family: var(--font-mono, monospace);
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary);
}

/* Filters */
.em-filters {
  display: flex;
  align-items: center;
  gap: var(--spacing-3, 0.75rem);
  flex-wrap: wrap;
}

.em-filter-label {
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-secondary);
  white-space: nowrap;
}

.em-select {
  padding: var(--spacing-1, 0.25rem) var(--spacing-3, 0.75rem);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 0.375rem);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm, 0.875rem);
}

/* Body layout */
.em-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6, 1.5rem);
  flex: 1;
  min-height: 0;
}

@media (max-width: 1024px) {
  .em-body {
    grid-template-columns: 1fr;
  }
}

.em-col-left,
.em-col-right {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5, 1.25rem);
}

/* Sections */
.em-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg, 0.5rem);
  padding: var(--spacing-4, 1rem);
}

.em-section-title {
  margin: 0 0 var(--spacing-3, 0.75rem);
  font-size: var(--text-base, 1rem);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
}

.em-empty {
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-secondary);
  padding: var(--spacing-4, 1rem) 0;
  text-align: center;
}

.em-empty-quiet {
  color: var(--text-tertiary, var(--text-secondary));
  font-style: italic;
}

/* Error list */
.em-error-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3, 0.75rem);
  max-height: 20rem;
  overflow-y: auto;
}

.em-error-item {
  padding: var(--spacing-3, 0.75rem);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 0.375rem);
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1, 0.25rem);
}

.em-error-resolved {
  opacity: 0.65;
}

.em-error-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1, 0.25rem);
}

.em-badge {
  font-size: var(--text-xs, 0.75rem);
  padding: 0.125rem var(--spacing-2, 0.5rem);
  border-radius: 9999px;
  background: var(--bg-tertiary, var(--bg-hover, #e5e7eb));
  color: var(--text-secondary);
}

.em-badge-category { background: var(--color-blue-100, #dbeafe); color: var(--color-blue-700, #1d4ed8); }
.em-badge-component { background: var(--color-purple-100, #ede9fe); color: var(--color-purple-700, #6d28d9); }
.em-badge-resolved {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: var(--color-green-100, #dcfce7);
  color: var(--color-green-700, #15803d);
}
.em-sev-critical { background: var(--color-red-100, #fee2e2); color: var(--color-red-700, #b91c1c); }
.em-sev-high { background: var(--color-orange-100, #ffedd5); color: var(--color-orange-700, #c2410c); }
.em-sev-warning { background: var(--color-yellow-100, #fef9c3); color: var(--color-yellow-700, #a16207); }

.em-error-message {
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-primary);
  word-break: break-word;
}

.em-error-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-2, 0.5rem);
}

.em-error-time {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-tertiary, var(--text-secondary));
}

.em-btn-resolve {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1, 0.25rem);
  padding: 0.125rem var(--spacing-2, 0.5rem);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 0.375rem);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--text-xs, 0.75rem);
  cursor: pointer;
  transition: background 0.15s;
}

.em-btn-resolve:hover:not(:disabled) {
  background: var(--bg-hover, var(--bg-tertiary));
  color: var(--text-primary);
}

.em-btn-resolve:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Breakdown list */
.em-breakdown-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2, 0.5rem);
}

.em-breakdown-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
  font-size: var(--text-sm, 0.875rem);
}

.em-breakdown-name {
  min-width: 7rem;
  max-width: 9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.em-breakdown-bar-wrap {
  flex: 1;
  height: 0.5rem;
  background: var(--bg-tertiary, #e5e7eb);
  border-radius: 9999px;
  overflow: hidden;
}

.em-breakdown-bar {
  height: 100%;
  border-radius: 9999px;
  background: var(--color-primary, #2563eb);
  transition: width 0.3s ease;
}

.em-bar-component {
  background: var(--color-purple-500, #7c3aed);
}

.em-breakdown-count {
  min-width: 2rem;
  text-align: right;
  font-weight: 600;
  color: var(--text-primary);
}

.em-breakdown-pct {
  min-width: 3.5rem;
  text-align: right;
  color: var(--text-secondary);
}
</style>
