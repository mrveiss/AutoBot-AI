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
          Pre-commit Hooks
        </h2>
        <p class="subtitle">Automated commit quality checks</p>
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
          {{ installing ? 'Installing...' : 'Install Hooks' }}
        </button>
        <button
          v-else
          class="action-btn danger"
          @click="uninstallHooks"
          :disabled="installing"
        >
          <span class="btn-icon">🗑️</span>
          Uninstall
        </button>
        <button class="action-btn secondary" @click="runCheck" :disabled="checking">
          <span v-if="checking" class="spinner"></span>
          <span class="btn-icon">▶️</span>
          {{ checking ? 'Checking...' : 'Run Check' }}
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
          {{ hookStatus.installed ? 'Hooks Installed' : 'Hooks Not Installed' }}
        </span>
        <span class="status-detail" v-if="hookStatus.installed">
          Version {{ hookStatus.version || '1.0.0' }}
          <span v-if="hookStatus.last_run"> • Last run: {{ formatTime(hookStatus.last_run) }}</span>
        </span>
        <span class="status-detail" v-else>
          Install hooks to enable automatic commit checks
        </span>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="summary-cards" v-if="lastResult">
      <div class="summary-card" :class="lastResult.passed ? 'success' : 'error'">
        <div class="card-icon">{{ lastResult.passed ? '✅' : '❌' }}</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.passed ? 'PASSED' : 'BLOCKED' }}</span>
          <span class="card-label">Status</span>
        </div>
      </div>
      <div class="summary-card">
        <div class="card-icon">📄</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.files_checked?.length || 0 }}</span>
          <span class="card-label">Files Checked</span>
        </div>
      </div>
      <div class="summary-card warning" v-if="lastResult.failed_checks > 0">
        <div class="card-icon">⚠️</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.failed_checks }}</span>
          <span class="card-label">Issues Found</span>
        </div>
      </div>
      <div class="summary-card">
        <div class="card-icon">⏱️</div>
        <div class="card-content">
          <span class="card-value">{{ lastResult.duration_ms }}ms</span>
          <span class="card-label">Duration</span>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-grid">
      <!-- Check Results -->
      <div class="panel results-panel">
        <div class="panel-header">
          <h3>Check Results</h3>
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
            <p>Run a check to see results</p>
          </div>
          <div v-else-if="filteredResults.length === 0" class="empty-state">
            <span class="empty-icon">✨</span>
            <p v-if="lastResult.passed">All checks passed!</p>
            <p v-else>No issues in this category</p>
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
          <h3>Check Rules</h3>
          <span class="check-count">
            {{ enabledChecks }}/{{ totalChecks }} enabled
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
              <span class="expand-icon">{{ expandedCategories.includes(category.id) ? '▼' : '▶' }}</span>
            </div>
            <div v-if="expandedCategories.includes(category.id)" class="category-checks">
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
        <h3>Recent Checks</h3>
        <button class="action-btn text" @click="loadHistory">
          Refresh
        </button>
      </div>
      <div class="panel-content">
        <div class="history-list" v-if="checkHistory.length > 0">
          <div
            v-for="(run, index) in checkHistory"
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
          <p>No check history</p>
        </div>
      </div>
    </div>

    <!-- Statistics -->
    <div class="panel stats-panel">
      <div class="panel-header">
        <h3>Statistics</h3>
      </div>
      <div class="panel-content">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-value">{{ summary.total_runs }}</span>
            <span class="stat-label">Total Runs</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ summary.pass_rate }}%</span>
            <span class="stat-label">Pass Rate</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ summary.average_duration_ms }}ms</span>
            <span class="stat-label">Avg Duration</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ summary.checks_enabled }}</span>
            <span class="stat-label">Active Rules</span>
          </div>
        </div>

        <div class="common-issues" v-if="summary.common_issues?.length > 0">
          <h4>Common Issues</h4>
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
import { useToast } from '@/composables/useToast'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('PrecommitHookDashboard')

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
const { showToast } = useToast()
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
const expandedCategories = ref<string[]>(['security', 'debug'])

