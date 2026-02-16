<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Code Review Dashboard - AI-Powered Code Review Automation
  Issue #225: Automated code review with pattern-based analysis
-->
<template>
  <div class="code-review-dashboard">
    <!-- Header Section -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2>
          <span class="icon">🔍</span>
          AI Code Review
        </h2>
        <p class="subtitle">Automated code analysis and review suggestions</p>
      </div>
      <div class="header-actions">
        <button class="action-btn secondary" @click="loadPatterns" :disabled="loading">
          <span class="btn-icon">⚙️</span>
          Patterns
        </button>
        <button class="action-btn primary" @click="runAnalysis" :disabled="loading || !selectedPath">
          <span v-if="loading" class="spinner"></span>
          <span v-else class="btn-icon">▶️</span>
          {{ loading ? 'Analyzing...' : 'Run Review' }}
        </button>
      </div>
    </div>

    <!-- Path Selection -->
    <div class="path-selection">
      <div class="input-group">
        <label>File or Directory Path</label>
        <input
          v-model="selectedPath"
          type="text"
          placeholder="Enter path to analyze (e.g., src/components/)"
          @keydown.enter="runAnalysis"
        />
      </div>
      <div class="input-group">
        <label>Languages</label>
        <div class="language-chips">
          <span
            v-for="lang in availableLanguages"
            :key="lang"
            class="chip"
            :class="{ active: selectedLanguages.includes(lang) }"
            @click="toggleLanguage(lang)"
          >
            {{ lang }}
          </span>
        </div>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="summary-cards">
      <div class="summary-card critical">
        <div class="card-icon">🔴</div>
        <div class="card-content">
          <span class="card-value">{{ summary.critical }}</span>
          <span class="card-label">Critical</span>
        </div>
      </div>
      <div class="summary-card high">
        <div class="card-icon">🟠</div>
        <div class="card-content">
          <span class="card-value">{{ summary.high }}</span>
          <span class="card-label">High</span>
        </div>
      </div>
      <div class="summary-card medium">
        <div class="card-icon">🟡</div>
        <div class="card-content">
          <span class="card-value">{{ summary.medium }}</span>
          <span class="card-label">Medium</span>
        </div>
      </div>
      <div class="summary-card low">
        <div class="card-icon">🟢</div>
        <div class="card-content">
          <span class="card-value">{{ summary.low }}</span>
          <span class="card-label">Low</span>
        </div>
      </div>
      <div class="summary-card files">
        <div class="card-icon">📄</div>
        <div class="card-content">
          <span class="card-value">{{ summary.filesAnalyzed }}</span>
          <span class="card-label">Files</span>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid">
      <!-- Issues List -->
      <div class="panel issues-panel">
        <div class="panel-header">
          <h3>Review Issues</h3>
          <div class="filter-tabs">
            <button
              v-for="category in categories"
              :key="category.id"
              class="filter-tab"
              :class="{ active: activeCategory === category.id }"
              @click="activeCategory = category.id"
            >
              {{ category.icon }} {{ category.name }}
              <span class="count">{{ getCategoryCount(category.id) }}</span>
            </button>
          </div>
        </div>
        <div class="panel-content">
          <div v-if="filteredIssues.length === 0" class="empty-state">
            <span class="empty-icon">✨</span>
            <p v-if="!hasAnalyzed">Run a review to find issues</p>
            <p v-else>No issues found in this category</p>
          </div>
          <div v-else class="issues-list">
            <div
              v-for="issue in filteredIssues"
              :key="issue.id"
              class="issue-card"
              :class="issue.severity"
              @click="selectIssue(issue)"
            >
              <div class="issue-header">
                <span class="severity-badge" :class="issue.severity">
                  {{ getSeverityIcon(issue.severity) }}
                </span>
                <span class="issue-code">{{ issue.code }}</span>
                <span class="issue-name">{{ issue.name }}</span>
              </div>
              <div class="issue-location">
                <span class="file-path">{{ issue.file }}</span>
                <span class="line-number">Line {{ issue.line }}</span>
              </div>
              <p class="issue-message">{{ issue.message }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Issue Detail -->
      <div class="panel detail-panel" v-if="selectedIssue">
        <div class="panel-header">
          <h3>Issue Details</h3>
          <button class="close-btn" @click="selectedIssue = null">×</button>
        </div>
        <div class="panel-content">
          <div class="detail-section">
            <div class="detail-header">
              <span class="severity-badge large" :class="selectedIssue.severity">
                {{ getSeverityIcon(selectedIssue.severity) }}
              </span>
              <div class="detail-title">
                <h4>{{ selectedIssue.name }}</h4>
                <span class="issue-code">{{ selectedIssue.code }}</span>
              </div>
            </div>
          </div>

          <div class="detail-section">
            <label>Location</label>
            <div class="location-info">
              <span class="file-path">{{ selectedIssue.file }}</span>
              <span class="line-info">Line {{ selectedIssue.line }}, Column {{ selectedIssue.column }}</span>
            </div>
          </div>

          <div class="detail-section">
            <label>Description</label>
            <p class="description">{{ selectedIssue.message }}</p>
          </div>

          <div class="detail-section" v-if="selectedIssue.suggestion">
            <label>Suggestion</label>
            <div class="suggestion-box">
              <span class="suggestion-icon">💡</span>
              <p>{{ selectedIssue.suggestion }}</p>
            </div>
          </div>

          <div class="detail-section" v-if="selectedIssue.snippet">
            <label>Code Snippet</label>
            <div class="code-snippet">
              <pre><code>{{ selectedIssue.snippet }}</code></pre>
            </div>
          </div>

          <div class="detail-actions">
            <button class="action-btn secondary" @click="markResolved(selectedIssue)">
              Mark Resolved
            </button>
            <button class="action-btn secondary" @click="markFalsePositive(selectedIssue)">
              False Positive
            </button>
          </div>
        </div>
      </div>

      <!-- Pattern Categories Chart -->
      <div class="panel chart-panel" v-if="!selectedIssue">
        <div class="panel-header">
          <h3>Issue Distribution</h3>
        </div>
        <div class="panel-content">
          <div class="donut-chart-container">
            <svg viewBox="0 0 200 200" class="donut-chart">
              <!-- Background circle -->
              <circle
                cx="100"
                cy="100"
                r="70"
                fill="none"
                stroke="var(--border-color)"
                stroke-width="20"
              />
              <!-- Category segments -->
              <circle
                v-for="(segment, index) in chartSegments"
                :key="segment.category"
                cx="100"
                cy="100"
                r="70"
                fill="none"
                :stroke="segment.color"
                stroke-width="20"
                :stroke-dasharray="segment.dashArray"
                :stroke-dashoffset="segment.offset"
                class="segment"
                :style="{ animationDelay: `${index * 100}ms` }"
              />
              <!-- Center text -->
              <text x="100" y="95" text-anchor="middle" class="center-value">
                {{ totalIssues }}
              </text>
              <text x="100" y="115" text-anchor="middle" class="center-label">
                Total Issues
              </text>
            </svg>
          </div>
          <div class="chart-legend">
            <div
              v-for="item in legendItems"
              :key="item.category"
              class="legend-item"
            >
              <span class="legend-color" :style="{ background: item.color }"></span>
              <span class="legend-label">{{ item.label }}</span>
              <span class="legend-value">{{ item.count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Reviews -->
    <div class="panel history-panel">
      <div class="panel-header">
        <h3>Review History</h3>
        <button class="action-btn text" @click="loadHistory">
          Refresh
        </button>
      </div>
      <div class="panel-content">
        <div class="history-list">
          <div
            v-for="review in reviewHistory"
            :key="review.id"
            class="history-item"
            @click="loadReview(review.id)"
          >
            <div class="history-info">
              <span class="history-path">{{ review.path }}</span>
              <span class="history-date">{{ formatDate(review.timestamp) }}</span>
            </div>
            <div class="history-stats">
              <span class="stat critical" v-if="review.critical > 0">
                {{ review.critical }} critical
              </span>
              <span class="stat high" v-if="review.high > 0">
                {{ review.high }} high
              </span>
              <span class="stat total">
                {{ review.total }} issues
              </span>
            </div>
          </div>
          <div v-if="reviewHistory.length === 0" class="empty-state small">
            <p>No previous reviews</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Patterns Modal -->
    <div v-if="showPatterns" class="modal-overlay" @click.self="showPatterns = false">
      <div class="modal patterns-modal">
        <div class="modal-header">
          <h3>Review Patterns</h3>
          <button class="close-btn" @click="showPatterns = false">×</button>
        </div>
        <div class="modal-content">
          <div
            v-for="(patterns, category) in patternsByCategory"
            :key="category"
            class="pattern-category"
          >
            <h4>{{ getCategoryName(category) }}</h4>
            <div class="pattern-list">
              <div
                v-for="pattern in patterns"
                :key="pattern.id"
                class="pattern-item"
                :class="{ enabled: pattern.enabled }"
              >
                <div class="pattern-toggle">
                  <input
                    type="checkbox"
                    :checked="pattern.enabled"
                    @change="togglePattern(pattern)"
                  />
                </div>
                <div class="pattern-info">
                  <span class="pattern-code">{{ pattern.id }}</span>
                  <span class="pattern-name">{{ pattern.name }}</span>
                  <span class="severity-badge small" :class="pattern.severity">
                    {{ pattern.severity }}
                  </span>
                </div>
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

const logger = createLogger('CodeReviewDashboard')

// Issue #701: Type for API response with data property
interface ApiDataResponse {
  data?: any
  issues?: ReviewIssue[]
  reviews?: ReviewHistory[]
  patterns?: Pattern[]
  path?: string
  [key: string]: any
}

// Types
interface ReviewIssue {
  id: string
  code: string
  name: string
  category: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  file: string
  line: number
  column: number
  message: string
  suggestion?: string
  snippet?: string
}

interface ReviewHistory {
  id: string
  path: string
  timestamp: string
  total: number
  critical: number
  high: number
  medium: number
  low: number
}

interface Pattern {
  id: string
  name: string
  category: string
  severity: string
  enabled: boolean
}

// State
const { showToast } = useToast()
const loading = ref(false)
const hasAnalyzed = ref(false)
const selectedPath = ref('')
const selectedLanguages = ref<string[]>(['python', 'typescript', 'javascript'])
const availableLanguages = ['python', 'typescript', 'javascript', 'vue', 'html', 'css']
const issues = ref<ReviewIssue[]>([])
const selectedIssue = ref<ReviewIssue | null>(null)
const activeCategory = ref('all')
const reviewHistory = ref<ReviewHistory[]>([])
const showPatterns = ref(false)
const patterns = ref<Pattern[]>([])

// Categories
const categories = [
  { id: 'all', name: 'All', icon: '📋' },
  { id: 'security', name: 'Security', icon: '🔒' },
  { id: 'performance', name: 'Performance', icon: '⚡' },
  { id: 'bugs', name: 'Bugs', icon: '🐛' },
  { id: 'style', name: 'Style', icon: '🎨' },
  { id: 'documentation', name: 'Docs', icon: '📝' },
]

// Computed
const summary = computed(() => {
  const result = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    filesAnalyzed: new Set<string>()
  }

  issues.value.forEach(issue => {
    result[issue.severity]++
    result.filesAnalyzed.add(issue.file)
  })

  return {
    ...result,
    filesAnalyzed: result.filesAnalyzed.size
  }
})

const filteredIssues = computed(() => {
  if (activeCategory.value === 'all') return issues.value
  return issues.value.filter(i => i.category === activeCategory.value)
})

const totalIssues = computed(() => issues.value.length)

const chartSegments = computed(() => {
  const categoryColors: Record<string, string> = {
    security: '#ef4444',
    performance: '#f59e0b',
    bugs: '#8b5cf6',
    style: '#3b82f6',
    documentation: '#10b981'
  }

  const counts: Record<string, number> = {}
  issues.value.forEach(issue => {
    counts[issue.category] = (counts[issue.category] || 0) + 1
  })

  const total = issues.value.length || 1
  const circumference = 2 * Math.PI * 70
  let currentOffset = circumference / 4 // Start from top

  return Object.entries(counts).map(([category, count]) => {
    const percentage = count / total
    const dashLength = circumference * percentage
    const segment = {
      category,
      color: categoryColors[category] || '#6b7280',
      dashArray: `${dashLength} ${circumference - dashLength}`,
      offset: currentOffset
    }
    currentOffset -= dashLength
    return segment
  })
})

const legendItems = computed(() => {
  const categoryColors: Record<string, string> = {
    security: '#ef4444',
    performance: '#f59e0b',
    bugs: '#8b5cf6',
    style: '#3b82f6',
    documentation: '#10b981'
  }

  const counts: Record<string, number> = {}
  issues.value.forEach(issue => {
    counts[issue.category] = (counts[issue.category] || 0) + 1
  })

  return Object.entries(counts).map(([category, count]) => ({
    category,
    label: getCategoryName(category),
    color: categoryColors[category] || '#6b7280',
    count
  }))
})

const patternsByCategory = computed(() => {
  const grouped: Record<string, Pattern[]> = {}
  patterns.value.forEach(pattern => {
    if (!grouped[pattern.category]) {
      grouped[pattern.category] = []
    }
    grouped[pattern.category].push(pattern)
  })
  return grouped
})

// Methods
function toggleLanguage(lang: string) {
  const idx = selectedLanguages.value.indexOf(lang)
  if (idx >= 0) {
    selectedLanguages.value.splice(idx, 1)
  } else {
    selectedLanguages.value.push(lang)
  }
}

function getCategoryCount(categoryId: string): number {
  if (categoryId === 'all') return issues.value.length
  return issues.value.filter(i => i.category === categoryId).length
}

function getCategoryName(category: string): string {
  const cat = categories.find(c => c.id === category)
  return cat?.name || category.charAt(0).toUpperCase() + category.slice(1)
}

function getSeverityIcon(severity: string): string {
  const icons: Record<string, string> = {
    critical: '🔴',
    high: '🟠',
    medium: '🟡',
    low: '🟢'
  }
  return icons[severity] || '⚪'
}

function selectIssue(issue: ReviewIssue) {
  selectedIssue.value = issue
}

function formatDate(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return 'Just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return date.toLocaleDateString()
}

async function runAnalysis() {
  if (!selectedPath.value) {
    showToast('Please enter a path to analyze', 'warning')
    return
  }

  loading.value = true
  hasAnalyzed.value = false

  try {
    // Issue #701: Fixed api.get call to use params option and type assertion
    const response = await api.get<ApiDataResponse>('/api/code-review/analyze', {
      params: {
        path: selectedPath.value,
        languages: selectedLanguages.value.join(',')
      }
    })

    // Issue #701: Response is returned directly, access .issues or .data.issues
    issues.value = (response as ApiDataResponse).issues || (response as ApiDataResponse).data?.issues || []
    hasAnalyzed.value = true

    if (issues.value.length === 0) {
      showToast('No issues found! Code looks good.', 'success')
    } else {
      showToast(`Found ${issues.value.length} issues`, 'info')
    }

    await loadHistory()
  } catch (error: unknown) {
    logger.error('Analysis failed:', error)
    issues.value = []
    hasAnalyzed.value = false
    showToast('Analysis failed - please check backend connection', 'error')
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<ApiDataResponse>('/api/code-review/history')
    reviewHistory.value = (response as ApiDataResponse).reviews || (response as ApiDataResponse).data?.reviews || []
  } catch (error) {
    logger.warn('Failed to load review history:', error)
    reviewHistory.value = []
  }
}

async function loadReview(reviewId: string) {
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<ApiDataResponse>(`/api/code-review/review/${reviewId}`)
    issues.value = (response as ApiDataResponse).issues || (response as ApiDataResponse).data?.issues || []
    selectedPath.value = (response as ApiDataResponse).path || (response as ApiDataResponse).data?.path || ''
    hasAnalyzed.value = true
  } catch (error) {
    logger.error('Failed to load review:', error)
    showToast('Failed to load review', 'error')
  }
}

async function loadPatterns() {
  showPatterns.value = true
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<ApiDataResponse>('/api/code-review/patterns')
    patterns.value = (response as ApiDataResponse).patterns || (response as ApiDataResponse).data?.patterns || []
    applyPatternPrefs()
  } catch (error) {
    logger.warn('Failed to load patterns:', error)
    patterns.value = []
  }
}

