# Code Intelligence Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the existing CodebaseAnalytics.vue with improved Code Intelligence UI, missing endpoints, and report download functionality.

**Architecture:** Extend the existing CodebaseAnalytics component with new sections for anti-pattern details, vulnerability types display, and report generation. Use existing API patterns and UI components (BasePanel, EmptyState).

**Tech Stack:** Vue 3, TypeScript, Pinia, TailwindCSS, Chart.js

**Related Issue:** #772 - Code Intelligence & Repository Analysis

---

## Task 1: Add TypeScript Interfaces for Code Intelligence

**Files:**
- Create: `autobot-user-frontend/src/types/codeIntelligence.ts`

**Step 1: Create the type definitions file**

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Intelligence TypeScript interfaces
 * Issue #772 - Code Intelligence & Repository Analysis
 */

// Severity levels used across all analyzers
export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

// Anti-pattern types
export interface AntiPatternType {
  name: string
  category: string
  description: string
  threshold: string
}

export interface AntiPatternResult {
  pattern_type: string
  severity: Severity
  file_path: string
  line_number: number
  message: string
  suggestion: string
}

export interface AnalysisReport {
  status: string
  timestamp: string
  report: {
    total_files: number
    total_issues: number
    anti_patterns: AntiPatternResult[]
    severity_distribution: Record<Severity, number>
  }
}

// Health score response
export interface HealthScoreResponse {
  status: string
  timestamp: string
  path: string
  health_score: number
  grade: string
  total_issues: number
  files_analyzed: number
  severity_breakdown: Record<Severity, number>
}

// Security types
export interface VulnerabilityType {
  type: string
  description: string
  owasp: string
  cwe?: string
}

export interface SecurityFinding {
  vulnerability_type: string
  severity: Severity
  file_path: string
  line_number: number
  code_snippet: string
  message: string
  remediation: string
  owasp_category: string
}

export interface SecurityScoreResponse {
  status: string
  timestamp: string
  path: string
  security_score: number
  grade: string
  risk_level: string
  status_message: string
  total_findings: number
  critical_issues: number
  high_issues: number
  files_analyzed: number
  severity_breakdown: Record<Severity, number>
  owasp_breakdown: Record<string, number>
}

// Performance types
export interface PerformanceIssueType {
  type: string
  category: string
  description: string
}

export interface PerformanceFinding {
  issue_type: string
  severity: Severity
  file_path: string
  line_number: number
  message: string
  recommendation: string
  estimated_impact: string
}

export interface PerformanceScoreResponse {
  status: string
  timestamp: string
  path: string
  performance_score: number
  grade: string
  status_message: string
  total_issues: number
  critical_issues: number
  high_issues: number
  files_analyzed: number
  severity_breakdown: Record<Severity, number>
  top_issues: string[]
}

// Redis optimization types
export interface RedisOptimizationType {
  name: string
  category: string
  description: string
  recommendation: string
}

export interface RedisHealthScoreResponse {
  status: string
  timestamp: string
  path: string
  health_score: number
  grade: string
  status_message: string
  total_optimizations: number
  files_with_issues: number
  severity_breakdown: Record<Severity, number>
  category_breakdown: Record<string, number>
}

// Report types
export interface ReportResponse {
  status: string
  timestamp: string
  path: string
  format: 'json' | 'markdown'
  report: string | object
}
```

**Step 2: Verify file created**

Run: `ls -la autobot-user-frontend/src/types/codeIntelligence.ts`
Expected: File exists with correct permissions

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/types/codeIntelligence.ts
git commit -m "feat(#772): add TypeScript interfaces for code intelligence"
```

---

## Task 2: Create Code Intelligence Composable

**Files:**
- Create: `autobot-user-frontend/src/composables/useCodeIntelligence.ts`

**Step 1: Create the composable**

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Intelligence API composable
 * Issue #772 - Code Intelligence & Repository Analysis
 */

import { ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type {
  HealthScoreResponse,
  SecurityScoreResponse,
  PerformanceScoreResponse,
  RedisHealthScoreResponse,
  AntiPatternType,
  VulnerabilityType,
  PerformanceIssueType,
  RedisOptimizationType,
  ReportResponse
} from '@/types/codeIntelligence'

const logger = createLogger('useCodeIntelligence')

export function useCodeIntelligence() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Health scores
  const healthScore = ref<HealthScoreResponse | null>(null)
  const securityScore = ref<SecurityScoreResponse | null>(null)
  const performanceScore = ref<PerformanceScoreResponse | null>(null)
  const redisScore = ref<RedisHealthScoreResponse | null>(null)

  // Type definitions
  const patternTypes = ref<Record<string, AntiPatternType> | null>(null)
  const vulnerabilityTypes = ref<VulnerabilityType[] | null>(null)
  const performanceIssueTypes = ref<PerformanceIssueType[] | null>(null)
  const redisOptimizationTypes = ref<Record<string, RedisOptimizationType> | null>(null)

  async function getBackendUrl(): Promise<string> {
    return await appConfig.getServiceUrl('backend')
  }

  async function fetchHealthScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code_intelligence/health-score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      healthScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch health score: ${e}`
      logger.error('fetchHealthScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchSecurityScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code_intelligence/security/score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      securityScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch security score: ${e}`
      logger.error('fetchSecurityScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchPerformanceScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code_intelligence/performance/score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      performanceScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch performance score: ${e}`
      logger.error('fetchPerformanceScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchRedisScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code_intelligence/redis/health-score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      redisScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch Redis score: ${e}`
      logger.error('fetchRedisScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchPatternTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code_intelligence/pattern-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      patternTypes.value = data.pattern_types
    } catch (e) {
      logger.error('fetchPatternTypes failed:', e)
    }
  }

  async function fetchVulnerabilityTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code_intelligence/security/vulnerability-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      vulnerabilityTypes.value = data.vulnerability_types
    } catch (e) {
      logger.error('fetchVulnerabilityTypes failed:', e)
    }
  }

  async function fetchPerformanceIssueTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code_intelligence/performance/issue-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      performanceIssueTypes.value = data.issue_types
    } catch (e) {
      logger.error('fetchPerformanceIssueTypes failed:', e)
    }
  }

  async function fetchRedisOptimizationTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code_intelligence/redis/optimization-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      redisOptimizationTypes.value = data.optimization_types
    } catch (e) {
      logger.error('fetchRedisOptimizationTypes failed:', e)
    }
  }

  async function downloadReport(
    path: string,
    type: 'security' | 'performance',
    format: 'json' | 'markdown'
  ): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code_intelligence/${type}/report?path=${encodeURIComponent(path)}&format=${format}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data: ReportResponse = await response.json()

      // Create download
      const content = format === 'json'
        ? JSON.stringify(data.report, null, 2)
        : data.report as string
      const blob = new Blob([content], {
        type: format === 'json' ? 'application/json' : 'text/markdown'
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${type}-report-${new Date().toISOString().split('T')[0]}.${format === 'json' ? 'json' : 'md'}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      error.value = `Failed to download report: ${e}`
      logger.error('downloadReport failed:', e)
    }
  }

  async function fetchAllScores(path: string): Promise<void> {
    await Promise.all([
      fetchHealthScore(path),
      fetchSecurityScore(path),
      fetchPerformanceScore(path),
      fetchRedisScore(path)
    ])
  }

  async function fetchAllTypes(): Promise<void> {
    await Promise.all([
      fetchPatternTypes(),
      fetchVulnerabilityTypes(),
      fetchPerformanceIssueTypes(),
      fetchRedisOptimizationTypes()
    ])
  }

  return {
    // State
    loading,
    error,
    healthScore,
    securityScore,
    performanceScore,
    redisScore,
    patternTypes,
    vulnerabilityTypes,
    performanceIssueTypes,
    redisOptimizationTypes,
    // Actions
    fetchHealthScore,
    fetchSecurityScore,
    fetchPerformanceScore,
    fetchRedisScore,
    fetchPatternTypes,
    fetchVulnerabilityTypes,
    fetchPerformanceIssueTypes,
    fetchRedisOptimizationTypes,
    fetchAllScores,
    fetchAllTypes,
    downloadReport
  }
}
```

**Step 2: Verify file created**

Run: `ls -la autobot-user-frontend/src/composables/useCodeIntelligence.ts`
Expected: File exists

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/composables/useCodeIntelligence.ts
git commit -m "feat(#772): add useCodeIntelligence composable for API calls"
```

---

## Task 3: Create Health Score Gauge Component

**Files:**
- Create: `autobot-user-frontend/src/components/analytics/HealthScoreGauge.vue`

**Step 1: Create the gauge component**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #772 - Code Intelligence Health Score Gauge -->

<template>
  <div class="health-score-gauge">
    <div class="gauge-container">
      <svg viewBox="0 0 120 80" class="gauge-svg">
        <!-- Background arc -->
        <path
          :d="backgroundArc"
          fill="none"
          stroke="var(--bg-tertiary)"
          stroke-width="12"
          stroke-linecap="round"
        />
        <!-- Score arc -->
        <path
          :d="scoreArc"
          fill="none"
          :stroke="scoreColor"
          stroke-width="12"
          stroke-linecap="round"
          class="score-arc"
        />
      </svg>
      <div class="score-display">
        <span class="score-value">{{ score }}</span>
        <span class="score-grade" :style="{ color: scoreColor }">{{ grade }}</span>
      </div>
    </div>
    <div class="gauge-label">{{ label }}</div>
    <div v-if="statusMessage" class="status-message">{{ statusMessage }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  score: number
  grade: string
  label: string
  statusMessage?: string
}>()

