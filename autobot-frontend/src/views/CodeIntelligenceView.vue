<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * CodeIntelligenceView - Code analysis and quality monitoring
 * Issue #899 - Code Intelligence Tools
 */

import { ref, computed, onMounted } from 'vue'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import type { CodeAnalysisRequest } from '@/composables/useCodeIntelligence'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodeIntelligenceView')

const {
  currentAnalysis,
  analysisHistory,
  qualityScore,
  healthScore,
  suggestions,
  trends,
  isLoading,
  error,
  analyzeCode,
  getQualityScore,
  getSuggestions,
  getHealthScore,
  getTrends,
  getAnalysisHistory,
  deleteAnalysis,
} = useCodeIntelligence({ autoFetch: true })

const activeTab = ref<'analysis' | 'quality' | 'suggestions' | 'history'>('analysis')
const codeInput = ref('')
const languageInput = ref('python')
const filenameInput = ref('')

const supportedLanguages = ['python', 'javascript', 'typescript', 'java', 'go', 'rust', 'cpp']

async function handleAnalyze() {
  if (!codeInput.value.trim()) return

  const request: CodeAnalysisRequest = {
    code: codeInput.value,
    language: languageInput.value,
    filename: filenameInput.value || undefined,
    include_suggestions: true,
  }

  const result = await analyzeCode(request)
  if (result) {
    logger.debug('Analysis complete, switching to quality tab')
    activeTab.value = 'quality'
  }
}

async function handleGetSuggestions() {
  if (!codeInput.value.trim()) return
  await getSuggestions(codeInput.value, languageInput.value)
  activeTab.value = 'suggestions'
}

async function handleDeleteAnalysis(id: string) {
  if (confirm('Delete this analysis?')) {
    await deleteAnalysis(id)
  }
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'score-success'
  if (score >= 60) return 'score-warning'
  return 'score-error'
}

function getSeverityClass(severity: string): string {
  switch (severity) {
    case 'critical': return 'severity-critical'
    case 'high': return 'severity-high'
    case 'medium': return 'severity-medium'
    case 'low': return 'severity-low'
    default: return 'severity-default'
  }
}

onMounted(async () => {
  await Promise.all([getHealthScore(), getTrends(), getAnalysisHistory()])
})
</script>

