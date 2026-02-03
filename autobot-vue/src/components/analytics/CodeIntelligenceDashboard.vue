<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #772 - Code Intelligence Dashboard Component -->

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
            placeholder="Enter path to analyze..."
            class="path-field"
          />
          <button
            @click="runAnalysis"
            :disabled="loading || !analysisPath"
            class="btn-primary"
          >
            <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
            Analyze
          </button>
        </div>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      {{ error }}
    </div>

    <!-- Health Scores Grid -->
    <div v-if="hasScores" class="scores-grid">
      <div class="score-card">
        <HealthScoreGauge
          v-if="healthScore"
          :score="healthScore.health_score"
          :grade="healthScore.grade"
          label="Code Quality"
          :status-message="`${healthScore.total_issues} issues in ${healthScore.files_analyzed} files`"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="securityScore"
          :score="securityScore.security_score"
          :grade="securityScore.grade"
          label="Security"
          :status-message="securityScore.status_message"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="performanceScore"
          :score="performanceScore.performance_score"
          :grade="performanceScore.grade"
          label="Performance"
          :status-message="performanceScore.status_message"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="redisScore"
          :score="redisScore.health_score"
          :grade="redisScore.grade"
          label="Redis Usage"
          :status-message="redisScore.status_message"
        />
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading" class="empty-state">
      <i class="fas fa-code"></i>
      <h3>No Analysis Results</h3>
      <p>Enter a path above and click Analyze to scan your codebase</p>
    </div>

    <!-- Reports Section -->
    <div v-if="hasScores" class="reports-section">
      <h3><i class="fas fa-file-alt"></i> Download Reports</h3>
      <div class="report-buttons">
        <button @click="downloadReport('security', 'json')" class="btn-secondary">
          <i class="fas fa-shield-alt"></i> Security Report (JSON)
        </button>
        <button @click="downloadReport('security', 'markdown')" class="btn-secondary">
          <i class="fas fa-shield-alt"></i> Security Report (MD)
        </button>
        <button @click="downloadReport('performance', 'json')" class="btn-secondary">
          <i class="fas fa-tachometer-alt"></i> Performance Report (JSON)
        </button>
        <button @click="downloadReport('performance', 'markdown')" class="btn-secondary">
          <i class="fas fa-tachometer-alt"></i> Performance Report (MD)
        </button>
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
  loading,
  error,
  healthScore,
  securityScore,
  performanceScore,
  redisScore,
  fetchAllScores,
  fetchAllTypes,
  downloadReport: doDownloadReport
} = useCodeIntelligence()

const analysisPath = ref('/home/kali/Desktop/AutoBot')

const hasScores = computed(() =>
  healthScore.value || securityScore.value || performanceScore.value || redisScore.value
)

async function runAnalysis() {
  if (!analysisPath.value) return
  logger.info('Running analysis on:', analysisPath.value)
  await fetchAllScores(analysisPath.value)
}

async function downloadReport(type: 'security' | 'performance', format: 'json' | 'markdown') {
  if (!analysisPath.value) return
  await doDownloadReport(analysisPath.value, type, format)
}

onMounted(async () => {
  await fetchAllTypes()
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

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
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

.reports-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.reports-section h3 {
  margin: 0 0 var(--spacing-4) 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.reports-section h3 i {
  margin-right: var(--spacing-2);
}

.report-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}
</style>
