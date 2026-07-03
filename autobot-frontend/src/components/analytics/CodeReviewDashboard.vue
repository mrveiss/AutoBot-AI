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
          {{ $t('analytics.codeReview.title') }}
        </h2>
        <p class="subtitle">{{ $t('analytics.codeReview.subtitle') }}</p>
        <!-- Issue #3436: show project scope when rendered under a codebase -->
        <p v-if="sourceId" class="project-scope-badge">{{ sourceId }}</p>
      </div>
      <div class="header-actions">
        <button class="action-btn secondary" @click="loadPatterns" :disabled="loading">
          <span class="btn-icon">⚙️</span>
          {{ $t('analytics.codeReview.patterns') }}
        </button>
        <button class="action-btn primary" @click="runAnalysis" :disabled="loading || !selectedPath">
          <span v-if="loading" class="spinner"></span>
          <span v-else class="btn-icon">▶️</span>
          {{ loading ? $t('analytics.codeReview.analyzing') : $t('analytics.codeReview.runReview') }}
        </button>
      </div>
    </div>

    <!-- Path Selection -->
    <div class="path-selection">
      <div class="input-group">
        <label>{{ $t('analytics.codeReview.filePath') }}</label>
        <input
          v-model="selectedPath"
          type="text"
          :placeholder="$t('analytics.codeReview.pathPlaceholder')"
          @keydown.enter="runAnalysis"
        />
      </div>
      <div class="input-group">
        <label>{{ $t('analytics.codeReview.languages') }}</label>
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
          <span class="card-label">{{ $t('analytics.codeReview.critical') }}</span>
        </div>
      </div>
      <div class="summary-card high">
        <div class="card-icon">🟠</div>
        <div class="card-content">
          <span class="card-value">{{ summary.high }}</span>
          <span class="card-label">{{ $t('analytics.codeReview.high') }}</span>
        </div>
      </div>
      <div class="summary-card medium">
        <div class="card-icon">🟡</div>
        <div class="card-content">
          <span class="card-value">{{ summary.medium }}</span>
          <span class="card-label">{{ $t('analytics.codeReview.medium') }}</span>
        </div>
      </div>
      <div class="summary-card low">
        <div class="card-icon">🟢</div>
        <div class="card-content">
          <span class="card-value">{{ summary.low }}</span>
          <span class="card-label">{{ $t('analytics.codeReview.low') }}</span>
        </div>
      </div>
      <div class="summary-card files">
        <div class="card-icon">📄</div>
        <div class="card-content">
          <span class="card-value">{{ summary.filesAnalyzed }}</span>
          <span class="card-label">{{ $t('analytics.codeReview.files') }}</span>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid">
      <!-- Issues List -->
      <div class="panel issues-panel">
        <div class="panel-header">
          <h3>{{ $t('analytics.codeReview.reviewIssues') }}</h3>
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
            <p v-if="!hasAnalyzed">{{ $t('analytics.codeReview.runToFindIssues') }}</p>
            <p v-else>{{ $t('analytics.codeReview.noIssuesInCategory') }}</p>
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
                <span class="line-number">{{ $t('analytics.codeReview.line') }} {{ issue.line }}</span>
              </div>
              <p class="issue-message">{{ issue.message }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Issue Detail -->
      <div class="panel detail-panel" v-if="selectedIssue">
        <div class="panel-header">
          <h3>{{ $t('analytics.codeReview.issueDetails') }}</h3>
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
            <label>{{ $t('analytics.codeReview.location') }}</label>
            <div class="location-info">
              <span class="file-path">{{ selectedIssue.file }}</span>
              <span class="line-info">{{ $t('analytics.codeReview.line') }} {{ selectedIssue.line }}, {{ $t('analytics.codeReview.column') }} {{ selectedIssue.column }}</span>
            </div>
          </div>

          <div class="detail-section">
            <label>{{ $t('analytics.codeReview.descriptionLabel') }}</label>
            <p class="description">{{ selectedIssue.message }}</p>
          </div>

          <div class="detail-section" v-if="selectedIssue.suggestion">
            <label>{{ $t('analytics.codeReview.suggestion') }}</label>
            <div class="suggestion-box">
              <span class="suggestion-icon">💡</span>
              <p>{{ selectedIssue.suggestion }}</p>
            </div>
          </div>

          <div class="detail-section" v-if="selectedIssue.snippet">
            <label>{{ $t('analytics.codeReview.codeSnippet') }}</label>
            <div class="code-snippet">
              <pre><code>{{ selectedIssue.snippet }}</code></pre>
            </div>
          </div>

          <div class="detail-actions">
            <button class="action-btn secondary" @click="markResolved(selectedIssue)">
              {{ $t('analytics.codeReview.markResolved') }}
            </button>
            <button class="action-btn secondary" @click="markFalsePositive(selectedIssue)">
              {{ $t('analytics.codeReview.falsePositive') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Pattern Categories Chart -->
      <div class="panel chart-panel" v-if="!selectedIssue">
        <div class="panel-header">
          <h3>{{ $t('analytics.codeReview.issueDistribution') }}</h3>
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
                :style="{ animationDelay: `${(index as number) * 100}ms` }"
              />
              <!-- Center text -->
              <text x="100" y="95" text-anchor="middle" class="center-value">
                {{ totalIssues }}
              </text>
              <text x="100" y="115" text-anchor="middle" class="center-label">
                {{ $t('analytics.codeReview.totalIssues') }}
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
        <h3>{{ $t('analytics.codeReview.reviewHistory') }}</h3>
        <button class="action-btn text" @click="loadHistory">
          {{ $t('analytics.codeReview.refresh') }}
        </button>
      </div>
      <div class="panel-content">
        <div class="history-list">
          <div
            v-for="review in reviewHistory"
            :key="review.id"
            class="history-item"
            @click="loadReview(review.id)"
            style="cursor: pointer;"
          >
            <div class="history-info">
              <span class="history-path">{{ review.path }}</span>
              <span class="history-date">{{ formatDate(review.timestamp) }}</span>
            </div>
            <div class="history-stats">
              <span class="stat critical" v-if="review.critical > 0">
                {{ review.critical }} {{ $t('analytics.codeReview.critical') }}
              </span>
              <span class="stat high" v-if="review.high > 0">
                {{ review.high }} {{ $t('analytics.codeReview.high') }}
              </span>
              <span class="stat total">
                {{ review.total }} {{ $t('analytics.codeReview.issuesCount') }}
              </span>
            </div>
          </div>
          <div v-if="reviewHistory.length === 0" class="empty-state small">
            <p>{{ $t('analytics.codeReview.noPreviousReviews') }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Patterns Modal -->
    <BaseModal
      :model-value="showPatterns"
      :title="$t('analytics.codeReview.reviewPatterns')"
      size="md"
      @close="showPatterns = false"
    >
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
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { BaseModal } from '@autobot/ui'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { useGroupingMemo, useAggregationMemo } from '@/composables/useComputedMemo'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const { t } = useI18n()
const logger = createLogger('CodeReviewDashboard')

// Issue #3436: read sourceId from route param set by codebase/:sourceId parent
const route = useRoute()
const sourceId = computed(() => route.params.sourceId as string | undefined)

/** Return params object merged with source_id when a sourceId is available. */
function withSourceIdParams(params: Record<string, unknown> = {}): Record<string, unknown> {
  const id = sourceId.value
  if (!id) return params
  return { ...params, source_id: id }
}

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
const { showToast } = useNotificationBus()
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
// Issue #4036: Memoized aggregation - avoid recalculating severity counts on every render
const summary = useAggregationMemo(
  () => {
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
  },
  () => [issues.value],
  { ttl: 60000 } // 1 minute TTL for summary aggregation
)

const filteredIssues = computed(() => {
  if (activeCategory.value === 'all') return issues.value
  return issues.value.filter(i => i.category === activeCategory.value)
})

const totalIssues = computed(() => issues.value.length)

// Issue #4036: Memoized chart calculations - expensive SVG segment computation
const chartSegments = useGroupingMemo(
  () => {
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
  },
  () => [issues.value],
  { ttl: 120000 } // 2 minutes TTL for chart segments
)

// Issue #4036: Memoized legend - avoids recalculating category grouping
const legendItems = useGroupingMemo(
  () => {
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
  },
  () => [issues.value],
  { ttl: 120000 } // 2 minutes TTL for legend items
)

// Issue #4036: Memoized grouping - avoid recalculating pattern categories
const patternsByCategory = useGroupingMemo(
  () => {
    const grouped: Record<string, Pattern[]> = {}
    patterns.value.forEach(pattern => {
      if (!grouped[pattern.category]) {
        grouped[pattern.category] = []
      }
      grouped[pattern.category].push(pattern)
    })
    return grouped
  },
  () => [patterns.value],
  { ttl: 180000 } // 3 minutes TTL for patterns (rarely change)
)

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

  if (diff < 60000) return t('analytics.codeReview.justNow')
  if (diff < 3600000) return t('analytics.codeReview.minutesAgo', { count: Math.floor(diff / 60000) })
  if (diff < 86400000) return t('analytics.codeReview.hoursAgo', { count: Math.floor(diff / 3600000) })
  return date.toLocaleDateString()
}

async function runAnalysis() {
  if (!selectedPath.value) {
    showToast(t('analytics.codeReview.enterPathWarning'), 'warning')
    return
  }

  loading.value = true
  hasAnalyzed.value = false

  try {
    // Issue #701: Fixed api.get call to use params option and type assertion
    // Issue #3436: scope to project when sourceId is present
    const response = await api.get<ApiDataResponse>(`${getApiBase()}/code-review/analyze`, {
      params: withSourceIdParams({
        path: selectedPath.value,
        languages: selectedLanguages.value.join(',')
      })
    })

    // Issue #701: Response is returned directly, access .issues or .data.issues
    issues.value = (response as ApiDataResponse).issues || (response as ApiDataResponse).data?.issues || []
    hasAnalyzed.value = true

    if (issues.value.length === 0) {
      showToast(t('analytics.codeReview.noIssuesFound'), 'success')
    } else {
      showToast(t('analytics.codeReview.foundIssues', { count: issues.value.length }), 'info')
    }

    await loadHistory()
  } catch (error: unknown) {
    logger.error('Analysis failed:', error)
    issues.value = []
    hasAnalyzed.value = false
    showToast(t('analytics.codeReview.analysisFailed'), 'error')
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    // Issue #701: Added type assertion for response
    // Issue #3436: scope to project when sourceId is present
    const response = await api.get<ApiDataResponse>(`${getApiBase()}/code-review/history`, {
      params: withSourceIdParams()
    })
    reviewHistory.value = (response as ApiDataResponse).reviews || (response as ApiDataResponse).data?.reviews || []
  } catch (error) {
    logger.warn('Failed to load review history:', error)
    reviewHistory.value = []
  }
}

async function loadReview(reviewId: string) {
  if (!reviewId) {
    showToast(t('analytics.codeReview.reviewNotAvailable'), 'warning')
    return
  }
  loading.value = true
  try {
    const params = withSourceIdParams()
    const response = await api.get<ApiDataResponse>(
      `${getApiBase()}/code-review/review/${reviewId}`,
      { params }
    )
    const data = response as ApiDataResponse
    issues.value = data.issues || data.data?.issues || []
    hasAnalyzed.value = true
    showToast(t('analytics.codeReview.reviewLoaded'), 'info')
  } catch (error: unknown) {
    logger.error('Failed to load review:', error)
    showToast(t('analytics.codeReview.analysisFailed'), 'error')
  } finally {
    loading.value = false
  }
}

async function loadPatterns() {
  showPatterns.value = true
  try {
    // Issue #701: Added type assertion for response
    const response = await api.get<ApiDataResponse>(`${getApiBase()}/code-review/patterns`)
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
    const response = await api.get<ApiDataResponse>(`${getApiBase()}/code-review/patterns/preferences`);
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
    await api.post<any>(`${getApiBase()}/code-review/patterns/toggle`, {
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
    await api.post<any>(`${getApiBase()}/code-review/feedback`, {
      issue_id: issue.id,
      feedback: 'resolved'
    })
    issues.value = issues.value.filter(i => i.id !== issue.id)
    selectedIssue.value = null
    showToast(t('analytics.codeReview.issueResolved'), 'success')
  } catch (error) {
    logger.warn('Failed to mark issue resolved:', error)
    showToast(t('analytics.codeReview.failedToUpdate'), 'error')
  }
}

async function markFalsePositive(issue: ReviewIssue) {
  try {
    await api.post<any>(`${getApiBase()}/code-review/feedback`, {
      issue_id: issue.id,
      feedback: 'false_positive'
    })
    issues.value = issues.value.filter(i => i.id !== issue.id)
    selectedIssue.value = null
    showToast(t('analytics.codeReview.markedFalsePositive'), 'info')
  } catch (error) {
    logger.warn('Failed to mark issue as false positive:', error)
    showToast(t('analytics.codeReview.failedToUpdate'), 'error')
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped src="@/design-system/styles/dashboard-common.css"></style>
<style scoped src="@/design-system/styles/dashboard-review-perf.css"></style>
<style scoped src="@/design-system/styles/dashboard-review-precommit.css"></style>

<style scoped>
.code-review-dashboard {
  padding: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* Path Selection */
.path-selection {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.input-group label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.language-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.chip {
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-2xl);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-200);
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
  gap: var(--spacing-4);
}

.card-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6);
}

/* Filter Tabs */
.filter-tabs {
  display: flex;
  gap: var(--spacing-1);
  flex-wrap: wrap;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: none;
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-tab.active {
  background: var(--accent-color);
  color: white;
}

.filter-tab .count {
  background: rgba(0,0,0,0.2);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-lg);
  font-size: 0.625rem;
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

.severity-badge.large {
  font-size: var(--text-2xl);
}

.severity-badge.small {
  font-size: 0.625rem;
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  background: var(--bg-quaternary);
}

.issue-code {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--accent-color);
  background: var(--bg-quaternary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
}

.issue-name {
  font-weight: 500;
  color: var(--text-primary);
}

.issue-location {
  display: flex;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.file-path {
  font-family: monospace;
}

.line-number {
  color: var(--text-tertiary);
}

.issue-message {
  margin: var(--spacing-0);
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Detail Panel */
.detail-section {
  margin-bottom: var(--spacing-5);
}

.detail-section label {
  display: block;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-2);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.location-info {
  font-family: monospace;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.code-snippet pre {
  margin: var(--spacing-0);
  padding: var(--spacing-3-5);
  overflow-x: auto;
}

.code-snippet code {
  font-family: 'Fira Code', 'Monaco', monospace;
  font-size: 0.8125rem;
  color: var(--text-primary);
}

.detail-actions {
  display: flex;
  gap: var(--spacing-3);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-color);
}

/* Donut Chart */
.donut-chart-container {
  display: flex;
  justify-content: center;
  padding: var(--spacing-4) var(--spacing-0);
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
  gap: var(--spacing-2);
  padding: var(--spacing-0) var(--spacing-4);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-default);
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
  gap: var(--spacing-3);
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.history-path {
  font-family: monospace;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.history-date {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.stat {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.6875rem;
  font-weight: 600;
}

.stat.critical {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
}

.stat.high {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
}

.stat.total {
  background: var(--bg-quaternary);
  color: var(--text-secondary);
}

.pattern-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  opacity: 0.6;
}

.pattern-toggle input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.pattern-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex: 1;
}

.pattern-code {
  font-family: monospace;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--accent-color);
}

.pattern-name {
  flex: 1;
  font-size: var(--text-sm);
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