const scoreColor = computed(() => {
  if (props.score >= 90) return 'var(--chart-green)'
  if (props.score >= 80) return 'var(--color-info-dark)'
  if (props.score >= 70) return 'var(--chart-yellow, #f59e0b)'
  if (props.score >= 50) return 'var(--chart-orange, #f97316)'
  return 'var(--chart-red, #ef4444)'
})

// SVG arc calculations
const radius = 50
const centerX = 60
const centerY = 70

function polarToCartesian(angle: number) {
  const radians = (angle - 180) * Math.PI / 180
  return {
    x: centerX + radius * Math.cos(radians),
    y: centerY + radius * Math.sin(radians)
  }
}

const backgroundArc = computed(() => {
  const start = polarToCartesian(0)
  const end = polarToCartesian(180)
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 0 1 ${end.x} ${end.y}`
})

const scoreArc = computed(() => {
  const scoreAngle = (props.score / 100) * 180
  const start = polarToCartesian(0)
  const end = polarToCartesian(scoreAngle)
  const largeArc = scoreAngle > 90 ? 1 : 0
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x} ${end.y}`
})
</script>

<style scoped>
.health-score-gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-4);
}

.gauge-container {
  position: relative;
  width: 120px;
  height: 80px;
}

.gauge-svg {
  width: 100%;
  height: 100%;
}

.score-arc {
  transition: stroke-dasharray 0.5s ease;
}

.score-display {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
}

.score-value {
  font-size: 1.5rem;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.score-grade {
  display: block;
  font-size: 0.875rem;
  font-weight: var(--font-medium);
}

.gauge-label {
  margin-top: var(--spacing-2);
  font-size: 0.875rem;
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.status-message {
  margin-top: var(--spacing-1);
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-align: center;
  max-width: 150px;
}
</style>
```

**Step 2: Verify file created**

Run: `ls -la autobot-user-frontend/src/components/analytics/HealthScoreGauge.vue`
Expected: File exists

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/HealthScoreGauge.vue
git commit -m "feat(#772): add HealthScoreGauge component for code intelligence"
```

---

## Task 4: Create Code Intelligence Dashboard Component

**Files:**
- Create: `autobot-user-frontend/src/components/analytics/CodeIntelligenceDashboard.vue`

**Step 1: Create the dashboard component**

```vue
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
```

**Step 2: Verify file created**

Run: `ls -la autobot-user-frontend/src/components/analytics/CodeIntelligenceDashboard.vue`
Expected: File exists

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/components/analytics/CodeIntelligenceDashboard.vue
git commit -m "feat(#772): add CodeIntelligenceDashboard component"
```

---

## Task 5: Add Code Intelligence Route to Analytics

**Files:**
- Modify: `autobot-user-frontend/src/router/index.ts`
- Modify: `autobot-user-frontend/src/views/AnalyticsView.vue`

**Step 1: Add route to router/index.ts**

Find the analytics children routes and add:

```typescript
{
  path: 'code-intelligence',
  name: 'analytics-code-intelligence',
  component: () => import('@/components/analytics/CodeIntelligenceDashboard.vue'),
  meta: {
    title: 'Code Intelligence',
    parent: 'analytics'
  }
}
```

**Step 2: Add tab to AnalyticsView.vue navigation**

Add a new tab link in the navigation section:

```vue
<router-link
  to="/analytics/code-intelligence"
  :class="{ active: $route.path === '/analytics/code-intelligence' }"
>
  <i class="fas fa-brain"></i>
  Code Intelligence
</router-link>
```

**Step 3: Verify changes work**

Run: `cd autobot-vue && npm run build`
Expected: Build succeeds without errors

**Step 4: Commit**

```bash
git add autobot-user-frontend/src/router/index.ts autobot-user-frontend/src/views/AnalyticsView.vue
git commit -m "feat(#772): add Code Intelligence route and navigation tab"
```

---

## Task 6: Sync to Frontend VM and Test

**Step 1: Sync frontend changes**

Run: `./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/ /home/autobot/autobot-user-frontend/src/`
Expected: Files synced successfully

**Step 2: Verify in browser**

Navigate to: `http://172.16.168.21:5173/analytics/code-intelligence`
Expected: Code Intelligence dashboard loads with health score gauges

**Step 3: Test analysis**

1. Enter path `/home/kali/Desktop/AutoBot`
2. Click Analyze
3. Verify health scores appear
4. Test report download

**Step 4: Commit final verification**

```bash
git add -A
git commit -m "feat(#772): complete Code Intelligence frontend implementation"
```

---

## Summary

This plan implements:
1. TypeScript interfaces for all Code Intelligence API responses
2. `useCodeIntelligence` composable for API calls
3. `HealthScoreGauge` visualization component
4. `CodeIntelligenceDashboard` main component
5. Route and navigation integration
6. Report download functionality

Total tasks: 6
Estimated commits: 6
