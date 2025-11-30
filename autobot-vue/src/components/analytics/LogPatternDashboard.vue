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
    const response = await fetch(
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
    const response = await fetch('/api/log-patterns/realtime')
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
  } catch {
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
    case 'increasing': return '#ef4444'
    case 'decreasing': return '#22c55e'
    default: return '#6b7280'
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
  padding: 1.5rem;
  background: #0f0f1a;
  min-height: 100vh;
  color: #e5e7eb;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #2a2a3e;
}

.header-content h2 {
  margin: 0;
  font-size: 1.5rem;
  color: #f9fafb;
}

.header-content h2 i {
  color: #8b5cf6;
  margin-right: 0.5rem;
}

.subtitle {
  margin: 0.25rem 0 0;
  color: #9ca3af;
  font-size: 0.875rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.time-select {
  padding: 0.5rem 1rem;
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  color: #e5e7eb;
  cursor: pointer;
}

.analyze-btn {
  padding: 0.5rem 1.25rem;
  background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
  border: none;
  border-radius: 6px;
  color: white;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.analyze-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4);
}

.analyze-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Realtime Summary */
.realtime-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-card {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 1rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.summary-card.has-errors {
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.summary-card.has-anomalies {
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(139, 92, 246, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  color: #8b5cf6;
}

.summary-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #f9fafb;
}

.summary-label {
  font-size: 0.75rem;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

/* Panels */
.panel {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
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
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #2a2a3e;
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #f9fafb;
}

.panel-header h3 i {
  margin-right: 0.5rem;
  color: #8b5cf6;
}

.pattern-count {
  font-size: 0.75rem;
  color: #9ca3af;
  background: #2a2a3e;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
}

.panel-content {
  padding: 1rem;
  max-height: 600px;
  overflow-y: auto;
}

/* Pattern Filters */
.pattern-filters {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.filter-btn {
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  color: #9ca3af;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: #8b5cf6;
  color: #8b5cf6;
}

.filter-btn.active {
  background: #8b5cf6;
  border-color: #8b5cf6;
  color: white;
}

/* Pattern Items */
.patterns-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.pattern-item {
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.pattern-item:hover {
  border-color: #8b5cf6;
  transform: translateX(2px);
}

.pattern-item.is-error {
  border-left: 3px solid #ef4444;
}

.pattern-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.pattern-id {
  font-family: monospace;
  font-size: 0.75rem;
  color: #8b5cf6;
}

.occurrence-badge {
  background: #2a2a3e;
  padding: 0.125rem 0.5rem;
  border-radius: 10px;
  font-size: 0.7rem;
  color: #d1d5db;
}

.pattern-template {
  font-family: monospace;
  font-size: 0.8rem;
  color: #d1d5db;
  background: #0f0f1a;
  padding: 0.5rem;
  border-radius: 4px;
  margin-bottom: 0.5rem;
  word-break: break-all;
}

.pattern-meta {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: 0.7rem;
}

.meta-item {
  color: #9ca3af;
}

.meta-item i {
  margin-right: 0.25rem;
}

.level-badge {
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 500;
}

.level-error, .level-critical {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.level-warning {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.level-info {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.level-debug {
  background: rgba(107, 114, 128, 0.2);
  color: #9ca3af;
}

/* Anomalies */
.anomalies-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.anomaly-item {
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
}

.anomaly-item.severity-critical {
  border-left: 3px solid #dc2626;
}

.anomaly-item.severity-high {
  border-left: 3px solid #ef4444;
}

.anomaly-item.severity-medium {
  border-left: 3px solid #f59e0b;
}

.anomaly-item.severity-low {
  border-left: 3px solid #22c55e;
}

.anomaly-header {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.5rem;
}

.severity-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
}

.severity-badge.severity-critical {
  background: rgba(220, 38, 38, 0.2);
  color: #dc2626;
}

.severity-badge.severity-high {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.severity-badge.severity-medium {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.severity-badge.severity-low {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.anomaly-type {
  font-size: 0.75rem;
  color: #9ca3af;
}

.anomaly-description {
  margin: 0;
  font-size: 0.85rem;
  color: #d1d5db;
}

.anomaly-meta {
  display: flex;
  gap: 1rem;
  margin-top: 0.5rem;
  font-size: 0.7rem;
  color: #9ca3af;
}

.anomaly-meta i {
  margin-right: 0.25rem;
}

/* Trends */
.trends-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.trend-item {
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
}

.trend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.trend-name {
  font-weight: 500;
  color: #f9fafb;
}

.trend-direction {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-weight: 600;
  font-size: 0.875rem;
}

.direction-increasing {
  color: #ef4444;
}

.direction-decreasing {
  color: #22c55e;
}

.direction-stable {
  color: #6b7280;
}

.trend-chart {
  height: 50px;
  margin: 0.5rem 0;
}

.sparkline {
  width: 100%;
  height: 100%;
}

.trend-period {
  font-size: 0.7rem;
  color: #9ca3af;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}

.empty-state i {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.empty-state p {
  margin: 0;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  width: 90%;
  max-width: 700px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #2a2a3e;
}

.modal-header h3 {
  margin: 0;
  color: #f9fafb;
}

.close-btn {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 1.25rem;
  cursor: pointer;
}

.close-btn:hover {
  color: #f9fafb;
}

.modal-body {
  padding: 1.25rem;
}

.detail-section {
  margin-bottom: 1.5rem;
}

.detail-section h4 {
  margin: 0 0 0.75rem;
  color: #f9fafb;
  font-size: 0.875rem;
}

.pattern-code {
  background: #0f0f1a;
  padding: 1rem;
  border-radius: 6px;
  font-family: monospace;
  font-size: 0.8rem;
  color: #d1d5db;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.detail-item {
  background: #111827;
  padding: 0.75rem;
  border-radius: 6px;
}

.detail-item .label {
  display: block;
  font-size: 0.7rem;
  color: #9ca3af;
  margin-bottom: 0.25rem;
}

.detail-item .value {
  font-weight: 600;
  color: #f9fafb;
}

.sample-messages {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sample-msg {
  background: #0f0f1a;
  padding: 0.5rem;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.75rem;
  color: #d1d5db;
  word-break: break-all;
}

/* Loading */
.loading-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4rem;
}

.loading-spinner {
  text-align: center;
  color: #8b5cf6;
}

.loading-spinner p {
  margin-top: 1rem;
  color: #9ca3af;
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
    gap: 1rem;
    align-items: flex-start;
  }

  .realtime-summary {
    grid-template-columns: 1fr;
  }
}
</style>
