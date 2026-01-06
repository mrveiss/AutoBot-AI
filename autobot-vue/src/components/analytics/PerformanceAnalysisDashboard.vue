<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Performance Analysis Dashboard - Detect Performance Bottlenecks
  Issue #222: Identifies N+1 queries, unnecessary loops, blocking I/O
-->
<template>
  <div class="performance-dashboard">
    <!-- Header Section -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2>
          <span class="icon">⚡</span>
          Performance Analysis
        </h2>
        <p class="subtitle">Detect anti-patterns and bottlenecks</p>
      </div>
      <div class="header-actions">
        <button class="action-btn secondary" @click="showPatterns = true">
          <span class="btn-icon">⚙️</span>
          Patterns
        </button>
        <button class="action-btn primary" @click="runAnalysis" :disabled="loading || !selectedPath">
          <span v-if="loading" class="spinner"></span>
          <span v-else class="btn-icon">▶️</span>
          {{ loading ? 'Analyzing...' : 'Analyze' }}
        </button>
      </div>
    </div>

    <!-- Path Selection -->
    <div class="path-selection">
      <div class="input-group">
        <label>Path to Analyze</label>
        <input
          v-model="selectedPath"
          type="text"
          placeholder="Enter path (e.g., src/services/)"
          @keydown.enter="runAnalysis"
        />
      </div>
      <div class="quick-paths">
        <button
          v-for="path in quickPaths"
          :key="path"
          class="quick-path-btn"
          :class="{ active: selectedPath === path }"
          @click="selectedPath = path"
        >
          {{ path }}
        </button>
      </div>
    </div>

    <!-- Score and Summary -->
    <div class="score-section" v-if="lastResult">
      <div class="score-ring">
        <svg viewBox="0 0 120 120" class="score-svg">
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke="var(--border-color)"
            stroke-width="12"
          />
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            :stroke="getScoreColor(lastResult.score)"
            stroke-width="12"
            stroke-linecap="round"
            :stroke-dasharray="scoreCircle"
            stroke-dashoffset="82"
            class="score-progress"
          />
          <text x="60" y="55" text-anchor="middle" class="score-value">
            {{ lastResult.score }}
          </text>
          <text x="60" y="72" text-anchor="middle" class="score-label">
            Health
          </text>
        </svg>
      </div>
      <div class="summary-stats">
        <div class="stat-item critical" v-if="lastResult.critical_count > 0">
          <span class="stat-icon">🔴</span>
          <span class="stat-value">{{ lastResult.critical_count }}</span>
          <span class="stat-label">Critical</span>
        </div>
        <div class="stat-item high" v-if="lastResult.high_count > 0">
          <span class="stat-icon">🟠</span>
          <span class="stat-value">{{ lastResult.high_count }}</span>
          <span class="stat-label">High</span>
        </div>
        <div class="stat-item medium" v-if="lastResult.medium_count > 0">
          <span class="stat-icon">🟡</span>
          <span class="stat-value">{{ lastResult.medium_count }}</span>
          <span class="stat-label">Medium</span>
        </div>
        <div class="stat-item low" v-if="lastResult.low_count > 0">
          <span class="stat-icon">🟢</span>
          <span class="stat-value">{{ lastResult.low_count }}</span>
          <span class="stat-label">Low</span>
        </div>
        <div class="stat-item files">
          <span class="stat-icon">📄</span>
          <span class="stat-value">{{ lastResult.files_analyzed }}</span>
          <span class="stat-label">Files</span>
        </div>
        <div class="stat-item duration">
          <span class="stat-icon">⏱️</span>
          <span class="stat-value">{{ lastResult.duration_ms }}ms</span>
          <span class="stat-label">Duration</span>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-grid">
      <!-- Issues by Category -->
      <div class="panel issues-panel">
        <div class="panel-header">
          <h3>Performance Issues</h3>
          <div class="category-tabs">
            <button
              v-for="cat in categories"
              :key="cat.id"
              class="cat-tab"
              :class="{ active: activeCategory === cat.id }"
              @click="activeCategory = cat.id"
            >
              {{ cat.icon }} {{ cat.name }}
              <span class="count">{{ getCategoryCount(cat.id) }}</span>
            </button>
          </div>
        </div>
        <div class="panel-content">
          <div v-if="!lastResult" class="empty-state">
            <span class="empty-icon">⚡</span>
            <p>Run analysis to find performance issues</p>
          </div>
          <div v-else-if="filteredIssues.length === 0" class="empty-state">
            <span class="empty-icon">✨</span>
            <p>No issues in this category</p>
          </div>
          <div v-else class="issues-list">
            <div
              v-for="issue in filteredIssues"
              :key="issue.id"
              class="issue-card"
              :class="issue.impact"
              @click="selectIssue(issue)"
            >
              <div class="issue-header">
                <span class="impact-badge" :class="issue.impact">
                  {{ getImpactIcon(issue.impact) }}
                </span>
                <span class="pattern-code">{{ issue.pattern_id }}</span>
                <span class="issue-name">{{ issue.name }}</span>
              </div>
              <div class="issue-location">
                <span class="file-path">{{ issue.file }}</span>
                <span class="line-number">:{{ issue.line }}</span>
              </div>
              <p class="issue-desc">{{ issue.description }}</p>
              <div class="issue-impact" v-if="issue.estimated_impact">
                <span class="impact-label">Impact:</span>
                <span class="impact-value">{{ issue.estimated_impact }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Issue Detail or Hotspots -->
      <div class="panel detail-panel" v-if="selectedIssue">
        <div class="panel-header">
          <h3>Issue Details</h3>
          <button class="close-btn" @click="selectedIssue = null">×</button>
        </div>
        <div class="panel-content">
          <div class="detail-header">
            <span class="impact-badge large" :class="selectedIssue.impact">
              {{ getImpactIcon(selectedIssue.impact) }}
            </span>
            <div class="detail-title">
              <h4>{{ selectedIssue.name }}</h4>
              <span class="pattern-code">{{ selectedIssue.pattern_id }}</span>
            </div>
          </div>

          <div class="detail-section">
            <label>Location</label>
            <div class="location-info">
              <span class="file-path">{{ selectedIssue.file }}</span>
              <span class="line-info">Line {{ selectedIssue.line }}</span>
            </div>
          </div>

          <div class="detail-section">
            <label>Description</label>
            <p class="description">{{ selectedIssue.description }}</p>
          </div>

          <div class="detail-section" v-if="selectedIssue.code_snippet">
            <label>Code</label>
            <div class="code-snippet">
              <pre><code>{{ selectedIssue.code_snippet }}</code></pre>
            </div>
          </div>

          <div class="detail-section" v-if="selectedIssue.estimated_impact">
            <label>Performance Impact</label>
            <div class="impact-box">
              <span class="impact-icon">📊</span>
              <span class="impact-text">{{ selectedIssue.estimated_impact }}</span>
            </div>
          </div>

          <div class="detail-section">
            <label>Suggestion</label>
            <div class="suggestion-box">
              <span class="suggestion-icon">💡</span>
              <p>{{ selectedIssue.suggestion }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Hotspots Panel -->
      <div class="panel hotspots-panel" v-else>
        <div class="panel-header">
          <h3>Hotspots</h3>
          <span class="subtitle">Files with most issues</span>
        </div>
        <div class="panel-content">
          <div v-if="hotspots.length === 0" class="empty-state small">
            <p>Run analysis to see hotspots</p>
          </div>
          <div v-else class="hotspots-list">
            <div
              v-for="hotspot in hotspots"
              :key="hotspot.file"
              class="hotspot-item"
            >
              <div class="hotspot-info">
                <span class="hotspot-file">{{ getFileName(hotspot.file) }}</span>
                <span class="hotspot-path">{{ hotspot.file }}</span>
              </div>
              <div class="hotspot-stats">
                <span v-if="hotspot.critical_count > 0" class="stat critical">
                  {{ hotspot.critical_count }} critical
                </span>
                <span v-if="hotspot.high_count > 0" class="stat high">
                  {{ hotspot.high_count }} high
                </span>
                <span class="stat total">{{ hotspot.issue_count }} total</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Category Distribution -->
    <div class="panel distribution-panel">
      <div class="panel-header">
        <h3>Issue Distribution</h3>
      </div>
      <div class="panel-content">
        <div class="category-bars">
          <div
            v-for="cat in categoryStats"
            :key="cat.category"
            class="category-bar-item"
          >
            <div class="bar-label">
              <span class="bar-icon">{{ getCategoryIcon(cat.category) }}</span>
              <span class="bar-name">{{ cat.name }}</span>
            </div>
            <div class="bar-container">
              <div
                class="bar-fill critical"
                :style="{ width: getBarWidth(cat.critical, cat.total) }"
              ></div>
              <div
                class="bar-fill high"
                :style="{ width: getBarWidth(cat.high, cat.total) }"
              ></div>
              <div
                class="bar-fill medium"
                :style="{ width: getBarWidth(cat.medium, cat.total) }"
              ></div>
              <div
                class="bar-fill low"
                :style="{ width: getBarWidth(cat.low, cat.total) }"
              ></div>
            </div>
            <span class="bar-value">{{ cat.total }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Patterns Modal -->
    <div v-if="showPatterns" class="modal-overlay" @click.self="showPatterns = false">
      <div class="modal patterns-modal">
        <div class="modal-header">
          <h3>Performance Patterns</h3>
          <button class="close-btn" @click="showPatterns = false">×</button>
        </div>
        <div class="modal-content">
          <div
            v-for="cat in patternCategories"
            :key="cat"
            class="pattern-category"
          >
            <h4>{{ getCategoryIcon(cat) }} {{ getCategoryName(cat) }}</h4>
            <div class="pattern-list">
              <div
                v-for="pattern in getPatternsForCategory(cat)"
                :key="pattern.id"
                class="pattern-item"
                :class="{ enabled: pattern.enabled }"
              >
                <label class="pattern-toggle">
                  <input
                    type="checkbox"
                    :checked="pattern.enabled"
                    @change="togglePattern(pattern)"
                  />
                </label>
                <div class="pattern-info">
                  <span class="pattern-id">{{ pattern.id }}</span>
                  <span class="pattern-name">{{ pattern.name }}</span>
                </div>
                <span class="impact-badge small" :class="pattern.impact">
                  {{ pattern.impact }}
                </span>
              </div>
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

const logger = createLogger('PerformanceAnalysisDashboard')

// Issue #701: Type for API response with data property
interface ApiDataResponse {
  data?: any
  total_issues?: number
  issues?: PerformanceIssue[]
  [key: string]: any
}

// Types
interface PerformanceIssue {
  id: string
  pattern_id: string
  name: string
  category: string
  impact: 'critical' | 'high' | 'medium' | 'low'
  file: string
  line: number
  description: string
  suggestion: string
  code_snippet?: string
  estimated_impact?: string
}

interface AnalysisResult {
  total_issues: number
  critical_count: number
  high_count: number
  medium_count: number
  low_count: number
  issues: PerformanceIssue[]
  files_analyzed: number
  duration_ms: number
  timestamp: string
  score: number
}

interface Pattern {
  id: string
  name: string
  category: string
  impact: string
  enabled: boolean
}

interface Hotspot {
  file: string
  issue_count: number
  critical_count: number
  high_count: number
}

// State
const { showToast } = useToast()
const loading = ref(false)
const selectedPath = ref('')
const lastResult = ref<AnalysisResult | null>(null)
const selectedIssue = ref<PerformanceIssue | null>(null)
const activeCategory = ref('all')
const patterns = ref<Pattern[]>([])
const hotspots = ref<Hotspot[]>([])
const showPatterns = ref(false)

const quickPaths = ['src/', 'backend/', 'backend/api/', 'backend/services/']

const categories = [
  { id: 'all', name: 'All', icon: '📋' },
  { id: 'query', name: 'Query', icon: '🗃️' },
  { id: 'loop', name: 'Loop', icon: '🔄' },
  { id: 'async', name: 'Async', icon: '⏳' },
  { id: 'cache', name: 'Cache', icon: '💾' },
  { id: 'memory', name: 'Memory', icon: '🧠' },
  { id: 'io', name: 'I/O', icon: '📁' }
]

// Computed
const filteredIssues = computed(() => {
  if (!lastResult.value) return []
  if (activeCategory.value === 'all') return lastResult.value.issues
  return lastResult.value.issues.filter(i => i.category === activeCategory.value)
})

const scoreCircle = computed(() => {
  if (!lastResult.value) return '0 327'
  const circumference = 2 * Math.PI * 52
  const progress = (lastResult.value.score / 100) * circumference
  return `${progress} ${circumference}`
})

const categoryStats = computed(() => {
  if (!lastResult.value) return []

  const stats: Record<string, { critical: number; high: number; medium: number; low: number; total: number }> = {}

  lastResult.value.issues.forEach(issue => {
    if (!stats[issue.category]) {
      stats[issue.category] = { critical: 0, high: 0, medium: 0, low: 0, total: 0 }
    }
    stats[issue.category][issue.impact]++
    stats[issue.category].total++
  })

  return Object.entries(stats).map(([category, counts]) => ({
    category,
    name: getCategoryName(category),
    ...counts
  }))
})

const patternCategories = computed(() => {
  return [...new Set(patterns.value.map(p => p.category))]
})

// Methods
function getScoreColor(score: number): string {
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#f59e0b'
  if (score >= 40) return '#f97316'
  return '#ef4444'
}

function getImpactIcon(impact: string): string {
  const icons: Record<string, string> = {
    critical: '🔴',
    high: '🟠',
    medium: '🟡',
    low: '🟢'
  }
  return icons[impact] || '⚪'
}

function getCategoryIcon(category: string): string {
  const cat = categories.find(c => c.id === category)
  return cat?.icon || '📋'
}

function getCategoryName(category: string): string {
  const cat = categories.find(c => c.id === category)
  return cat?.name || category.charAt(0).toUpperCase() + category.slice(1)
}

function getCategoryCount(categoryId: string): number {
  if (!lastResult.value) return 0
  if (categoryId === 'all') return lastResult.value.issues.length
  return lastResult.value.issues.filter(i => i.category === categoryId).length
}

function getFileName(path: string): string {
  return path.split('/').pop() || path
}

function getBarWidth(count: number, total: number): string {
  if (total === 0) return '0%'
  return `${(count / total) * 100}%`
}

function selectIssue(issue: PerformanceIssue) {
  selectedIssue.value = issue
}

function getPatternsForCategory(category: string): Pattern[] {
  return patterns.value.filter(p => p.category === category)
}

async function runAnalysis() {
  if (!selectedPath.value) {
    showToast('Please enter a path to analyze', 'warning')
    return
  }

  loading.value = true
  try {
    // Issue #701: Fixed api.get call to use params option and type assertion
    const response = await api.get<ApiDataResponse>('/api/performance/analyze', {
      params: { path: selectedPath.value }
    })
    // Issue #701: Response is returned directly, handle both response structures
    lastResult.value = (response as ApiDataResponse).data || response as unknown as AnalysisResult

    const totalIssues = (response as ApiDataResponse).total_issues ?? (response as ApiDataResponse).data?.total_issues ?? 0
    if (totalIssues === 0) {
      showToast('No performance issues found!', 'success')
    } else {
      showToast(`Found ${totalIssues} issues`, 'info')
    }

    await loadHotspots()
  } catch (error) {
    logger.error('Failed to run analysis:', error)
    showToast('Failed to run performance analysis', 'error')
  } finally {
    loading.value = false
  }
}

async function loadPatterns() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<Pattern[] | ApiDataResponse>('/api/performance/patterns')
    // Issue #701: Response could be array directly or wrapped in data
    patterns.value = Array.isArray(response) ? response : ((response as ApiDataResponse).data || [])
  } catch (error) {
    logger.warn('Failed to load patterns:', error)
    patterns.value = []
  }
}

async function loadHotspots() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<Hotspot[] | ApiDataResponse>('/api/performance/hotspots')
    // Issue #701: Response could be array directly or wrapped in data
    hotspots.value = Array.isArray(response) ? response : ((response as ApiDataResponse).data || [])
  } catch (error) {
    logger.warn('Failed to load hotspots:', error)
    hotspots.value = []
  }
}

