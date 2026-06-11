<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  Author: mrveiss

  Error Monitoring Dashboard
  Issue #9891 - Wire error-monitoring UI to backend /api/errors/* endpoints
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

      <label class="em-filter-label" :for="'em-hours-filter'">
        {{ $t('errorMonitoring.filters.timelineHours') }}
      </label>
      <select id="em-hours-filter" v-model.number="timelineHours" class="em-select" @change="fetchTimeline()">
        <option :value="1">1h</option>
        <option :value="6">6h</option>
        <option :value="12">12h</option>
        <option :value="24">24h</option>
        <option :value="48">48h</option>
        <option :value="168">7d</option>
      </select>
    </div>

    <div class="em-body">
      <!-- Left column: recent errors + top errors -->
      <div class="em-col-left">
        <!-- Recent errors -->
        <section class="em-section">
          <h3 class="em-section-title">{{ $t('errorMonitoring.sections.recentErrors') }}</h3>
          <div v-if="filteredRecentErrors.length === 0" class="em-empty">
            {{ $t('errorMonitoring.empty.noErrors') }}
          </div>
          <ul v-else class="em-error-list">
            <li
              v-for="(err, idx) in filteredRecentErrors"
              :key="err.trace_id ?? idx"
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
                  {{ $t('errorMonitoring.resolved') }}
                </span>
              </div>
              <div class="em-error-message">{{ err.message ?? $t('errorMonitoring.noMessage') }}</div>
              <div class="em-error-footer">
                <span class="em-error-time">{{ formatTimestamp(err.timestamp) }}</span>
                <button
                  v-if="!err.resolved && err.trace_id"
                  class="em-btn-resolve"
                  :aria-label="$t('errorMonitoring.actions.resolve')"
                  @click="handleResolve(err.trace_id as string)"
                >
                  <Icon name="check-circle" />
                  {{ $t('errorMonitoring.actions.resolve') }}
                </button>
              </div>
            </li>
          </ul>
        </section>

        <!-- Top errors -->
        <section class="em-section">
          <h3 class="em-section-title">{{ $t('errorMonitoring.sections.topErrors') }}</h3>
          <div v-if="topErrors.length === 0" class="em-empty">
            {{ $t('errorMonitoring.empty.noTopErrors') }}
          </div>
          <table v-else class="em-table">
            <thead>
              <tr>
                <th>{{ $t('errorMonitoring.table.component') }}</th>
                <th>{{ $t('errorMonitoring.table.errorCode') }}</th>
                <th>{{ $t('errorMonitoring.table.count') }}</th>
                <th>{{ $t('errorMonitoring.table.lastSeen') }}</th>
                <th>{{ $t('errorMonitoring.table.action') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(te, idx) in topErrors"
                :key="te.trace_id ?? te.error_code ?? idx"
                :class="{ 'em-row-resolved': te.resolved }"
              >
                <td>{{ te.component ?? '—' }}</td>
                <td>{{ te.error_code ?? '—' }}</td>
                <td>{{ te.count ?? '—' }}</td>
                <td>{{ formatTimestamp(te.last_seen) }}</td>
                <td>
                  <button
                    v-if="!te.resolved && te.trace_id"
                    class="em-btn-resolve-sm"
                    :aria-label="$t('errorMonitoring.actions.resolve')"
                    @click="handleResolve(te.trace_id as string)"
                  >
                    <Icon name="check" />
                  </button>
                  <span v-else-if="te.resolved" class="em-badge em-badge-resolved">
                    {{ $t('errorMonitoring.resolved') }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>

      <!-- Right column: categories, components, timeline -->
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

        <!-- Timeline chart (simple bar representation) -->
        <section class="em-section">
          <h3 class="em-section-title">
            {{ $t('errorMonitoring.sections.timeline') }}
            <span class="em-section-sub">({{ timelineHours }}h)</span>
          </h3>
          <div v-if="!timeline || timeline.timeline.length === 0" class="em-empty">
            {{ $t('errorMonitoring.empty.noTimeline') }}
          </div>
          <div v-else class="em-timeline">
            <div
              v-for="entry in timeline.timeline"
              :key="String(entry.hour)"
              class="em-timeline-bar-wrap"
              :title="`Hour ${entry.hour}: ${entry.error_count} errors`"
            >
              <div
                class="em-timeline-bar"
                :style="{ height: `${timelineBarHeight(entry.error_count)}%` }"
              />
              <span class="em-timeline-label">{{ String(entry.hour).slice(-2) }}</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'
import { useErrorMonitoring } from '@/composables/useErrorMonitoring'

const { t } = useI18n()
const logger = createLogger('ErrorMonitoringView')

const {
  statistics,
  recentErrors,
  categories,
  components,
  timeline,
  topErrors,
  isLoading,
  error,
  lastUpdate,
  categoryFilter,
  componentFilter,
  timelineHours,
  totalErrors,
  healthStatus,
  filteredRecentErrors,
  fetchTimeline,
  resolveError,
  refresh,
} = useErrorMonitoring({ autoFetch: true, pollInterval: 60_000 })

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

const maxTimelineCount = computed(() => {
  if (!timeline.value) return 1
  return Math.max(...timeline.value.timeline.map((e: { hour: string | number; error_count: number; errors: unknown[] }) => e.error_count), 1)
})

// ── Helper functions ───────────────────────────────────────────────────────

function componentBarWidth(count: number): number {
  return Math.round((count / maxComponentCount.value) * 100)
}

function timelineBarHeight(count: number): number {
  return Math.max(Math.round((count / maxTimelineCount.value) * 100), count > 0 ? 4 : 0)
}

function formatTimestamp(ts: number | string | undefined): string {
  if (ts === undefined || ts === null) return '—'
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts as string)
  if (isNaN(d.getTime())) return String(ts)
  return d.toLocaleString()
}

async function handleResolve(traceId: string): Promise<void> {
  const ok = await resolveError(traceId)
  if (!ok) {
    logger.warn('resolve did not succeed for trace:', traceId)
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

.em-section-sub {
  font-size: var(--text-xs, 0.75rem);
  color: var(--text-secondary);
  font-weight: 400;
}

.em-empty {
  font-size: var(--text-sm, 0.875rem);
  color: var(--text-secondary);
  padding: var(--spacing-4, 1rem) 0;
  text-align: center;
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
  opacity: 0.5;
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
.em-badge-resolved { background: var(--color-green-100, #dcfce7); color: var(--color-green-700, #15803d); }
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
  font-size: var(--text-xs, 0.75rem);
  border: 1px solid var(--color-success, #16a34a);
  border-radius: var(--radius-sm, 0.25rem);
  color: var(--color-success, #16a34a);
  background: none;
  cursor: pointer;
  transition: background 0.1s;
}

.em-btn-resolve:hover {
  background: var(--color-green-50, #f0fdf4);
}

.em-btn-resolve-sm {
  padding: 0.125rem 0.375rem;
  border: 1px solid var(--color-success, #16a34a);
  border-radius: var(--radius-sm, 0.25rem);
  color: var(--color-success, #16a34a);
  background: none;
  cursor: pointer;
}

/* Table */
.em-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm, 0.875rem);
}

.em-table th {
  text-align: left;
  padding: var(--spacing-2, 0.5rem) var(--spacing-3, 0.75rem);
  border-bottom: 1px solid var(--border-default);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: var(--text-xs, 0.75rem);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.em-table td {
  padding: var(--spacing-2, 0.5rem) var(--spacing-3, 0.75rem);
  border-bottom: 1px solid var(--border-subtle, var(--border-default));
  color: var(--text-primary);
  word-break: break-word;
}

.em-row-resolved {
  opacity: 0.5;
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

/* Timeline */
.em-timeline {
  display: flex;
  align-items: flex-end;
  gap: 0.125rem;
  height: 6rem;
  overflow-x: auto;
}

.em-timeline-bar-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.125rem;
  flex: 1;
  min-width: 1rem;
  height: 100%;
  justify-content: flex-end;
}

.em-timeline-bar {
  width: 100%;
  background: var(--color-primary, #2563eb);
  border-radius: var(--radius-sm, 0.25rem) var(--radius-sm, 0.25rem) 0 0;
  transition: height 0.3s ease;
  min-height: 0;
}

.em-timeline-label {
  font-size: 0.6rem;
  color: var(--text-tertiary, var(--text-secondary));
  white-space: nowrap;
  overflow: hidden;
}
</style>
