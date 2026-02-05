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
            placeholder="Enter path to analyze..."
            class="path-field"
          />
        </div>
        <button @click="showFileScanModal = true" class="btn-secondary">
          <i class="fas fa-file-code"></i> Scan File
        </button>
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

    <!-- Empty state for scores -->
    <div v-else-if="!loading" class="empty-state">
      <i class="fas fa-code"></i>
      <h3>No Analysis Results</h3>
      <p>Enter a path above and click Analyze to scan your codebase</p>
    </div>

    <!-- Tabs -->
    <div v-if="hasScores" class="tabs-section">
      <div class="tabs-header">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="['tab-btn', { active: activeTab === tab.id }]"
        >
          <i :class="tab.icon"></i>
          {{ tab.label }}
          <span v-if="getTabCount(tab.id) > 0" class="tab-count">
            {{ getTabCount(tab.id) }}
          </span>
        </button>
      </div>

      <div class="tabs-content">
        <SecurityFindingsPanel
          v-if="activeTab === 'security'"
          :findings="securityFindings"
          :loading="findingsLoading"
        />
        <PerformanceFindingsPanel
          v-if="activeTab === 'performance'"
          :findings="performanceFindings"
          :loading="findingsLoading"
        />
        <RedisFindingsPanel
          v-if="activeTab === 'redis'"
          :findings="redisFindings"
          :loading="findingsLoading"
        />
      </div>
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

    <!-- File Scan Modal -->
    <FileScanModal
      :show="showFileScanModal"
      @close="showFileScanModal = false"
      @scan="handleFileScan"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import HealthScoreGauge from './HealthScoreGauge.vue'
import SecurityFindingsPanel from './code-intelligence/SecurityFindingsPanel.vue'
import PerformanceFindingsPanel from './code-intelligence/PerformanceFindingsPanel.vue'
import RedisFindingsPanel from './code-intelligence/RedisFindingsPanel.vue'
import FileScanModal from './code-intelligence/FileScanModal.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodeIntelligenceDashboard')

const {
  loading,
  error,
  healthScore,
  securityScore,
  performanceScore,
  redisScore,
  securityFindings,
  performanceFindings,
  redisFindings,
  fetchAllScores,
  fetchAllTypes,
  fetchSecurityFindings,
  fetchPerformanceFindings,
  fetchRedisFindings,
  scanFileSecurity,
  scanFilePerformance,
  scanFileRedis,
  downloadReport: doDownloadReport
} = useCodeIntelligence()

const analysisPath = ref('/home/kali/Desktop/AutoBot')
const activeTab = ref<'security' | 'performance' | 'redis'>('security')
const showFileScanModal = ref(false)
const findingsLoading = ref(false)
const findingsFetched = ref({ security: false, performance: false, redis: false })

const tabs = [
  { id: 'security' as const, label: 'Security', icon: 'fas fa-shield-alt' },
  { id: 'performance' as const, label: 'Performance', icon: 'fas fa-tachometer-alt' },
  { id: 'redis' as const, label: 'Redis', icon: 'fas fa-database' }
]

const hasScores = computed(() =>
  healthScore.value || securityScore.value || performanceScore.value || redisScore.value
)

function getTabCount(tabId: string): number {
  switch (tabId) {
    case 'security': return securityFindings.value.length
    case 'performance': return performanceFindings.value.length
    case 'redis': return redisFindings.value.length
    default: return 0
  }
}

async function runAnalysis() {
  if (!analysisPath.value) return
  logger.info('Running analysis on:', analysisPath.value)

  // Reset findings cache
  findingsFetched.value = { security: false, performance: false, redis: false }

  // Fetch scores
  await fetchAllScores(analysisPath.value)

  // Fetch findings for active tab
  await loadFindingsForTab(activeTab.value)
}

async function loadFindingsForTab(tab: 'security' | 'performance' | 'redis') {
  if (findingsFetched.value[tab]) return

  findingsLoading.value = true
  try {
    switch (tab) {
      case 'security':
        await fetchSecurityFindings(analysisPath.value)
        break
      case 'performance':
        await fetchPerformanceFindings(analysisPath.value)
        break
      case 'redis':
        await fetchRedisFindings(analysisPath.value)
        break
    }
    findingsFetched.value[tab] = true
  } finally {
    findingsLoading.value = false
  }
}

// Load findings when tab changes
watch(activeTab, (newTab) => {
  if (hasScores.value) {
    loadFindingsForTab(newTab)
  }
})

async function handleFileScan(
  filePath: string,
  types: { security: boolean; performance: boolean; redis: boolean }
) {
  showFileScanModal.value = false
  findingsLoading.value = true

  try {
    const results: string[] = []

    if (types.security) {
      const findings = await scanFileSecurity(filePath)
      if (findings.length > 0) {
        findingsFetched.value.security = true
        results.push(`${findings.length} security`)
      }
    }

    if (types.performance) {
      const findings = await scanFilePerformance(filePath)
      if (findings.length > 0) {
        findingsFetched.value.performance = true
        results.push(`${findings.length} performance`)
      }
    }

    if (types.redis) {
      const findings = await scanFileRedis(filePath)
      if (findings.length > 0) {
        findingsFetched.value.redis = true
        results.push(`${findings.length} Redis`)
      }
    }

    if (results.length > 0) {
      logger.info(`File scan found: ${results.join(', ')} issues`)
      // Switch to first tab with results
      if (types.security && securityFindings.value.length > 0) {
        activeTab.value = 'security'
      } else if (types.performance && performanceFindings.value.length > 0) {
        activeTab.value = 'performance'
      } else if (types.redis && redisFindings.value.length > 0) {
        activeTab.value = 'redis'
      }
    }
  } finally {
    findingsLoading.value = false
  }
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

.tab-btn.active .tab-count {
  background: rgba(99, 102, 241, 0.2);
  color: var(--color-info-dark);
}

.tabs-content {
  min-height: 200px;
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