const PATTERN_PREFS_KEY = 'autobot-code-review-pattern-prefs';

function savePatternPrefs(): void {
  const disabled = patterns.value
    .filter(p => !p.enabled)
    .map(p => p.id);
  localStorage.setItem(PATTERN_PREFS_KEY, JSON.stringify(disabled));
}

async function applyPatternPrefs(): Promise<void> {
  // Issue #638: Load preferences from backend first, fallback to localStorage
  try {
    const response = await api.get<ApiDataResponse>('/api/analytics/code-review/patterns/preferences');
    const prefs = (response as ApiDataResponse).patterns || (response as ApiDataResponse).data?.patterns;

    if (prefs) {
      // Apply backend preferences
      for (const p of patterns.value) {
        if (prefs[p.id]) {
          p.enabled = prefs[p.id].enabled;
        }
      }
      logger.debug('Loaded pattern preferences from backend');
      return;
    }
  } catch (error) {
    logger.warn('Failed to load preferences from backend, falling back to localStorage:', error);
  }

  // Fallback to localStorage if backend fails
  try {
    const raw = localStorage.getItem(PATTERN_PREFS_KEY);
    if (!raw) return;
    const disabled: string[] = JSON.parse(raw);
    for (const p of patterns.value) {
      if (disabled.includes(p.id)) p.enabled = false;
    }
    logger.debug('Loaded pattern preferences from localStorage');
  } catch {
    logger.warn('Failed to parse pattern preferences from localStorage');
  }
}