<template>
  <div class="code-intel-view">
    <!-- Page Header -->
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Code Intelligence</h2>
        <p class="page-subtitle">Analyze code quality, get suggestions, and monitor health</p>
      </div>
      <div v-if="healthScore" class="health-summary">
        <div class="health-label">Codebase Health</div>
        <div :class="['health-value', getScoreColor(healthScore.health_score)]">
          {{ healthScore.health_score.toFixed(0) }}%
        </div>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="alert alert-error">
      <i class="fas fa-exclamation-circle"></i>
      <div class="alert-content">
        <strong>Error</strong>
        <p>{{ error }}</p>
      </div>
    </div>

    <!-- Tabs -->
    <nav class="tab-nav">
      <button
        @click="activeTab = 'analysis'"
        :class="['tab-btn', { active: activeTab === 'analysis' }]"
      >
        <i class="fas fa-microscope"></i> Analysis
      </button>
      <button
        @click="activeTab = 'quality'"
        :class="['tab-btn', { active: activeTab === 'quality' }]"
      >
        <i class="fas fa-chart-bar"></i> Quality Score
      </button>
      <button
        @click="activeTab = 'suggestions'"
        :class="['tab-btn', { active: activeTab === 'suggestions' }]"
      >
        <i class="fas fa-lightbulb"></i> Suggestions ({{ suggestions.length }})
      </button>
      <button
        @click="activeTab = 'history'"
        :class="['tab-btn', { active: activeTab === 'history' }]"
      >
        <i class="fas fa-history"></i> History ({{ analysisHistory.length }})
      </button>
    </nav>

    <!-- Tab Content -->
    <div class="tab-content">
      <!-- Analysis Tab -->
      <div v-show="activeTab === 'analysis'" class="tab-panel">
        <div class="card">
          <div class="card-header">
            <span class="card-title">Code Analysis</span>
          </div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field-group">
                <label class="field-label">Language</label>
                <select v-model="languageInput" class="field-select">
                  <option v-for="lang in supportedLanguages" :key="lang" :value="lang">
                    {{ lang.charAt(0).toUpperCase() + lang.slice(1) }}
                  </option>
                </select>
              </div>
              <div class="field-group">
                <label class="field-label">Filename (optional)</label>
                <input
                  v-model="filenameInput"
                  type="text"
                  placeholder="example.py"
                  class="field-input"
                >
              </div>
            </div>

            <div class="field-group">
              <label class="field-label">Code</label>
              <textarea
                v-model="codeInput"
                rows="15"
                placeholder="Paste your code here..."
                class="field-input code-textarea"
              ></textarea>
            </div>

            <div class="action-row">
              <button
                @click="handleAnalyze"
                :disabled="isLoading || !codeInput.trim()"
                class="btn-action-primary"
              >
                {{ isLoading ? 'Analyzing...' : 'Analyze Code' }}
              </button>
              <button
                @click="handleGetSuggestions"
                :disabled="isLoading || !codeInput.trim()"
                class="btn-action-secondary"
              >
                Get Suggestions
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Quality Tab -->
      <div v-show="activeTab === 'quality'" class="tab-panel">
        <div v-if="!currentAnalysis && !qualityScore" class="empty-state">
          <i class="fas fa-chart-bar"></i>
          <p>Analyze code to see quality metrics</p>
        </div>

        <template v-else>
          <div v-if="currentAnalysis" class="card">
            <div class="card-header">
              <span class="card-title">Quality Score</span>
              <span :class="['score-display', getScoreColor(currentAnalysis.quality_score)]">
                {{ currentAnalysis.quality_score.toFixed(0) }}/100
              </span>
            </div>
            <div class="card-body">
              <div class="metrics-grid">
                <div v-for="(value, key) in currentAnalysis.metrics" :key="key" class="metric-card">
                  <div class="metric-label">{{ (key as string).replace(/_/g, ' ') }}</div>
                  <div class="metric-value">{{ value }}</div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="currentAnalysis && currentAnalysis.issues.length > 0" class="card issues-card">
            <div class="card-header">
              <span class="card-title">Issues ({{ currentAnalysis.issues.length }})</span>
            </div>
            <div class="card-body">
              <div class="issues-list">
                <div v-for="(issue, idx) in currentAnalysis.issues" :key="idx" class="issue-item">
                  <span :class="['badge', getSeverityClass(issue.severity)]">
                    {{ issue.severity }}
                  </span>
                  <div class="issue-content">
                    <p class="issue-message">{{ issue.message }}</p>
                    <p v-if="issue.line_number" class="issue-line">Line {{ issue.line_number }}</p>
                    <p v-if="issue.suggestion" class="issue-suggestion">{{ issue.suggestion }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Suggestions Tab -->
      <div v-show="activeTab === 'suggestions'" class="tab-panel">
        <div v-if="suggestions.length === 0" class="empty-state">
          <i class="fas fa-lightbulb"></i>
          <p>No suggestions available. Analyze code first.</p>
        </div>

        <div v-else class="suggestions-list">
          <div v-for="suggestion in suggestions" :key="suggestion.id" class="card suggestion-card">
            <div class="card-body">
              <h3 class="suggestion-title">{{ suggestion.title }}</h3>
              <div class="suggestion-meta">
                <span class="badge badge-info">{{ suggestion.type }}</span>
                <span :class="[
                  'badge',
                  suggestion.priority === 'high' ? 'severity-high' :
                  suggestion.priority === 'medium' ? 'severity-medium' :
                  'severity-default'
                ]">
                  {{ suggestion.priority }} priority
                </span>
              </div>
              <p class="suggestion-desc">{{ suggestion.description }}</p>
              <div v-if="suggestion.impact" class="suggestion-impact">
                <strong>Impact:</strong> {{ suggestion.impact }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- History Tab -->
      <div v-show="activeTab === 'history'" class="tab-panel">
        <div v-if="analysisHistory.length === 0" class="empty-state">
          <i class="fas fa-history"></i>
          <p>No analysis history yet</p>
        </div>

        <div v-else class="card">
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Language</th>
                  <th>Quality Score</th>
                  <th>Issues</th>
                  <th>Date</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="analysis in analysisHistory" :key="analysis.id">
                  <td class="cell-primary">{{ analysis.filename || 'Untitled' }}</td>
                  <td>{{ analysis.language }}</td>
                  <td>
                    <span :class="['score-inline', getScoreColor(analysis.quality_score)]">
                      {{ analysis.quality_score.toFixed(0) }}
                    </span>
                  </td>
                  <td>{{ analysis.issues.length }}</td>
                  <td>{{ new Date(analysis.timestamp).toLocaleString() }}</td>
                  <td>
                    <button @click="handleDeleteAnalysis(analysis.id)" class="btn-delete">
                      Delete
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.code-intel-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.health-summary {
  text-align: right;
  flex-shrink: 0;
}

.health-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.health-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
}

.alert {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  margin: 0 var(--spacing-5);
  border-radius: var(--radius-md);
}

.alert-error {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
}

.alert-content p {
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.code-textarea {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  resize: vertical;
}

.action-row {
  display: flex;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
}

.score-success { color: var(--color-success); }
.score-warning { color: var(--color-warning); }
.score-error { color: var(--color-error); }

.score-display {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
}

.score-inline {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--spacing-4);
}

.metric-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
}

.metric-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
  text-transform: capitalize;
}

.metric-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.issues-card { margin-top: var(--spacing-4); }

.issues-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.issue-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.issue-content { flex: 1; }

.issue-message {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin: 0;
}

.issue-line {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: var(--spacing-1) 0 0;
}

.issue-suggestion {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-2) 0 0;
}

.severity-critical { background: var(--color-error-bg); color: var(--color-error); }
.severity-high { background: var(--color-warning-bg); color: var(--color-warning); }
.severity-medium { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.severity-low { background: var(--color-info-bg); color: var(--color-info); }
.severity-default { background: var(--bg-tertiary); color: var(--text-secondary); }

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.suggestion-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2);
}

.suggestion-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-3);
}

.suggestion-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3);
}

.suggestion-impact {
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
}

.table-wrapper { overflow-x: auto; }

.cell-primary {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.btn-delete {
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
  transition: background var(--duration-150) var(--ease-in-out);
}

.btn-delete:hover { background: var(--color-error-bg); }

@media (max-width: 768px) {
  .form-grid { grid-template-columns: 1fr; }
  .metrics-grid { grid-template-columns: 1fr 1fr; }
}
</style>