// Severity filters
const severities = [
  { id: 'all', name: 'All', icon: '📋' },
  { id: 'block', name: 'Block', icon: '🔴' },
  { id: 'warn', name: 'Warn', icon: '🟡' },
  { id: 'info', name: 'Info', icon: '🔵' }
]

// Computed
const filteredResults = computed(() => {
  if (!lastResult.value) return []
  const results = lastResult.value.results.filter(r => !r.passed)
  if (activeSeverity.value === 'all') return results
  return results.filter(r => r.severity === activeSeverity.value)
})

const enabledChecks = computed(() => checks.value.filter(c => c.enabled).length)
const totalChecks = computed(() => checks.value.length)

const checkCategories = computed(() => {
  const cats: Record<string, { enabled: number; total: number }> = {}

  checks.value.forEach(check => {
    if (!cats[check.category]) {
      cats[check.category] = { enabled: 0, total: 0 }
    }
    cats[check.category].total++
    if (check.enabled) cats[check.category].enabled++
  })

  return Object.entries(cats).map(([id, counts]) => ({
    id,
    name: getCategoryName(id),
    ...counts
  }))
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
  const names: Record<string, string> = {
    security: 'Security',
    quality: 'Quality',
    style: 'Style',
    debug: 'Debug',
    docs: 'Documentation'
  }
  return names[category] || category.charAt(0).toUpperCase() + category.slice(1)
}

function getChecksForCategory(category: string): Check[] {
  return checks.value.filter(c => c.category === category)
}

function toggleCategory(category: string) {
  const idx = expandedCategories.value.indexOf(category)
  if (idx >= 0) {
    expandedCategories.value.splice(idx, 1)
  } else {
    expandedCategories.value.push(category)
  }
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return 'Just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return date.toLocaleDateString()
}

function getIssueBarWidth(count: number): string {
  const max = Math.max(...(summary.value.common_issues?.map(i => i.count) || [1]))
  return `${(count / max) * 100}%`
}

async function loadStatus() {
  try {
    const response = await api.get('/api/precommit/status')
    hookStatus.value = response.data
  } catch {
    hookStatus.value = { installed: false }
  }
}

async function loadChecks() {
  try {
    const response = await api.get('/api/precommit/checks')
    checks.value = response.data
  } catch {
    checks.value = getDemoChecks()
  }
}

async function loadHistory() {
  try {
    const response = await api.get('/api/precommit/history')
    checkHistory.value = response.data
  } catch {
    checkHistory.value = []
  }
}

async function loadSummary() {
  try {
    const response = await api.get('/api/precommit/summary')
    summary.value = response.data
  } catch {
    summary.value = getDemoSummary()
  }
}

async function installHooks() {
  installing.value = true
  try {
    await api.post('/api/precommit/install')
    await loadStatus()
    showToast('Pre-commit hooks installed successfully', 'success')
  } catch (error) {
    logger.error('Failed to install hooks:', error)
    showToast('Failed to install hooks', 'error')
  } finally {
    installing.value = false
  }
}

async function uninstallHooks() {
  installing.value = true
  try {
    await api.post('/api/precommit/uninstall')
    await loadStatus()
    showToast('Pre-commit hooks uninstalled', 'info')
  } catch (error) {
    logger.error('Failed to uninstall hooks:', error)
    showToast('Failed to uninstall hooks', 'error')
  } finally {
    installing.value = false
  }
}

async function runCheck() {
  checking.value = true
  try {
    const response = await api.get('/api/precommit/check')
    lastResult.value = response.data
    await loadHistory()
    await loadSummary()

    if (response.data.passed) {
      showToast('All checks passed!', 'success')
    } else {
      showToast(`Found ${response.data.failed_checks} issues`, 'warning')
    }
  } catch {
    // Use demo data
    lastResult.value = getDemoResult()
    showToast('Using demo data - API unavailable', 'warning')
  } finally {
    checking.value = false
  }
}

async function toggleCheck(check: Check) {
  const newState = !check.enabled
  try {
    await api.post(`/api/precommit/checks/${check.id}/toggle`, null, {
      params: { enabled: newState }
    })
    check.enabled = newState
  } catch {
    check.enabled = !newState
    showToast('Failed to update check', 'error')
  }
}

function showHistoryDetail(run: CommitCheckResult) {
  lastResult.value = run
}

// Demo data
function getDemoChecks(): Check[] {
  return [
    { id: 'SEC001', name: 'Hardcoded Password', category: 'security', severity: 'block', enabled: true },
    { id: 'SEC002', name: 'API Key Exposure', category: 'security', severity: 'block', enabled: true },
    { id: 'SEC003', name: 'Private Key in Code', category: 'security', severity: 'block', enabled: true },
    { id: 'SEC004', name: 'Hardcoded IP Address', category: 'security', severity: 'warn', enabled: true },
    { id: 'DBG001', name: 'Console.log Statement', category: 'debug', severity: 'warn', enabled: true },
    { id: 'DBG002', name: 'Print Statement', category: 'debug', severity: 'warn', enabled: true },
    { id: 'DBG003', name: 'Debugger Statement', category: 'debug', severity: 'block', enabled: true },
    { id: 'DBG004', name: 'TODO/FIXME Comment', category: 'debug', severity: 'info', enabled: false },
    { id: 'QUA001', name: 'Empty Except Block', category: 'quality', severity: 'warn', enabled: true },
    { id: 'QUA002', name: 'Magic Number', category: 'quality', severity: 'info', enabled: false },
    { id: 'STY001', name: 'Trailing Whitespace', category: 'style', severity: 'info', enabled: true },
    { id: 'DOC001', name: 'Missing Docstring', category: 'docs', severity: 'info', enabled: false }
  ]
}

function getDemoResult(): CommitCheckResult {
  return {
    passed: false,
    total_checks: 24,
    passed_checks: 21,
    failed_checks: 3,
    warnings: 2,
    blocked: true,
    duration_ms: 42,
    files_checked: ['src/config.py', 'src/utils/helper.js'],
    timestamp: new Date().toISOString(),
    results: [
      {
        check_id: 'SEC001',
        name: 'Hardcoded Password',
        category: 'security',
        severity: 'block',
        passed: false,
        message: 'Detected hardcoded password',
        file: 'src/config.py',
        line: 15,
        snippet: '15: password = "admin123"',
        suggestion: 'Use environment variables or secrets manager'
      },
      {
        check_id: 'DBG001',
        name: 'Console.log Statement',
        category: 'debug',
        severity: 'warn',
        passed: false,
        message: 'Console statement found',
        file: 'src/utils/helper.js',
        line: 42,
        snippet: '42: console.log("debug")',
        suggestion: 'Remove console statements before committing'
      },
      {
        check_id: 'DBG004',
        name: 'TODO/FIXME Comment',
        category: 'debug',
        severity: 'info',
        passed: false,
        message: 'TODO/FIXME comment found',
        file: 'src/config.py',
        line: 8,
        suggestion: 'Consider addressing before committing'
      }
    ]
  }
}

function getDemoSummary(): Summary {
  return {
    total_runs: 47,
    pass_rate: 85.1,
    average_duration_ms: 38,
    common_issues: [
      { check_id: 'DBG001', count: 12, name: 'Console.log' },
      { check_id: 'SEC004', count: 8, name: 'Hardcoded IP' },
      { check_id: 'STY001', count: 6, name: 'Trailing Whitespace' }
    ],
    checks_enabled: 10,
    total_checks: 12
  }
}

onMounted(() => {
  loadStatus()
  loadChecks()
  loadHistory()
  loadSummary()
})
</script>

<style scoped>
.precommit-dashboard {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.header-content h2 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: 1.5rem;
  color: var(--text-primary);
}

.header-content .icon {
  font-size: 1.75rem;
}

.subtitle {
  color: var(--text-secondary);
  margin: 0.25rem 0 0 0;
  font-size: 0.875rem;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

/* Buttons */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn.primary {
  background: var(--accent-color, #3b82f6);
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  background: var(--accent-color-hover, #2563eb);
}

.action-btn.secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.action-btn.secondary:hover:not(:disabled) {
  background: var(--bg-quaternary);
}

.action-btn.danger {
  background: #ef4444;
  color: white;
}

.action-btn.danger:hover:not(:disabled) {
  background: #dc2626;
}

.action-btn.text {
  background: transparent;
  color: var(--accent-color);
  padding: 0.25rem 0.5rem;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Status Banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-radius: 8px;
  border: 1px solid;
}

.status-banner.installed {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.3);
}

.status-banner.not-installed {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.3);
}

.status-icon {
  font-size: 1.5rem;
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
  gap: 1rem;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.summary-card.success {
  border-color: rgba(16, 185, 129, 0.5);
}

.summary-card.error {
  border-color: rgba(239, 68, 68, 0.5);
}

.summary-card.warning {
  border-color: rgba(245, 158, 11, 0.5);
}

.card-icon {
  font-size: 1.5rem;
}

.card-content {
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.card-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 1.5rem;
}

/* Panels */
.panel {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.panel-content {
  padding: 1rem;
  max-height: 400px;
  overflow-y: auto;
}

/* Severity Filters */
.severity-filters {
  display: flex;
  gap: 0.25rem;
}

.filter-btn {
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: none;
  border-radius: 4px;
  font-size: 0.75rem;
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
  gap: 0.75rem;
}

.result-card {
  padding: 0.875rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border-left: 3px solid;
}

.result-card.block {
  border-left-color: #ef4444;
}

.result-card.warn {
  border-left-color: #eab308;
}

.result-card.info {
  border-left-color: #3b82f6;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.severity-badge {
  font-size: 0.875rem;
}

.check-code {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent-color);
  background: var(--bg-quaternary);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.check-name {
  font-weight: 500;
  color: var(--text-primary);
}

.result-location {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.result-message {
  margin: 0 0 0.5rem 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.result-snippet {
  background: var(--bg-quaternary);
  border-radius: 4px;
  padding: 0.5rem;
  margin-bottom: 0.5rem;
}

.result-snippet pre {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-primary);
  overflow-x: auto;
}

.result-suggestion {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: #10b981;
}

/* Config Panel */
.check-count {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.category-section {
  margin-bottom: 1rem;
}

.category-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  cursor: pointer;
}

.category-icon {
  font-size: 1rem;
}

.category-name {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.category-count {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.expand-icon {
  font-size: 0.625rem;
  color: var(--text-tertiary);
}

.category-checks {
  padding: 0.5rem 0 0 1.5rem;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
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
  border-radius: 10px;
  cursor: pointer;
  transition: 0.3s;
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
  transition: 0.3s;
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
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  text-transform: uppercase;
}

.severity-indicator.block {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.severity-indicator.warn {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.severity-indicator.info {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

/* History Panel */
.history-panel {
  grid-column: 1 / 2;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.875rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.history-item:hover {
  background: var(--bg-quaternary);
}

.history-item.failed {
  border-left: 3px solid #ef4444;
}

.history-item.passed {
  border-left: 3px solid #10b981;
}

.history-status {
  font-size: 1rem;
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
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.history-stats {
  display: flex;
  gap: 0.5rem;
}

.stat {
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.625rem;
  font-weight: 600;
}

.stat.failed {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
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
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-item {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.common-issues h4 {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.issue-bar-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.issue-bar-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
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
  border-radius: 4px;
  overflow: hidden;
}

.issue-bar-fill {
  height: 100%;
  background: var(--accent-color);
  border-radius: 4px;
  transition: width 0.3s;
}

.issue-count {
  width: 24px;
  text-align: right;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: var(--text-secondary);
}

.empty-state.small {
  padding: 1.5rem 1rem;
}

.empty-icon {
  font-size: 2.5rem;
  margin-bottom: 0.75rem;
}

.empty-state p {
  margin: 0;
  font-size: 0.875rem;
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