async function togglePattern(pattern: Pattern) {
  const newState = !pattern.enabled
  try {
    // Issue #701: Fixed api.post call - data should be second arg, options third
    await api.post(`/api/performance/patterns/${pattern.id}/toggle`, { enabled: newState })
    pattern.enabled = newState
  } catch (error) {
    logger.warn('Failed to toggle pattern:', error)
    pattern.enabled = !newState
  }
}

onMounted(() => {
  loadPatterns()
})
</script>

<style scoped>
.performance-dashboard {
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

/* Path Selection */
.path-selection {
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.input-group label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.input-group input {
  padding: 0.625rem 0.875rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.input-group input:focus {
  outline: none;
  border-color: var(--accent-color);
}

.quick-paths {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.quick-path-btn {
  padding: 0.375rem 0.75rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--text-secondary);
  cursor: pointer;
}

.quick-path-btn.active {
  background: var(--accent-color);
  color: white;
  border-color: var(--accent-color);
}

/* Score Section */
.score-section {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 1.5rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.score-ring {
  flex-shrink: 0;
}

.score-svg {
  width: 100px;
  height: 100px;
}

.score-progress {
  transform: rotate(-90deg);
  transform-origin: center;
  transition: stroke-dasharray 0.5s ease;
}

.score-value {
  font-size: 1.75rem;
  font-weight: 700;
  fill: var(--text-primary);
}

.score-label {
  font-size: 0.625rem;
  fill: var(--text-secondary);
  text-transform: uppercase;
}

.summary-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.stat-icon {
  font-size: 1.25rem;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.6875rem;
  color: var(--text-secondary);
  text-transform: uppercase;
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

.close-btn {
  background: none;
  border: none;
  font-size: 1.25rem;
  color: var(--text-secondary);
  cursor: pointer;
}

/* Category Tabs */
.category-tabs {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.cat-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: none;
  border-radius: 4px;
  font-size: 0.6875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.cat-tab.active {
  background: var(--accent-color);
  color: white;
}

.cat-tab .count {
  background: rgba(0,0,0,0.2);
  padding: 0.125rem 0.25rem;
  border-radius: 4px;
}

/* Issues List */
.issues-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.issue-card {
  padding: 0.875rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border-left: 3px solid;
  cursor: pointer;
  transition: all 0.2s;
}

.issue-card:hover {
  background: var(--bg-quaternary);
}

.issue-card.critical { border-left-color: #ef4444; }
.issue-card.high { border-left-color: #f59e0b; }
.issue-card.medium { border-left-color: #eab308; }
.issue-card.low { border-left-color: #22c55e; }

.issue-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.impact-badge {
  font-size: 0.875rem;
}

.impact-badge.large {
  font-size: 1.5rem;
}

.impact-badge.small {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  background: var(--bg-quaternary);
}

.pattern-code {
  font-size: 0.6875rem;
  font-weight: 600;
  font-family: monospace;
  color: var(--accent-color);
  background: var(--bg-quaternary);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.issue-name {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.issue-location {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.issue-desc {
  margin: 0 0 0.5rem 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.issue-impact {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
}

.impact-label {
  color: var(--text-tertiary);
}

.impact-value {
  font-weight: 600;
  color: var(--text-primary);
}

/* Detail Panel */
.detail-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.detail-title h4 {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.detail-section {
  margin-bottom: 1rem;
}

.detail-section label {
  display: block;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  margin-bottom: 0.5rem;
}

.location-info {
  font-family: monospace;
  font-size: 0.875rem;
}

.line-info {
  color: var(--text-secondary);
  margin-left: 0.5rem;
}

.description {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.code-snippet {
  background: var(--bg-tertiary);
  border-radius: 6px;
  overflow: hidden;
}

.code-snippet pre {
  margin: 0;
  padding: 0.875rem;
  font-size: 0.75rem;
  overflow-x: auto;
}

.impact-box {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: rgba(245, 158, 11, 0.1);
  border-radius: 6px;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.impact-icon {
  font-size: 1.25rem;
}

.impact-text {
  font-weight: 600;
  color: var(--text-primary);
}

.suggestion-box {
  display: flex;
  gap: 0.75rem;
  padding: 0.875rem;
  background: rgba(16, 185, 129, 0.1);
  border-radius: 6px;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.suggestion-icon {
  font-size: 1.25rem;
}

.suggestion-box p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.4;
}

/* Hotspots Panel */
.hotspots-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.hotspot-item {
  padding: 0.75rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.hotspot-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}

.hotspot-file {
  font-weight: 600;
  color: var(--text-primary);
}

.hotspot-path {
  font-size: 0.6875rem;
  font-family: monospace;
  color: var(--text-tertiary);
}

.hotspot-stats {
  display: flex;
  gap: 0.5rem;
}

.hotspot-stats .stat {
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.625rem;
  font-weight: 600;
}

.hotspot-stats .stat.critical {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.hotspot-stats .stat.high {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.hotspot-stats .stat.total {
  background: var(--bg-quaternary);
  color: var(--text-secondary);
}

/* Distribution Panel */
.distribution-panel {
  grid-column: 1 / -1;
}

.category-bars {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.category-bar-item {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.bar-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100px;
}

.bar-icon {
  font-size: 1rem;
}

.bar-name {
  font-size: 0.8125rem;
  color: var(--text-primary);
}

.bar-container {
  flex: 1;
  height: 24px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
}

.bar-fill {
  height: 100%;
  transition: width 0.3s;
}

.bar-fill.critical { background: #ef4444; }
.bar-fill.high { background: #f59e0b; }
.bar-fill.medium { background: #eab308; }
.bar-fill.low { background: #22c55e; }

.bar-value {
  width: 40px;
  text-align: right;
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
  padding: 1.5rem;
}

.empty-icon {
  font-size: 2.5rem;
  margin-bottom: 0.75rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg-secondary);
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-color);
}

.modal-content {
  padding: 1.25rem;
  overflow-y: auto;
}

.pattern-category {
  margin-bottom: 1.5rem;
}

.pattern-category h4 {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.pattern-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.pattern-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  opacity: 0.6;
}

.pattern-item.enabled {
  opacity: 1;
}

.pattern-toggle input {
  width: 16px;
  height: 16px;
}

.pattern-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.pattern-id {
  font-size: 0.625rem;
  font-family: monospace;
  color: var(--text-tertiary);
}

.pattern-name {
  font-size: 0.8125rem;
  color: var(--text-primary);
}

/* Responsive */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .score-section {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .summary-stats {
    justify-content: center;
  }
}
</style>
