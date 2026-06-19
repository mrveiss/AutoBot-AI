<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Pre-commit Hook Dashboard - Git Pre-commit Hook Analyzer
  Issue #223: Git hooks that check for patterns before allowing commits
-->
<template>
  <div class="precommit-dashboard">
    <!-- Header Section -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2>
          <span class="icon">🔒</span>
          {{ $t('analytics.precommit.title') }}
        </h2>
        <p class="subtitle">{{ $t('analytics.precommit.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button
          v-if="!hookStatus.installed"
          class="action-btn primary"
          @click="installHooks"
          :disabled="installing"
        >
          <span v-if="installing" class="spinner"></span>
          <span class="btn-icon">⬇️</span>
          {{ installing ? $t('analytics.precommit.installing') : $t('analytics.precommit.installHooks') }}
        </button>
        <button
          v-else
          class="action-btn danger"
          @click="uninstallHooks"
          :disabled="installing"
        >
          <span class="btn-icon">🗑️</span>
          {{ $t('analytics.precommit.uninstall') }}
        </button>
        <button class="action-btn secondary" @click="runCheck" :disabled="checking">
          <span v-if="checking" class="spinner"></span>
          <span class="btn-icon">▶️</span>
          {{ checking ? $t('analytics.precommit.checking') : $t('analytics.precommit.runCheck') }}
        </button>
      </div>
    </div>

    <!-- Status Banner -->
    <div class="status-banner" :class="hookStatus.installed ? 'installed' : 'not-installed'">
      <div class="status-icon">
        {{ hookStatus.installed ? '✅' : '⚠️' }}
      </div>
      <div class="status-content">
        <span class="status-title">
          {{ hookStatus.installed ? $t('analytics.precommit.hooksInstalled') : $t('analytics.precommit.hooksNotInstalled') }}
        </span>
        <span class="status-detail" v-if="hookStatus.installed">
          Version {{ hookStatus.version || '1.0.0' }}
          <span v-if="hookStatus.last_run"> • Last run: {{ formatTime(hookStatus.last_run) }}</span>
        </span>
        <span class="status-detail" v-else>
          {{ $t('analytics.precommit.installHint') }}
        </span>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="summary-cards" v-if="lastResult">
      <div class="summary-card" :class="lastResult.passed ? 'success' : 'error'">
        <div class="card-icon">{{ lastResult.passed ? '✅' : '❌' }}</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.passed ? $t('analytics.precommit.passed') : $t('analytics.precommit.blocked') }}</span>
          <span class="card-label">{{ $t('analytics.precommit.status') }}</span>
        </div>
      </div>
      <div class="summary-card">
        <div class="card-icon">📄</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.files_checked?.length || 0 }}</span>
          <span class="card-label">{{ $t('analytics.precommit.filesChecked') }}</span>
        </div>
      </div>
      <div class="summary-card warning" v-if="lastResult.failed_checks > 0">
        <div class="card-icon">⚠️</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.failed_checks }}</span>
          <span class="card-label">{{ $t('analytics.precommit.issuesFound') }}</span>
        </div>
      </div>
      <div class="summary-card">
        <div class="card-icon">⏱️</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.duration_ms }}ms</span>
          <span class="card-label">{{ $t('analytics.precommit.duration') }}</span>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-grid">
      <!-- Check Results -->
      <div class="panel results-panel">
        <div class="panel-header">
          <h3>{{ $t('analytics.precommit.checkResults') }}</h3>
          <div class="severity-filters">
            <button
              v-for="sev in severities"
              :key="sev.id"
              class="filter-btn"
              :class="{ active: activeSeverity === sev.id }"
              @click="activeSeverity = sev.id"
            >
              {{ sev.icon }} {{ sev.name }}
            </button>
          </div>
        </div>
        <div class="panel-content">
          <div v-if="!lastResult" class="empty-state">
            <span class="empty-icon">🔍</span>
            <p>{{ $t('analytics.precommit.runCheckToSee') }}</p>
          </div>
          <div v-else-if="filteredResults.length === 0" class="empty-state">
            <span class="empty-icon">✨</span>
            <p v-if="lastResult.passed">{{ $t('analytics.precommit.allPassed') }}</p>
            <p v-else>{{ $t('analytics.precommit.noIssuesInCategory') }}</p>
          </div>
          <div v-else class="results-list">
            <div
              v-for="result in filteredResults"
              :key="result.check_id + result.line"
              class="result-card"
              :class="result.severity"
            >
              <div class="result-header">
                <span class="severity-badge" :class="result.severity">
                  {{ getSeverityIcon(result.severity) }}
                </span>
                <span class="check-code">{{ result.check_id }}</span>
                <span class="check-name">{{ result.name }}</span>
              </div>
              <div class="result-location" v-if="result.file">
                <span class="file-path">{{ result.file }}</span>
                <span class="line-number" v-if="result.line">:{{ result.line }}</span>
              </div>
              <p class="result-message">{{ result.message }}</p>
              <div class="result-snippet" v-if="result.snippet">
                <pre><code>{{ result.snippet }}</code></pre>
              </div>
              <div class="result-suggestion" v-if="result.suggestion">
                <span class="suggestion-icon">💡</span>
                {{ result.suggestion }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Check Configuration -->
      <div class="panel config-panel">
        <div class="panel-header">
          <h3>{{ $t('analytics.precommit.checkRules') }}</h3>
          <span class="check-count">
            {{ $t('analytics.precommit.enabledCount', { enabled: enabledChecks, total: totalChecks }) }}
          </span>
        </div>
        <div class="panel-content">
          <div
            v-for="category in checkCategories"
            :key="category.id"
            class="category-section"
          >
            <div class="category-header" @click="toggleCategory(category.id)">
              <span class="category-icon">{{ getCategoryIcon(category.id) }}</span>
              <span class="category-name">{{ category.name }}</span>
              <span class="category-count">{{ category.enabled }}/{{ category.total }}</span>
              <span class="expand-icon">{{ isCategoryExpanded(category.id) ? '▼' : '▶' }}</span>
            </div>
            <div v-if="isCategoryExpanded(category.id)" class="category-checks">
              <div
                v-for="check in getChecksForCategory(category.id)"
                :key="check.id"
                class="check-item"
                :class="{ enabled: check.enabled }"
              >
                <label class="check-toggle">
                  <input
                    type="checkbox"
                    :checked="check.enabled"
                    @change="toggleCheck(check)"
                  />
                  <span class="toggle-slider"></span>
                </label>
                <div class="check-info">
                  <span class="check-id">{{ check.id }}</span>
                  <span class="check-title">{{ check.name }}</span>
                </div>
                <span class="severity-indicator" :class="check.severity">
                  {{ check.severity }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- History Section -->
    <div class="panel history-panel">
      <div class="panel-header">
        <h3>{{ $t('analytics.precommit.recentChecks') }}</h3>
        <button class="action-btn text" @click="loadHistory">
        {{ $t('analytics.precommit.refresh') }}
        </button>
      </div>
      <div class="panel-content">
        <div class="history-list" v-if="checkHistory.length > 0">
          <div
            v-for="run in checkHistory"
            :key="run.timestamp"
            class="history-item"
            :class="{ passed: run.passed, failed: !run.passed }"
            @click="showHistoryDetail(run)"
          >
            <div class="history-status">
              {{ run.passed ? '✅' : '❌' }}
            </div>
            <div class="history-info">
              <span class="history-time">{{ formatTime(run.timestamp) }}</span>
              <span class="history-files">{{ run.files_checked?.length || 0 }} files</span>
            </div>
            <div class="history-stats">
              <span v-if="run.failed_checks > 0" class="stat failed">
                {{ run.failed_checks }} issues
              </span>
              <span class="stat duration">{{ run.duration_ms }}ms</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state small">
          <p>{{ $t('analytics.precommit.noHistory') }}</p>
        </div>
      </div>
    </div>

    <!-- Statistics -->
    <div class="panel stats-panel">
      <div class="panel-header">
        <h3>{{ $t('analytics.precommit.statistics') }}</h3>
      </div>
      <div class="panel-content">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-value">{{ summary.total_runs }}</span>
            <span class="stat-label">{{ $t('analytics.precommit.totalRuns') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ summary.pass_rate }}%</span>
            <span class="stat-label">{{ $t('analytics.precommit.passRate') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ summary.average_duration_ms }}ms</span>
            <span class="stat-label">{{ $t('analytics.precommit.avgDuration') }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ summary.checks_enabled }}</span>
            <span class="stat-label">{{ $t('analytics.precommit.activeRules') }}</span>
          </div>
        </div>

        <div class="common-issues" v-if="summary.common_issues?.length > 0">
          <h4>{{ $t('analytics.precommit.commonIssues') }}</h4>
          <div class="issue-bar-list">
            <div
              v-for="issue in summary.common_issues"
              :key="issue.check_id"
              class="issue-bar-item"
            >
              <span class="issue-label">{{ issue.check_id }}</span>
              <div class="issue-bar">
                <div
                  class="issue-bar-fill"
                  :style="{ width: getIssueBarWidth(issue.count) }"
                ></div>
              </div>
              <span class="issue-count">{{ issue.count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { useExpansion } from '@/composables/useExpansion'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const { t } = useI18n()

const logger = createLogger('PrecommitHookDashboard')

// Issue #701: Type for API response with data property
interface ApiDataResponse {
  data?: any
  [key: string]: any
}

// Types
interface CheckResult {
  check_id: string
  name: string
  category: string
  severity: 'block' | 'warn' | 'info'
  passed: boolean
  message: string
  file?: string
  line?: number
  snippet?: string
  suggestion?: string
}

interface CommitCheckResult {
  passed: boolean
  total_checks: number
  passed_checks: number
  failed_checks: number
  warnings: number
  blocked: boolean
  duration_ms: number
  results: CheckResult[]
  files_checked: string[]
  timestamp: string
}

interface Check {
  id: string
  name: string
  category: string
  severity: string
  enabled: boolean
}

interface HookStatus {
  installed: boolean
  path?: string
  version?: string
  last_run?: string
}

interface Summary {
  total_runs: number
  pass_rate: number
  average_duration_ms: number
  common_issues: { check_id: string; count: number; name: string }[]
  checks_enabled: number
  total_checks: number
}

// State
const { showToast } = useNotificationBus()
const installing = ref(false)
const checking = ref(false)
const hookStatus = ref<HookStatus>({ installed: false })
const lastResult = ref<CommitCheckResult | null>(null)
const checks = ref<Check[]>([])
const checkHistory = ref<CommitCheckResult[]>([])
const summary = ref<Summary>({
  total_runs: 0,
  pass_rate: 0,
  average_duration_ms: 0,
  common_issues: [],
  checks_enabled: 0,
  total_checks: 0
})
const activeSeverity = ref('all')
const categoryExpansion = useExpansion<string>(['security', 'debug'])
const isCategoryExpanded = categoryExpansion.isExpanded

// Severity filters
const severities = computed(() => [
  { id: 'all', name: t('analytics.precommit.severityAll'), icon: '📋' },
  { id: 'block', name: t('analytics.precommit.severityBlock'), icon: '🔴' },
  { id: 'warn', name: t('analytics.precommit.severityWarn'), icon: '🟡' },
  { id: 'info', name: t('analytics.precommit.severityInfo'), icon: '🔵' }
])

// Computed
const filteredResults = computed(() => {
  if (!lastResult.value) return []
  const results = lastResult.value.results.filter(r => !r.passed)
  if (activeSeverity.value === 'all') return results
  return results.filter(r => r.severity === activeSeverity.value)
})

// Single-pass computed that partitions checks by category, producing both
// the category summary rows and an O(1) lookup map used by getChecksForCategory.
// Replaces a separate forEach (checkCategories) + per-category .filter()
// (getChecksForCategory) that together traversed the array multiple times per
// reactive update.
const checksByCategory = computed((): Map<string, Check[]> => {
  const map = new Map<string, Check[]>()
  for (const check of checks.value) {
    const bucket = map.get(check.category)
    if (bucket) {
      bucket.push(check)
    } else {
      map.set(check.category, [check])
    }
  }
  return map
})

const enabledChecks = computed(() => checks.value.filter(c => c.enabled).length)
const totalChecks = computed(() => checks.value.length)

const checkCategories = computed(() => {
  const result: { id: string; name: string; enabled: number; total: number }[] = []
  for (const [id, items] of checksByCategory.value) {
    result.push({
      id,
      name: getCategoryName(id),
      enabled: items.filter(c => c.enabled).length,
      total: items.length,
    })
  }
  return result
})

// Methods
function getSeverityIcon(severity: string): string {
  const icons: Record<string, string> = {
    block: '🔴',
    warn: '🟡',
    info: '🔵'
  }
  return icons[severity] || '⚪'
}

function getCategoryIcon(category: string): string {
  const icons: Record<string, string> = {
    security: '🔒',
    quality: '⭐',
    style: '🎨',
    debug: '🐛',
    docs: '📝'
  }
  return icons[category] || '📋'
}

function getCategoryName(category: string): string {
  const key = `analytics.precommit.categories.${category}`
  const translated = t(key)
  return translated !== key ? translated : category.charAt(0).toUpperCase() + category.slice(1)
}

function getChecksForCategory(category: string): Check[] {
  return checksByCategory.value.get(category) ?? []
}

function toggleCategory(category: string) {
  categoryExpansion.toggle(category)
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return t('analytics.precommit.justNow')
  if (diff < 3600000) return t('analytics.precommit.minutesAgo', { count: Math.floor(diff / 60000) })
  if (diff < 86400000) return t('analytics.precommit.hoursAgo', { count: Math.floor(diff / 3600000) })
  return date.toLocaleDateString()
}

function getIssueBarWidth(count: number): string {
  const max = Math.max(...(summary.value.common_issues?.map(i => i.count) || [1]))
  return `${(count / max) * 100}%`
}

async function loadStatus() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<HookStatus | ApiDataResponse>(`${getApiBase()}/precommit/status`)
    // Issue #701: Response could be data directly or wrapped
    hookStatus.value = (response as ApiDataResponse).data || response as HookStatus
  } catch (error) {
    logger.warn('Failed to load status:', error)
    hookStatus.value = { installed: false }
  }
}

async function loadChecks() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<Check[] | ApiDataResponse>(`${getApiBase()}/precommit/checks`)
    // Issue #701: Response could be array directly or wrapped in data
    checks.value = Array.isArray(response) ? response : ((response as ApiDataResponse).data || [])
  } catch (error) {
    logger.warn('Failed to load checks:', error)
    checks.value = []
  }
}