async function togglePattern(pattern: Pattern): Promise<void> {
  // Issue #638: Save to backend first, fallback to localStorage
  const newState = !pattern.enabled;

  try {
    await api.post('/api/analytics/code-review/patterns/toggle', {
      pattern_id: pattern.id,
      enabled: newState
    });
    pattern.enabled = newState;
    // Also save to localStorage as backup
    savePatternPrefs();
    logger.debug('Pattern toggled:', { id: pattern.id, enabled: pattern.enabled });
  } catch (error) {
    logger.warn('Failed to save pattern preference to backend, using localStorage only:', error);
    // Fallback to localStorage-only mode
    pattern.enabled = newState;
    savePatternPrefs();
  }
}

async function markResolved(issue: ReviewIssue) {
  try {
    await api.post('/api/code-review/feedback', {
      issue_id: issue.id,
      feedback: 'resolved'
    })
    issues.value = issues.value.filter(i => i.id !== issue.id)
    selectedIssue.value = null
    showToast('Issue marked as resolved', 'success')
  } catch (error) {
    logger.warn('Failed to mark issue resolved:', error)
    showToast('Failed to update issue', 'error')
  }
}

async function markFalsePositive(issue: ReviewIssue) {
  try {
    await api.post('/api/code-review/feedback', {
      issue_id: issue.id,
      feedback: 'false_positive'
    })
    issues.value = issues.value.filter(i => i.id !== issue.id)
    selectedIssue.value = null
    showToast('Marked as false positive', 'info')
  } catch (error) {
    logger.warn('Failed to mark issue as false positive:', error)
    showToast('Failed to update issue', 'error')
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.code-review-dashboard {
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

/* Path Selection */
.path-selection {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.input-group label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
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

.language-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.chip {
  padding: 0.375rem 0.75rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.chip.active {
  background: var(--accent-color);
  color: white;
  border-color: var(--accent-color);
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
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

.card-icon {
  font-size: 1.5rem;
}

.card-content {
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: 1.5rem;
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
  grid-template-columns: 1fr 1fr;
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

/* Filter Tabs */
.filter-tabs {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: transparent;
  border: none;
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-tab.active {
  background: var(--accent-color);
  color: white;
}

.filter-tab .count {
  background: rgba(0,0,0,0.2);
  padding: 0.125rem 0.375rem;
  border-radius: 8px;
  font-size: 0.625rem;
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

/* Issue #704: Migrated severity colors to CSS design tokens */
.issue-card.critical {
  border-left-color: var(--color-error);
}

.issue-card.high {
  border-left-color: var(--color-warning);
}

.issue-card.medium {
  border-left-color: var(--chart-yellow);
}

.issue-card.low {
  border-left-color: var(--color-success);
}

.issue-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.severity-badge {
  font-size: 0.875rem;
}

.severity-badge.large {
  font-size: 1.5rem;
}

.severity-badge.small {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  background: var(--bg-quaternary);
}

.issue-code {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent-color);
  background: var(--bg-quaternary);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.issue-name {
  font-weight: 500;
  color: var(--text-primary);
}

.issue-location {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.file-path {
  font-family: monospace;
}

.line-number {
  color: var(--text-tertiary);
}

.issue-message {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Detail Panel */
.detail-section {
  margin-bottom: 1.25rem;
}

.detail-section label {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.detail-title h4 {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.location-info {
  font-family: monospace;
  font-size: 0.875rem;
  color: var(--text-primary);
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

.code-snippet {
  background: var(--bg-tertiary);
  border-radius: 6px;
  overflow: hidden;
}

.code-snippet pre {
  margin: 0;
  padding: 0.875rem;
  overflow-x: auto;
}

.code-snippet code {
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 0.8125rem;
  color: var(--text-primary);
}

.detail-actions {
  display: flex;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

/* Donut Chart */
.donut-chart-container {
  display: flex;
  justify-content: center;
  padding: 1rem 0;
}

.donut-chart {
  width: 160px;
  height: 160px;
}

.donut-chart .segment {
  animation: segmentFadeIn 0.5s ease-out forwards;
  opacity: 0;
}

@keyframes segmentFadeIn {
  to { opacity: 1; }
}

.center-value {
  font-size: 1.75rem;
  font-weight: 700;
  fill: var(--text-primary);
}

.center-label {
  font-size: 0.625rem;
  fill: var(--text-secondary);
}

.chart-legend {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0 1rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.legend-label {
  flex: 1;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.legend-value {
  font-weight: 600;
  color: var(--text-primary);
}

/* History Panel */
.history-panel {
  grid-column: 1 / -1;
}

.history-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 0.75rem;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.history-item:hover {
  background: var(--bg-quaternary);
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.history-path {
  font-family: monospace;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.history-date {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.history-stats {
  display: flex;
  gap: 0.5rem;
}

.stat {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
}

.stat.critical {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.stat.high {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.stat.total {
  background: var(--bg-quaternary);
  color: var(--text-secondary);
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

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
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
  padding: 0.625rem 0.875rem;
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
  cursor: pointer;
}

.pattern-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
}

.pattern-code {
  font-family: monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent-color);
}

.pattern-name {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
}

/* Responsive */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .summary-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .path-selection {
    grid-template-columns: 1fr;
  }

  .summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .history-list {
    grid-template-columns: 1fr;
  }
}
</style>
