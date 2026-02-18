<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard Component -->

<template>
  <div class="code-intelligence-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2><i class="fas fa-brain"></i> Code Intelligence</h2>
        <p class="header-description">Analyze your codebase for quality, security, and performance issues</p>
      </div>
      <div class="header-actions">
        <div class="path-input">
          <input
            v-model="analysisPath"
            type="text"
            placeholder="Enter code snippet to analyze..."
            class="path-field"
          />
        </div>
        <button
          @click="runAnalysis"
          :disabled="isLoading || !analysisPath"
          class="btn-primary"
        >
          <i :class="isLoading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          Analyze
        </button>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      {{ error }}
    </div>

    <!-- Health & Quality Scores Grid -->
    <div v-if="hasScores" class="scores-grid">
      <div class="score-card">
        <HealthScoreGauge
          v-if="healthScore"
          :score="healthScore.health_score"
          :grade="healthScore.health_score >= 90 ? 'A' : healthScore.health_score >= 80 ? 'B' : healthScore.health_score >= 70 ? 'C' : healthScore.health_score >= 60 ? 'D' : 'F'"
          label="Code Health"
          :status-message="`${healthScore.issues_count.critical + healthScore.issues_count.high + healthScore.issues_count.medium + healthScore.issues_count.low} issues · ${healthScore.coverage_percent}% coverage`"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="qualityScore"
          :score="qualityScore.overall_score"
          :grade="qualityScore.grade"
          label="Code Quality"
          :status-message="`Trend: ${qualityScore.trend}`"
        />
      </div>
      <!-- TODO: implement securityScore in backend (#920) -->
      <!-- TODO: implement performanceScore in backend (#920) -->
      <!-- TODO: implement redisScore in backend (#920) -->
    </div>

    <!-- Empty state for scores -->
    <div v-else-if="!isLoading" class="empty-state">
      <i class="fas fa-code"></i>
      <h3>No Analysis Results</h3>
      <p>Enter a code snippet above and click Analyze to inspect quality and health</p>
    </div>

    <!-- Suggestions Tab -->
    <div v-if="suggestions.length > 0" class="tabs-section">
      <div class="tabs-header">
        <button class="tab-btn active">
          <i class="fas fa-lightbulb"></i>
          Suggestions
          <span class="tab-count">{{ suggestions.length }}</span>
        </button>
      </div>

      <div class="tabs-content">
        <div class="suggestions-list">
          <div
            v-for="suggestion in suggestions"
            :key="suggestion.id"
            class="suggestion-item"
            :class="`priority-${suggestion.priority}`"
          >
            <div class="suggestion-header">
              <span class="suggestion-type">{{ suggestion.type }}</span>
              <span class="suggestion-priority" :class="`badge-${suggestion.priority}`">
                {{ suggestion.priority }}
              </span>
            </div>
            <div class="suggestion-title">{{ suggestion.title }}</div>
            <div class="suggestion-description">{{ suggestion.description }}</div>
            <div v-if="suggestion.impact" class="suggestion-impact">
              <i class="fas fa-bolt"></i> {{ suggestion.impact }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Current Analysis Issues -->
    <div v-if="currentAnalysis && currentAnalysis.issues.length > 0" class="issues-section">
      <h3><i class="fas fa-exclamation-triangle"></i> Issues Found</h3>
      <div class="issues-list">
        <div
          v-for="(issue, idx) in currentAnalysis.issues"
          :key="idx"
          class="issue-item"
          :class="`severity-${issue.severity}`"
        >
          <span class="issue-severity" :class="issue.severity">{{ issue.severity }}</span>
          <span class="issue-category">{{ issue.category }}</span>
          <span class="issue-message">{{ issue.message }}</span>
          <span v-if="issue.line_number" class="issue-line">Line {{ issue.line_number }}</span>
        </div>
      </div>
    </div>

    <!-- Analysis History -->
    <div v-if="analysisHistory.length > 0" class="history-section">
      <h3><i class="fas fa-history"></i> Analysis History</h3>
      <div class="history-list">
        <div
          v-for="item in analysisHistory.slice(0, 10)"
          :key="item.id"
          class="history-item"
          @click="loadHistoryItem(item.id)"
        >
          <div class="history-meta">
            <span class="history-lang">{{ item.language }}</span>
            <span class="history-score" :class="getQualityClass(item.quality_score)">
              {{ item.quality_score }}/100
            </span>
          </div>
          <div class="history-filename">{{ item.filename || 'Untitled' }}</div>
          <div class="history-time">{{ formatTimestamp(item.timestamp) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import HealthScoreGauge from './HealthScoreGauge.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodeIntelligenceDashboard')

const {
  isLoading,
  error,
  currentAnalysis,
  analysisHistory,
  qualityScore,
  healthScore,
  suggestions,
  analyzeCode,
  getAnalysis,
  getQualityScore,
  getHealthScore,
  getSuggestions,
  getAnalysisHistory,
} = useCodeIntelligence()

const analysisPath = ref('')

const hasScores = computed(() => healthScore.value !== null || qualityScore.value !== null)

async function runAnalysis() {
  if (!analysisPath.value) return
  logger.info('Running code analysis')
  await analyzeCode({ code: analysisPath.value })
  await Promise.all([
    getQualityScore(analysisPath.value),
    getSuggestions(analysisPath.value),
  ])
}

async function loadHistoryItem(id: string) {
  await getAnalysis(id)
}

function getQualityClass(score: number): string {
  if (score >= 80) return 'score-good'
  if (score >= 60) return 'score-medium'
  return 'score-poor'
}

function formatTimestamp(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleString()
  } catch {
    return timestamp
  }
}

onMounted(async () => {
  await Promise.all([getHealthScore(), getAnalysisHistory()])
})
</script>

<style scoped>
.code-intelligence-dashboard {
  padding: var(--spacing-4);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-6);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.header-content h2 {
  font-size: 1.5rem;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.header-content h2 i {
  margin-right: var(--spacing-2);
  color: var(--color-info-dark);
}

.header-description {
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.path-input {
  display: flex;
  gap: var(--spacing-2);
}

.path-field {
  width: 300px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.btn-primary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-info-dark);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: var(--font-medium);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  padding: var(--spacing-3);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  color: #ef4444;
  margin-bottom: var(--spacing-4);
}

.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.score-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  justify-content: center;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.empty-state i {
  font-size: 3rem;
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.empty-state h3 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
}

.tabs-section {
  margin-bottom: var(--spacing-6);
}

.tabs-header {
  display: flex;
  gap: var(--spacing-1);
  border-bottom: 1px solid var(--border-primary);
  margin-bottom: var(--spacing-4);
}

.tab-btn {
  padding: var(--spacing-2) var(--spacing-4);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: 0.875rem;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--color-info-dark);
  border-bottom-color: var(--color-info-dark);
}

.tab-count {
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
}

.tabs-content {
  min-height: 200px;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.suggestion-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1);
}

.suggestion-type {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.badge-high {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
}

.badge-medium {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
}

.badge-low {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
}

.suggestion-title {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.suggestion-description {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.suggestion-impact {
  margin-top: var(--spacing-1);
  font-size: 0.8rem;
  color: var(--color-info-dark);
}

.issues-section {
  margin-bottom: var(--spacing-6);
}

.issues-section h3 {
  font-size: 1rem;
  margin-bottom: var(--spacing-3);
  color: var(--text-primary);
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.issue-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-primary);
  font-size: 0.875rem;
}

.issue-severity {
  font-size: 0.75rem;
  font-weight: var(--font-semibold);
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.issue-severity.critical { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.issue-severity.high { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.issue-severity.medium { background: rgba(99, 102, 241, 0.15); color: var(--color-info-dark); }
.issue-severity.low { background: rgba(16, 185, 129, 0.15); color: #10b981; }

.issue-category {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.issue-message {
  flex: 1;
  color: var(--text-primary);
}

.issue-line {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.history-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.history-section h3 {
  margin: 0 0 var(--spacing-4) 0;
  font-size: 1rem;
  color: var(--text-primary);
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
  padding: var(--spacing-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s;
}

.history-item:hover {
  background: var(--bg-tertiary);
}

.history-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.history-lang {
  font-size: 0.75rem;
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  color: var(--text-secondary);
}

.history-score {
  font-weight: var(--font-semibold);
  font-size: 0.875rem;
}

.score-good { color: #10b981; }
.score-medium { color: #f59e0b; }
.score-poor { color: #ef4444; }

.history-filename {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.history-time {
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