async function loadHistory() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<CommitCheckResult[] | ApiDataResponse>(`${getApiBase()}/precommit/history`)
    // Issue #701: Response could be array directly or wrapped in data
    checkHistory.value = Array.isArray(response) ? response : ((response as ApiDataResponse).data || [])
  } catch (error) {
    logger.warn('Failed to load history:', error)
    checkHistory.value = []
  }
}

async function loadSummary() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<Summary | ApiDataResponse>(`${getApiBase()}/precommit/summary`)
    // Issue #701: Response could be data directly or wrapped
    summary.value = (response as ApiDataResponse).data || response as Summary
  } catch (error) {
    logger.warn('Failed to load summary:', error)
    // Keep default empty summary state
  }
}

async function installHooks() {
  installing.value = true
  try {
    // Issue #701: api.post requires data argument
    await api.post<any>(`${getApiBase()}/precommit/install`, {})
    await loadStatus()
    showToast(t('analytics.precommit.installSuccess'), 'success')
  } catch (error) {
    logger.error('Failed to install hooks:', error)
    showToast(t('analytics.precommit.installFailed'), 'error')
  } finally {
    installing.value = false
  }
}

async function uninstallHooks() {
  installing.value = true
  try {
    // Issue #701: api.post requires data argument
    await api.post<any>(`${getApiBase()}/precommit/uninstall`, {})
    await loadStatus()
    showToast(t('analytics.precommit.uninstallSuccess'), 'info')
  } catch (error) {
    logger.error('Failed to uninstall hooks:', error)
    showToast(t('analytics.precommit.uninstallFailed'), 'error')
  } finally {
    installing.value = false
  }
}

