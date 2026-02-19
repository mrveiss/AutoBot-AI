<template>
  <div class="log-pattern-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2><i class="fas fa-stream"></i> Dynamic Log Pattern Mining</h2>
        <p class="subtitle">Discover patterns, anomalies, and trends in log data</p>
      </div>
      <div class="header-actions">
        <select v-model="timeRange" class="time-select">
          <option value="1">Last 1 hour</option>
          <option value="6">Last 6 hours</option>
          <option value="24">Last 24 hours</option>
          <option value="72">Last 3 days</option>
          <option value="168">Last 7 days</option>
        </select>
        <button @click="runAnalysis" class="analyze-btn" :disabled="isAnalyzing">
          <i :class="isAnalyzing ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          {{ isAnalyzing ? 'Analyzing...' : 'Analyze Logs' }}
        </button>
      </div>
    </div>

    <!-- Real-time Summary -->
    <div class="realtime-summary" v-if="realtimeData">
      <div class="summary-card">
        <div class="summary-icon"><i class="fas fa-clock"></i></div>
        <div class="summary-content">
          <div class="summary-value">{{ realtimeData.logs_last_5min }}</div>
          <div class="summary-label">Logs (5 min)</div>
        </div>
      </div>
      <div class="summary-card" :class="{ 'has-errors': realtimeData.error_count > 0 }">
        <div class="summary-icon"><i class="fas fa-exclamation-triangle"></i></div>
        <div class="summary-content">
          <div class="summary-value">{{ realtimeData.error_count }}</div>
          <div class="summary-label">Recent Errors</div>
        </div>
      </div>
      <div class="summary-card">
        <div class="summary-icon"><i class="fas fa-layer-group"></i></div>
        <div class="summary-content">
          <div class="summary-value">{{ miningResult?.summary?.unique_patterns || 0 }}</div>
          <div class="summary-label">Patterns Found</div>
        </div>
      </div>
      <div class="summary-card" :class="{ 'has-anomalies': (miningResult?.anomalies?.length || 0) > 0 }">
        <div class="summary-icon"><i class="fas fa-bolt"></i></div>
        <div class="summary-content">
          <div class="summary-value">{{ miningResult?.anomalies?.length || 0 }}</div>
          <div class="summary-label">Anomalies</div>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid" v-if="miningResult">
      <!-- Patterns Panel -->
      <div class="panel patterns-panel">
        <div class="panel-header">
          <h3><i class="fas fa-fingerprint"></i> Discovered Patterns</h3>
          <span class="pattern-count">{{ miningResult.patterns.length }} patterns</span>
        </div>
        <div class="panel-content">
          <div class="pattern-filters">
            <button
              v-for="filter in patternFilters"
              :key="filter.value"
              @click="selectedPatternFilter = filter.value"
              :class="['filter-btn', { active: selectedPatternFilter === filter.value }]"
            >
              {{ filter.label }}
            </button>
          </div>
          <div class="patterns-list">
            <div
              v-for="pattern in filteredPatterns"
              :key="pattern.pattern_id"
              class="pattern-item"
              :class="{ 'is-error': pattern.is_error_pattern }"
              @click="selectedPattern = pattern"
            >
              <div class="pattern-header">
                <span class="pattern-id">{{ pattern.pattern_id }}</span>
                <span class="occurrence-badge">{{ pattern.occurrences }}x</span>
              </div>
              <div class="pattern-template">{{ truncate(pattern.pattern_template, 120) }}</div>
              <div class="pattern-meta">
                <span class="meta-item">
                  <i class="fas fa-chart-line"></i> {{ pattern.frequency_per_hour }}/hr
                </span>
                <span class="meta-item">
                  <i class="fas fa-folder"></i> {{ pattern.sources.join(', ') }}
                </span>
                <span v-for="level in pattern.log_levels" :key="level" :class="['level-badge', `level-${level.toLowerCase()}`]">
                  {{ level }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Anomalies Panel -->
      <div class="panel anomalies-panel">
        <div class="panel-header">
          <h3><i class="fas fa-exclamation-circle"></i> Detected Anomalies</h3>
        </div>
        <div class="panel-content">
          <div v-if="miningResult.anomalies.length === 0" class="empty-state">
            <i class="fas fa-check-circle"></i>
            <p>No anomalies detected</p>
          </div>
          <div v-else class="anomalies-list">
            <div
              v-for="anomaly in miningResult.anomalies"
              :key="anomaly.anomaly_id"
              class="anomaly-item"
              :class="`severity-${anomaly.severity}`"
            >
              <div class="anomaly-header">
                <span :class="['severity-badge', `severity-${anomaly.severity}`]">
                  {{ anomaly.severity.toUpperCase() }}
                </span>
                <span class="anomaly-type">{{ formatAnomalyType(anomaly.anomaly_type) }}</span>
              </div>
              <p class="anomaly-description">{{ anomaly.description }}</p>
              <div class="anomaly-meta">
                <span><i class="fas fa-clock"></i> {{ formatTimestamp(anomaly.timestamp) }}</span>
                <span><i class="fas fa-percentage"></i> {{ Math.round(anomaly.confidence * 100) }}% confidence</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Trends Panel -->
      <div class="panel trends-panel">
        <div class="panel-header">
          <h3><i class="fas fa-chart-bar"></i> Log Trends</h3>
        </div>
        <div class="panel-content">
          <div v-if="miningResult.trends.length === 0" class="empty-state">
            <i class="fas fa-minus"></i>
            <p>Not enough data for trend analysis</p>
          </div>
          <div v-else class="trends-list">
            <div v-for="trend in miningResult.trends" :key="trend.trend_id" class="trend-item">
              <div class="trend-header">
                <span class="trend-name">{{ trend.metric_name }}</span>
                <span :class="['trend-direction', `direction-${trend.direction}`]">
                  <i :class="getTrendIcon(trend.direction)"></i>
                  {{ trend.change_percent > 0 ? '+' : '' }}{{ trend.change_percent }}%
                </span>
              </div>
              <div class="trend-chart">
                <svg viewBox="0 0 200 50" class="sparkline">
                  <polyline
                    :points="getTrendPoints(trend)"
                    fill="none"
                    :stroke="getTrendColor(trend.direction)"
                    stroke-width="2"
                  />
                </svg>
              </div>
              <div class="trend-period">{{ trend.time_period }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Pattern Details Modal -->
    <div v-if="selectedPattern" class="modal-overlay" @click="selectedPattern = null">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>Pattern Details: {{ selectedPattern.pattern_id }}</h3>
          <button @click="selectedPattern = null" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="detail-section">
            <h4>Pattern Template</h4>
            <pre class="pattern-code">{{ selectedPattern.pattern_template }}</pre>
          </div>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="label">Occurrences</span>
              <span class="value">{{ selectedPattern.occurrences }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Frequency</span>
              <span class="value">{{ selectedPattern.frequency_per_hour }}/hour</span>
            </div>
            <div class="detail-item">
              <span class="label">First Seen</span>
              <span class="value">{{ formatTimestamp(selectedPattern.first_seen) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Last Seen</span>
              <span class="value">{{ formatTimestamp(selectedPattern.last_seen) }}</span>
            </div>
          </div>
          <div class="detail-section">
            <h4>Sample Messages</h4>
            <div class="sample-messages">
              <div v-for="(msg, idx) in selectedPattern.sample_messages" :key="idx" class="sample-msg">
                {{ msg }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isAnalyzing && !miningResult" class="loading-overlay">
      <div class="loading-spinner">
        <i class="fas fa-cog fa-spin fa-3x"></i>
        <p>Mining log patterns...</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LogPatternDashboard')

// Types
interface LogPattern {
  pattern_id: string
  pattern_template: string
  occurrences: number
  first_seen: string
  last_seen: string
  log_levels: string[]
  sources: string[]
  sample_messages: string[]
  frequency_per_hour: number
  is_error_pattern: boolean
  is_anomaly: boolean
}

interface LogAnomaly {
  anomaly_id: string
  anomaly_type: string
  severity: string
  description: string
  timestamp: string
  affected_sources: string[]
  metric_before: number
  metric_after: number
  confidence: number
}

interface LogTrend {
  trend_id: string
  metric_name: string
  direction: string
  change_percent: number
  time_period: string
  data_points: Array<Record<string, unknown>>
}

interface MiningResult {
  patterns: LogPattern[]
  anomalies: LogAnomaly[]
  trends: LogTrend[]
  summary: {
    total_logs: number
    unique_patterns: number
    error_patterns: number
    anomalies_detected: number
  }
  analysis_time_ms: number
  logs_analyzed: number
}

interface RealtimeData {
  logs_last_5min: number
  error_count: number
  level_counts: Record<string, number>
  recent_errors: Array<Record<string, unknown>>
}

// State
const timeRange = ref(24)
const isAnalyzing = ref(false)
const miningResult = ref<MiningResult | null>(null)
const realtimeData = ref<RealtimeData | null>(null)
const selectedPattern = ref<LogPattern | null>(null)
const selectedPatternFilter = ref('all')

const patternFilters = [
  { label: 'All', value: 'all' },
  { label: 'Errors', value: 'errors' },
  { label: 'Warnings', value: 'warnings' },
  { label: 'High Frequency', value: 'high_freq' }
]

let realtimeInterval: ReturnType<typeof setInterval> | null = null

// Helper to get CSS variable values for dynamic JS usage
const getCssVar = (varName: string): string => {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

// Computed
const filteredPatterns = computed(() => {
  if (!miningResult.value) return []

  let patterns = miningResult.value.patterns

  switch (selectedPatternFilter.value) {
    case 'errors':
      return patterns.filter(p => p.is_error_pattern)
    case 'warnings':
      return patterns.filter(p => p.log_levels.includes('WARNING'))
    case 'high_freq':
      return patterns.filter(p => p.frequency_per_hour > 10)
    default:
      return patterns
  }
})

// Methods
const runAnalysis = async () => {
  isAnalyzing.value = true
  try {
    const response = await fetchWithAuth(
      `/api/log-patterns/mine?hours=${timeRange.value}&include_anomalies=true&include_trends=true`
    )
    if (response.ok) {
      miningResult.value = await response.json()
    }
  } catch (error) {
    logger.error('Failed to run log analysis:', error)
  } finally {
    isAnalyzing.value = false
  }
}

const fetchRealtimeData = async () => {
  try {
    const response = await fetchWithAuth('/api/log-patterns/realtime')
    if (response.ok) {
      realtimeData.value = await response.json()
    }
  } catch (error) {
    logger.error('Failed to fetch realtime data:', error)
  }
}

const truncate = (text: string, length: number): string => {
  if (text.length <= length) return text
  return text.substring(0, length) + '...'
}

const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'N/A'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch (error) {
    logger.warn('Failed to parse timestamp:', error)
    return timestamp
  }
}

const formatAnomalyType = (type: string): string => {
  const typeMap: Record<string, string> = {
    'error_surge': 'Error Surge',
    'new_pattern': 'New Pattern',
    'gap': 'Log Gap',
    'spike': 'Activity Spike'
  }
  return typeMap[type] || type
}

const getTrendIcon = (direction: string): string => {
  switch (direction) {
    case 'increasing': return 'fas fa-arrow-up'
    case 'decreasing': return 'fas fa-arrow-down'
    default: return 'fas fa-minus'
  }
}

const getTrendColor = (direction: string): string => {
  switch (direction) {
    case 'increasing': return getCssVar('--color-error')
    case 'decreasing': return getCssVar('--color-success')
    default: return getCssVar('--text-muted')
  }
}

const getTrendPoints = (trend: LogTrend): string => {
  if (!trend.data_points || trend.data_points.length === 0) return ''

  const values = trend.data_points.map(dp => {
    const val = dp.count || dp.error_rate || 0
    return typeof val === 'number' ? val : 0
  })

  const max = Math.max(...values, 1)
  const step = 200 / Math.max(values.length - 1, 1)

  return values.map((v, i) => `${i * step},${50 - (v / max) * 45}`).join(' ')
}

// Lifecycle
onMounted(() => {
  fetchRealtimeData()
  runAnalysis()

  // Refresh realtime data every 30 seconds
  realtimeInterval = setInterval(fetchRealtimeData, 30000)
})

onUnmounted(() => {
  if (realtimeInterval) {
    clearInterval(realtimeInterval)
  }
})
</script>

<style scoped>
.log-pattern-dashboard {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  min-height: 100vh;
  color: var(--text-primary);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.header-content h2 {
  margin: 0;
  font-size: var(--text-2xl);
  color: var(--text-primary);
}

.header-content h2 i {
  color: var(--color-primary);
  margin-right: var(--spacing-2);
}

.subtitle {
  margin: var(--spacing-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-4);
  align-items: center;
}

.time-select {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  cursor: pointer;
}

.analyze-btn {
  padding: var(--spacing-2) var(--spacing-5);
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-on-primary);
  font-weight: var(--font-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: var(--transition-all);
}

.analyze-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary);
}

.analyze-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Realtime Summary */
.realtime-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.summary-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.summary-card.has-errors {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.summary-card.has-anomalies {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-xl);
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  color: var(--color-primary);
}

.summary-value {
  font-size: 1.75rem;
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6);
}

/* Panels */
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.patterns-panel {
  grid-column: 1;
  grid-row: span 2;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
  margin: 0;
  font-size: var(--text-base);
  color: var(--text-primary);
}

.panel-header h3 i {
  margin-right: var(--spacing-2);
  color: var(--color-primary);
}

.pattern-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-xl);
}

.panel-content {
  padding: var(--spacing-4);
  max-height: 600px;
  overflow-y: auto;
}

/* Pattern Filters */
.pattern-filters {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
}

.filter-btn {
  padding: var(--spacing-1-5) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: var(--transition-all);
}

.filter-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.filter-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary);
}