async function runCheck() {
  checking.value = true
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<CommitCheckResult | ApiDataResponse>(`${getApiBase()}/precommit/check`)
    // Issue #701: Response could be data directly or wrapped
    lastResult.value = (response as ApiDataResponse).data || response as CommitCheckResult
    await loadHistory()
    await loadSummary()

    const result = lastResult.value
    if (result?.passed) {
      showToast(t('analytics.precommit.allChecksPassed'), 'success')
    } else {
      showToast(t('analytics.precommit.foundIssues', { count: result?.failed_checks || 0 }), 'warning')
    }
  } catch (error) {
    logger.error('Failed to run check:', error)
    showToast(t('analytics.precommit.checkFailed'), 'error')
  } finally {
    checking.value = false
  }
}

async function toggleCheck(check: Check) {
  const newState = !check.enabled
  try {
    // Issue #701: Fixed api.post call - data should be second arg
    await api.post<any>(`${getApiBase()}/precommit/checks/${check.id}/toggle`, { enabled: newState })
    check.enabled = newState
  } catch (error) {
    logger.warn('Failed to toggle check:', error)
    check.enabled = !newState
    showToast(t('analytics.precommit.updateCheckFailed'), 'error')
  }
}

function showHistoryDetail(run: CommitCheckResult) {
  lastResult.value = run
}

onMounted(() => {
  loadStatus()
  loadChecks()
  loadHistory()
  loadSummary()
})
</script>

<style scoped src="@/design-system/styles/dashboard-common.css"></style>
<style scoped src="@/design-system/styles/dashboard-review-precommit.css"></style>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.precommit-dashboard {
  padding: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.action-btn.danger {
  background: var(--color-error);
  color: var(--text-on-primary);
}

.action-btn.danger:hover:not(:disabled) {
  background: var(--color-error-hover);
}

/* Status Banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-lg);
  border: 1px solid;
}

.status-banner.installed {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.status-banner.not-installed {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
}

.status-icon {
  font-size: var(--text-2xl);
}

.status-content {
  display: flex;
  flex-direction: column;
}

.status-title {
  font-weight: 600;
  color: var(--text-primary);
}

.status-detail {
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.summary-card.success {
  border-color: var(--color-success-border);
}

.summary-card.error {
  border-color: var(--color-error-border);
}

.summary-card.warning {
  border-color: var(--color-warning-border);
}

.card-value {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: var(--spacing-6);
}

/* Severity Filters */
.severity-filters {
  display: flex;
  gap: var(--spacing-1);
}

.filter-btn {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: none;
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-btn.active {
  background: var(--accent-color);
  color: white;
}

/* Results List */
.results-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.result-card {
  padding: var(--spacing-3-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border-left: 3px solid;
}

.result-card.block {
  border-left-color: var(--color-error);
}

.result-card.warn {
  border-left-color: var(--color-warning);
}

.result-card.info {
  border-left-color: var(--color-info);
}

.result-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.check-code {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--accent-color);
  background: var(--bg-quaternary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
}

.check-name {
  font-weight: 500;
  color: var(--text-primary);
}

.result-location {
  font-size: var(--text-xs);
  font-family: monospace;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.result-message {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.result-snippet {
  background: var(--bg-quaternary);
  border-radius: var(--radius-default);
  padding: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.result-snippet pre {
  margin: var(--spacing-0);
  font-size: var(--text-xs);
  color: var(--text-primary);
  overflow-x: auto;
}

.result-suggestion {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--color-success);
}

/* Config Panel */
.check-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.category-section {
  margin-bottom: var(--spacing-4);
}

.category-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.category-icon {
  font-size: var(--text-base);
}

.category-name {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.category-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.expand-icon {
  font-size: 0.625rem;
  color: var(--text-tertiary);
}

.category-checks {
  padding: var(--spacing-2) var(--spacing-0) var(--spacing-0) var(--spacing-6);
}

.check-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-0);
  opacity: 0.6;
}

.check-item.enabled {
  opacity: 1;
}

.check-toggle {
  position: relative;
  width: 36px;
  height: 20px;
}

.check-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--bg-quaternary);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: var(--duration-300);
}

.toggle-slider::before {
  position: absolute;
  content: "";
  width: 14px;
  height: 14px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: var(--duration-300);
}

.check-toggle input:checked + .toggle-slider {
  background: var(--accent-color);
}

.check-toggle input:checked + .toggle-slider::before {
  transform: translateX(16px);
}

.check-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.check-id {
  font-size: 0.625rem;
  font-family: monospace;
  color: var(--text-tertiary);
}

.check-title {
  font-size: 0.8125rem;
  color: var(--text-primary);
}

.severity-indicator {
  font-size: 0.625rem;
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  text-transform: uppercase;
}

.severity-indicator.block {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.severity-indicator.warn {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.severity-indicator.info {
  background: var(--color-info-bg);
  color: var(--color-info);
}

/* History Panel */
.history-panel {
  grid-column: 1 / 2;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.history-item.failed {
  border-left: 3px solid var(--color-error);
}

.history-item.passed {
  border-left: 3px solid var(--color-success);
}

.history-status {
  font-size: var(--text-base);
}

.history-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.history-time {
  font-size: 0.8125rem;
  color: var(--text-primary);
}

.history-files {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.stat {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: 0.625rem;
  font-weight: 600;
}

.stat.failed {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stat.duration {
  background: var(--bg-quaternary);
  color: var(--text-secondary);
}

/* Stats Panel */
.stats-panel {
  grid-column: 2 / 3;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-item {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.common-issues h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3) var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.issue-bar-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.issue-bar-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.issue-label {
  width: 60px;
  font-size: 0.6875rem;
  font-family: monospace;
  color: var(--text-secondary);
}

.issue-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-quaternary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.issue-bar-fill {
  height: 100%;
  background: var(--accent-color);
  border-radius: var(--radius-default);
  transition: width var(--duration-300);
}

.issue-count {
  width: 24px;
  text-align: right;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-primary);
}

/* Responsive */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .history-panel,
  .stats-panel {
    grid-column: 1 / -1;
  }
}
</style>