/* Pattern Items */
.patterns-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.pattern-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
  cursor: pointer;
  transition: var(--transition-all);
}

.pattern-item:hover {
  border-color: var(--color-primary);
  transform: translateX(2px);
}

.pattern-item.is-error {
  border-left: 3px solid var(--color-error);
}

.pattern-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.pattern-id {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-primary);
}

.occurrence-badge {
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-lg);
  font-size: 0.7rem;
  color: var(--text-secondary);
}

.pattern-template {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-2);
  word-break: break-all;
}

.pattern-meta {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
  font-size: 0.7rem;
}

.meta-item {
  color: var(--text-secondary);
}

.meta-item i {
  margin-right: var(--spacing-1);
}

.level-badge {
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: 0.65rem;
  font-weight: var(--font-medium);
}

.level-error, .level-critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.level-warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.level-info {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.level-debug {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* Anomalies */
.anomalies-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.anomaly-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
}

.anomaly-item.severity-critical {
  border-left: 3px solid var(--color-error-dark);
}

.anomaly-item.severity-high {
  border-left: 3px solid var(--color-error);
}

.anomaly-item.severity-medium {
  border-left: 3px solid var(--color-warning);
}

.anomaly-item.severity-low {
  border-left: 3px solid var(--color-success);
}

.anomaly-header {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.severity-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.65rem;
  font-weight: var(--font-semibold);
}

.severity-badge.severity-critical {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.severity-badge.severity-high {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.severity-badge.severity-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.severity-badge.severity-low {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.anomaly-type {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.anomaly-description {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.anomaly-meta {
  display: flex;
  gap: var(--spacing-4);
  margin-top: var(--spacing-2);
  font-size: 0.7rem;
  color: var(--text-secondary);
}

.anomaly-meta i {
  margin-right: var(--spacing-1);
}

/* Trends */
.trends-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.trend-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
}

.trend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.trend-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.trend-direction {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
}

.direction-increasing {
  color: var(--color-error);
}

.direction-decreasing {
  color: var(--color-success);
}

.direction-stable {
  color: var(--text-muted);
}

.trend-chart {
  height: 50px;
  margin: var(--spacing-2) 0;
}

.sparkline {
  width: 100%;
  height: 100%;
}

.trend-period {
  font-size: 0.7rem;
  color: var(--text-secondary);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-muted);
}

.empty-state i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-2);
}

.empty-state p {
  margin: 0;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 700px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-subtle);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--text-xl);
  cursor: pointer;
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-5);
}

.detail-section {
  margin-bottom: var(--spacing-6);
}

.detail-section h4 {
  margin: 0 0 var(--spacing-3);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.pattern-code {
  background: var(--bg-primary);
  padding: var(--spacing-4);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.detail-item {
  background: var(--bg-secondary);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
}

.detail-item .label {
  display: block;
  font-size: 0.7rem;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.detail-item .value {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.sample-messages {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.sample-msg {
  background: var(--bg-primary);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  word-break: break-all;
}

/* Loading */
.loading-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-16);
}

.loading-spinner {
  text-align: center;
  color: var(--color-primary);
}

.loading-spinner p {
  margin-top: var(--spacing-4);
  color: var(--text-secondary);
}

/* Responsive */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .patterns-panel {
    grid-column: 1;
    grid-row: auto;
  }

  .realtime-summary {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .dashboard-header {
    flex-direction: column;
    gap: var(--spacing-4);
    align-items: flex-start;
  }

  .realtime-summary {
    grid-template-columns: 1fr;
  }
}
</style>
