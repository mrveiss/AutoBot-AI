<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Code Intelligence Scores section (#538,#566) -->
<!-- Issue #3073: Wired HealthScoreGauge, health/quality scores, suggestions, and analysis history -->
<template>
  <div class="code-intelligence-scores-section analytics-section">
    <h3>
      <Icon name="shield-alt" /> {{ $t('analytics.codebase.intelligence.scoresTitle') }}
      <button
        @click="emit('refresh-all')"
        :disabled="securityLoading || performanceLoading || redisLoading"
        class="refresh-btn"
        style="margin-left: 10px;"
      >
        <i
          :class="
            securityLoading || performanceLoading || redisLoading
              ? 'fas fa-spinner fa-spin'
              : 'sync-alt'
          "
        ></i>
      </button>
    </h3>

    <div class="scores-grid">
      <!-- Security Score Card -->
      <div class="score-card security-card">
        <div class="score-header">
          <Icon name="shield-alt" />
          <span>{{ $t('analytics.codebase.intelligence.security') }}</span>
          <button
            @click="emit('refresh-security')"
            :disabled="securityLoading"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshSecurity')"
          >
            <i :class="securityLoading ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
          </button>
        </div>
        <div v-if="securityLoading" class="score-loading">
          <Icon name="spinner" class="animate-spin" />
        </div>
        <div v-else-if="securityError" class="score-error">
          <Icon name="exclamation-triangle" />
          <span>{{ securityError }}</span>
        </div>
        <div v-else-if="securityScore" class="score-content">
          <HealthScoreGauge
            :score="securityScore.security_score"
            :grade="securityScore.grade"
            :label="$t('analytics.codebase.intelligence.security')"
            :status-message="securityScore.status_message"
          />
          <div class="score-details">
            <span class="detail-item critical" v-if="securityScore.critical_issues > 0">
              <Icon name="times-circle" /> {{ securityScore.critical_issues }} critical
            </span>
            <span class="detail-item warning" v-if="securityScore.high_issues > 0">
              <Icon name="exclamation-circle" /> {{ securityScore.high_issues }} high
            </span>
            <span class="detail-item info">
              <Icon name="file-code" /> {{ securityScore.files_analyzed }} files
            </span>
          </div>
          <button
            class="view-details-btn"
            @click="toggleSecurityDetails"
            :disabled="securityFindingsLoading"
          >
            <i
              :class="
                securityFindingsLoading
                  ? 'fas fa-spinner fa-spin'
                  : showSecurityDetails
                  ? 'chevron-up'
                  : 'chevron-down'
              "
            ></i>
            {{
              showSecurityDetails
                ? $t('analytics.codebase.intelligence.hideDetails')
                : $t('analytics.codebase.intelligence.viewDetails')
            }}
          </button>
        </div>
        <div v-else class="score-empty">
          <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
        </div>
      </div>

      <!-- Performance Score Card -->
      <div class="score-card performance-card">
        <div class="score-header">
          <Icon name="tachometer-alt" />
          <span>{{ $t('analytics.codebase.intelligence.performanceLabel') }}</span>
          <button
            @click="emit('refresh-performance')"
            :disabled="performanceLoading"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshPerformance')"
          >
            <i :class="performanceLoading ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
          </button>
        </div>
        <div v-if="performanceLoading" class="score-loading">
          <Icon name="spinner" class="animate-spin" />
        </div>
        <div v-else-if="performanceError" class="score-error">
          <Icon name="exclamation-triangle" />
          <span>{{ performanceError }}</span>
        </div>
        <div v-else-if="performanceScore" class="score-content">
          <HealthScoreGauge
            :score="performanceScore.performance_score"
            :grade="performanceScore.grade"
            :label="$t('analytics.codebase.intelligence.performanceLabel')"
            :status-message="performanceScore.status_message"
          />
          <div class="score-details">
            <span class="detail-item warning" v-if="performanceScore.total_issues > 0">
              <Icon name="exclamation-triangle" /> {{ performanceScore.total_issues }} issues
            </span>
            <span class="detail-item info">
              <Icon name="file-code" /> {{ performanceScore.files_analyzed }} files
            </span>
          </div>
          <button
            class="view-details-btn"
            @click="togglePerformanceDetails"
            :disabled="performanceFindingsLoading"
          >
            <i
              :class="
                performanceFindingsLoading
                  ? 'fas fa-spinner fa-spin'
                  : showPerformanceDetails
                  ? 'chevron-up'
                  : 'chevron-down'
              "
            ></i>
            {{
              showPerformanceDetails
                ? $t('analytics.codebase.intelligence.hideDetails')
                : $t('analytics.codebase.intelligence.viewDetails')
            }}
          </button>
        </div>
        <div v-else class="score-empty">
          <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
        </div>
      </div>

      <!-- Redis Health Score Card -->
      <div class="score-card redis-card">
        <div class="score-header">
          <Icon name="database" />
          <span>{{ $t('analytics.codebase.intelligence.redisUsage') }}</span>
          <button
            @click="emit('refresh-redis')"
            :disabled="redisLoading"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshRedis')"
          >
            <i :class="redisLoading ? 'fas fa-spinner fa-spin' : 'sync-alt'"></i>
          </button>
        </div>
        <div v-if="redisLoading" class="score-loading">
          <Icon name="spinner" class="animate-spin" />
        </div>
        <div v-else-if="redisError" class="score-error">
          <Icon name="exclamation-triangle" />
          <span>{{ redisError }}</span>
        </div>
        <div v-else-if="redisHealth" class="score-content">
          <HealthScoreGauge
            :score="redisHealth.redis_health_score"
            :grade="redisHealth.grade"
            :label="$t('analytics.codebase.intelligence.redisUsage')"
            :status-message="redisHealth.status_message"
          />
          <div class="score-details">
            <span class="detail-item warning" v-if="redisHealth.total_issues > 0">
              <Icon name="exclamation-triangle" /> {{ redisHealth.total_issues }} issues
            </span>
            <span class="detail-item info">
              <Icon name="file-code" /> {{ redisHealth.total_files }} files
            </span>
          </div>
          <button
            class="view-details-btn"
            @click="toggleRedisDetails"
            :disabled="redisOptimizationsLoading"
          >
            <i
              :class="
                redisOptimizationsLoading
                  ? 'fas fa-spinner fa-spin'
                  : showRedisDetails
                  ? 'chevron-up'
                  : 'chevron-down'
              "
            ></i>
            {{
              showRedisDetails
                ? $t('analytics.codebase.intelligence.hideDetails')
                : $t('analytics.codebase.intelligence.viewDetails')
            }}
          </button>
        </div>
        <div v-else class="score-empty">
          <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
        </div>
      </div>

      <!-- Health Score Card (#3073) -->
      <div class="score-card health-card">
        <div class="score-header">
          <Icon name="heartbeat" />
          <span>{{ $t('analytics.codebase.intelligence.healthScore') }}</span>
          <button
            @click="emit('load-health-score')"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshHealthScore')"
          >
            <Icon name="sync-alt" />
          </button>
        </div>
        <div v-if="healthScore" class="score-content">
          <HealthScoreGauge
            :score="healthScore.health_score"
            :grade="getHealthGrade(healthScore.health_score)"
            :label="$t('analytics.codebase.intelligence.healthScore')"
          />
          <div class="score-details">
            <span class="detail-item critical" v-if="healthScore.issues_count.critical > 0">
              <Icon name="times-circle" /> {{ healthScore.issues_count.critical }} critical
            </span>
            <span class="detail-item warning" v-if="healthScore.issues_count.high > 0">
              <Icon name="exclamation-circle" /> {{ healthScore.issues_count.high }} high
            </span>
            <span class="detail-item info">
              <Icon name="file-code" /> {{ healthScore.total_files }} files
            </span>
            <span class="detail-item info">
              <Icon name="clock" /> {{ healthScore.technical_debt_hours }}h debt
            </span>
          </div>
        </div>
        <div v-else class="score-empty">
          <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
        </div>
      </div>

      <!-- Quality Score Card (#3073) -->
      <div class="score-card quality-card">
        <div class="score-header">
          <Icon name="star" />
          <span>{{ $t('analytics.codebase.intelligence.qualityScore') }}</span>
          <button
            @click="emit('load-quality-score')"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshQualityScore')"
          >
            <Icon name="sync-alt" />
          </button>
        </div>
        <div v-if="qualityScore" class="score-content">
          <HealthScoreGauge
            :score="qualityScore.overall_score"
            :grade="qualityScore.grade"
            :label="$t('analytics.codebase.intelligence.qualityScore')"
          />
          <div class="quality-metrics">
            <div class="quality-metric">
              <span class="metric-label">Complexity</span>
              <div class="metric-bar">
                <div
                  class="metric-fill"
                  :style="{ width: qualityScore.metrics.complexity + '%' }"
                  :class="getScoreClass(qualityScore.metrics.complexity)"
                ></div>
              </div>
              <span class="metric-value">{{ qualityScore.metrics.complexity }}</span>
            </div>
            <div class="quality-metric">
              <span class="metric-label">Maintainability</span>
              <div class="metric-bar">
                <div
                  class="metric-fill"
                  :style="{ width: qualityScore.metrics.maintainability + '%' }"
                  :class="getScoreClass(qualityScore.metrics.maintainability)"
                ></div>
              </div>
              <span class="metric-value">{{ qualityScore.metrics.maintainability }}</span>
            </div>
            <div class="quality-metric">
              <span class="metric-label">Documentation</span>
              <div class="metric-bar">
                <div
                  class="metric-fill"
                  :style="{ width: qualityScore.metrics.documentation + '%' }"
                  :class="getScoreClass(qualityScore.metrics.documentation)"
                ></div>
              </div>
              <span class="metric-value">{{ qualityScore.metrics.documentation }}</span>
            </div>
            <div class="quality-metric">
              <span class="metric-label">Testing</span>
              <div class="metric-bar">
                <div
                  class="metric-fill"
                  :style="{ width: qualityScore.metrics.testing + '%' }"
                  :class="getScoreClass(qualityScore.metrics.testing)"
                ></div>
              </div>
              <span class="metric-value">{{ qualityScore.metrics.testing }}</span>
            </div>
            <div class="quality-metric">
              <span class="metric-label">Security</span>
              <div class="metric-bar">
                <div
                  class="metric-fill"
                  :style="{ width: qualityScore.metrics.security + '%' }"
                  :class="getScoreClass(qualityScore.metrics.security)"
                ></div>
              </div>
              <span class="metric-value">{{ qualityScore.metrics.security }}</span>
            </div>
          </div>
          <div class="quality-trend" :class="'trend-' + qualityScore.trend">
            <i
              :class="
                qualityScore.trend === 'improving'
                  ? 'arrow-up'
                  : qualityScore.trend === 'declining'
                  ? 'arrow-down'
                  : 'minus'
              "
            ></i>
            {{ qualityScore.trend }}
          </div>
        </div>
        <div v-else class="score-empty">
          <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
        </div>
      </div>
    </div>

    <!-- Expandable Security Findings Panel -->
    <div v-if="showSecurityDetails" class="findings-panel security-findings-panel">
      <div class="findings-header">
        <h4>
          <Icon name="shield-alt" />
          {{ $t('analytics.codebase.intelligence.securityFindings') }}
        </h4>
        <span class="findings-count">{{ securityFindings?.length ?? 0 }} findings</span>
      </div>
      <div v-if="securityFindingsLoading" class="findings-loading">
        <Icon name="spinner" class="animate-spin" />
        {{ $t('analytics.codebase.intelligence.loadingSecurityFindings') }}
      </div>
      <div v-else-if="!securityFindings?.length" class="findings-empty">
        <Icon name="check-circle" />
        {{ $t('analytics.codebase.intelligence.noSecurityVulnerabilities') }}
      </div>
      <div v-else class="findings-list">
        <div
          v-for="(finding, index) in securityFindings"
          :key="'sec-' + index"
          class="finding-item"
          :class="getSeverityClass(finding.severity)"
        >
          <div class="finding-header">
            <span class="finding-severity" :class="getSeverityClass(finding.severity)">
              {{ finding.severity }}
            </span>
            <span class="finding-type">{{ finding.vulnerability_type }}</span>
          </div>
          <div class="finding-description">{{ finding.description }}</div>
          <div class="finding-location">
            <Icon name="file-code" />
            {{ finding.file_path }}
            <span v-if="finding.line">:{{ finding.line }}</span>
          </div>
          <div v-if="finding.recommendation" class="finding-recommendation">
            <Icon name="lightbulb" /> {{ finding.recommendation }}
          </div>
          <div v-if="finding.owasp_category" class="finding-owasp">
            <Icon name="tag" /> OWASP: {{ finding.owasp_category }}
          </div>
        </div>
      </div>
    </div>

    <!-- Expandable Performance Findings Panel -->
    <div v-if="showPerformanceDetails" class="findings-panel performance-findings-panel">
      <div class="findings-header">
        <h4>
          <Icon name="tachometer-alt" />
          {{ $t('analytics.codebase.intelligence.performanceIssues') }}
        </h4>
        <span class="findings-count">{{ performanceFindings?.length ?? 0 }} issues</span>
      </div>
      <div v-if="performanceFindingsLoading" class="findings-loading">
        <Icon name="spinner" class="animate-spin" />
        {{ $t('analytics.codebase.intelligence.loadingPerformanceIssues') }}
      </div>
      <div v-else-if="!performanceFindings?.length" class="findings-empty">
        <Icon name="check-circle" />
        {{ $t('analytics.codebase.intelligence.noPerformanceIssues') }}
      </div>
      <div v-else class="findings-list">
        <div
          v-for="(finding, index) in performanceFindings"
          :key="'perf-' + index"
          class="finding-item"
          :class="getSeverityClass(finding.severity)"
        >
          <div class="finding-header">
            <span class="finding-severity" :class="getSeverityClass(finding.severity)">
              {{ finding.severity }}
            </span>
            <span class="finding-type">{{ finding.issue_type }}</span>
          </div>
          <div class="finding-description">{{ finding.description }}</div>
          <div class="finding-location">
            <Icon name="file-code" />
            {{ finding.file_path }}
            <span v-if="finding.line">:{{ finding.line }}</span>
            <span v-if="finding.function_name" class="function-name">
              in {{ finding.function_name }}()
            </span>
          </div>
          <div v-if="finding.recommendation" class="finding-recommendation">
            <Icon name="lightbulb" /> {{ finding.recommendation }}
          </div>
        </div>
      </div>
    </div>

    <!-- Expandable Redis Optimizations Panel -->
    <div v-if="showRedisDetails" class="findings-panel redis-findings-panel">
      <div class="findings-header">
        <h4>
          <Icon name="database" />
          {{ $t('analytics.codebase.intelligence.redisOptimizations') }}
        </h4>
        <span class="findings-count">{{ redisOptimizations?.length ?? 0 }} suggestions</span>
      </div>
      <div v-if="redisOptimizationsLoading" class="findings-loading">
        <Icon name="spinner" class="animate-spin" />
        {{ $t('analytics.codebase.intelligence.loadingRedisOptimizations') }}
      </div>
      <div v-else-if="!redisOptimizations?.length" class="findings-empty">
        <Icon name="check-circle" />
        {{ $t('analytics.codebase.intelligence.noRedisOptimizations') }}
      </div>
      <div v-else class="findings-list">
        <div
          v-for="(opt, index) in redisOptimizations"
          :key="'redis-' + index"
          class="finding-item"
          :class="getSeverityClass(opt.severity)"
        >
          <div class="finding-header">
            <span class="finding-severity" :class="getSeverityClass(opt.severity)">
              {{ opt.severity }}
            </span>
            <span class="finding-type">{{ opt.optimization_type }}</span>
            <span v-if="opt.category" class="finding-category">{{ opt.category }}</span>
          </div>
          <div class="finding-description">{{ opt.description }}</div>
          <div class="finding-location">
            <Icon name="file-code" />
            {{ opt.file_path }}
            <span v-if="opt.line">:{{ opt.line }}</span>
          </div>
          <div v-if="opt.recommendation" class="finding-recommendation">
            <Icon name="lightbulb" /> {{ opt.recommendation }}
          </div>
        </div>
      </div>
    </div>

    <!-- Suggestions Section (#3073) -->
    <div v-if="suggestions && suggestions.length > 0" class="suggestions-section">
      <h4>
        <Icon name="lightbulb" />
        {{ $t('analytics.codebase.intelligence.suggestionsTitle') }}
        <span class="suggestions-count">{{ suggestions.length }}</span>
      </h4>
      <div class="suggestions-list">
        <div
          v-for="suggestion in suggestions"
          :key="suggestion.id"
          class="suggestion-item"
          :class="'priority-' + suggestion.priority"
        >
          <div class="suggestion-header">
            <span class="suggestion-type-badge">{{ suggestion.type }}</span>
            <span class="suggestion-priority" :class="'priority-' + suggestion.priority">
              {{ suggestion.priority }}
            </span>
          </div>
          <div class="suggestion-title">{{ suggestion.title }}</div>
          <div class="suggestion-description">{{ suggestion.description }}</div>
          <div class="suggestion-impact">
            <Icon name="chart-line" /> {{ suggestion.impact }}
          </div>
        </div>
      </div>
    </div>

    <!-- Analysis History Section (#3073) -->
    <div v-if="analysisHistory && analysisHistory.length > 0" class="analysis-history-section">
      <h4>
        <Icon name="history" />
        {{ $t('analytics.codebase.intelligence.analysisHistoryTitle') }}
        <button
          @click="emit('load-analysis-history')"
          class="card-refresh-btn"
          style="margin-left: 8px;"
        >
          <Icon name="sync-alt" />
        </button>
      </h4>
      <div class="history-list">
        <div
          v-for="entry in analysisHistory"
          :key="entry.id"
          class="history-item"
        >
          <div class="history-meta">
            <span class="history-language">{{ entry.language }}</span>
            <span v-if="entry.filename" class="history-filename">{{ entry.filename }}</span>
          </div>
          <div class="history-score" :class="getScoreClass(entry.quality_score)">
            {{ entry.quality_score }}
          </div>
          <div class="history-time">{{ formatTimestamp(entry.timestamp) }}</div>
        </div>
      </div>
    </div>

    <EmptyState
      v-if="!rootPath && !securityScore && !performanceScore && !redisHealth"
      icon="shield-alt"
      :message="$t('analytics.codebase.intelligence.noScoresData')"
    />
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import HealthScoreGauge from '@/components/analytics/HealthScoreGauge.vue'

interface SecurityScoreResult {
  security_score: number
  grade: string
  risk_level: string
  status_message: string
  total_findings: number
  critical_issues: number
  high_issues: number
  files_analyzed: number
  severity_breakdown: Record<string, number>
  owasp_breakdown: Record<string, number>
}

interface PerformanceScoreResult {
  performance_score: number
  grade: string
  status_message: string
  total_issues: number
  files_analyzed: number
}

interface RedisHealthResult {
  redis_health_score: number
  grade: string
  status_message: string
  total_files: number
  total_issues: number
  files_with_issues: number
}

interface SecurityFindingDetail {
  severity: string
  vulnerability_type: string
  description: string
  file_path: string
  line?: number
  recommendation?: string
  owasp_category?: string
}

interface PerformanceFindingDetail {
  severity: string
  issue_type: string
  description: string
  file_path: string
  line?: number
  function_name?: string
  recommendation?: string
}

interface RedisOptimization {
  severity: string
  optimization_type: string
  description: string
  file_path: string
  line?: number
  category?: string
  recommendation?: string
}

interface CodeHealthScore {
  health_score: number
  total_files: number
  issues_count: {
    critical: number
    high: number
    medium: number
    low: number
  }
  coverage_percent: number
  technical_debt_hours: number
  timestamp: string
}

interface QualityScore {
  overall_score: number
  metrics: {
    complexity: number
    maintainability: number
    documentation: number
    testing: number
    security: number
  }
  grade: string
  trend: 'improving' | 'stable' | 'declining'
}

interface CodeSuggestion {
  id: string
  type: string
  priority: 'high' | 'medium' | 'low'
  title: string
  description: string
  impact: string
}

interface CodeAnalysisResult {
  id: string
  language: string
  filename?: string
  quality_score: number
  timestamp: string
}

const props = defineProps<{
  rootPath: string
  securityScore: SecurityScoreResult | null
  securityLoading: boolean
  securityError: string
  securityFindings: SecurityFindingDetail[] | null
  securityFindingsLoading: boolean
  performanceScore: PerformanceScoreResult | null
  performanceLoading: boolean
  performanceError: string
  performanceFindings: PerformanceFindingDetail[] | null
  performanceFindingsLoading: boolean
  redisHealth: RedisHealthResult | null
  redisLoading: boolean
  redisError: string
  redisOptimizations: RedisOptimization[] | null
  redisOptimizationsLoading: boolean
  healthScore: CodeHealthScore | null
  qualityScore: QualityScore | null
  suggestions: CodeSuggestion[]
  analysisHistory: CodeAnalysisResult[]
}>()

const emit = defineEmits<{
  'refresh-all': []
  'refresh-security': []
  'refresh-performance': []
  'refresh-redis': []
  'load-security-findings': []
  'load-performance-findings': []
  'load-redis-optimizations': []
  'load-health-score': []
  'load-quality-score': []
  'load-analysis-history': []
}>()

const showSecurityDetails = ref(false)
const showPerformanceDetails = ref(false)
const showRedisDetails = ref(false)

function toggleSecurityDetails(): void {
  showSecurityDetails.value = !showSecurityDetails.value
  if (showSecurityDetails.value && !props.securityFindings?.length) {
    emit('load-security-findings')
  }
}

function togglePerformanceDetails(): void {
  showPerformanceDetails.value = !showPerformanceDetails.value
  if (showPerformanceDetails.value && !props.performanceFindings?.length) {
    emit('load-performance-findings')
  }
}

function toggleRedisDetails(): void {
  showRedisDetails.value = !showRedisDetails.value
  if (showRedisDetails.value && !props.redisOptimizations?.length) {
    emit('load-redis-optimizations')
  }
}

function getScoreClass(score: number): string {
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-medium'
  return 'score-low'
}

function getSeverityClass(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'severity-critical'
    case 'high': return 'severity-high'
    case 'medium': return 'severity-medium'
    case 'low': return 'severity-low'
    default: return 'severity-info'
  }
}

function getHealthGrade(score: number): string {
  if (score >= 90) return 'A+'
  if (score >= 80) return 'A'
  if (score >= 70) return 'B'
  if (score >= 60) return 'C'
  if (score >= 50) return 'D'
  return 'F'
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.code-intelligence-scores-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  contain: layout style;}

.code-intelligence-scores-section h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--text-primary);
  margin-bottom: var(--spacing-5);
  font-size: 1.2em;
  font-weight: 600;
}

.code-intelligence-scores-section h3 i {
  color: var(--chart-blue);
}

/* Score Cards Grid */
.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-5);
}

.score-card {
  background: rgba(17, 24, 39, 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  border: 1px solid rgba(71, 85, 105, 0.4);
  transition: all var(--duration-200) var(--ease-out);
}

.score-card:hover {
  border-color: rgba(71, 85, 105, 0.7);
  background: rgba(17, 24, 39, 0.8);
}

.score-card .score-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-4);
  font-size: 1.1em;
  font-weight: 600;
  color: var(--text-secondary);
}

.score-card .score-header .card-refresh-btn {
  margin-left: auto;
  padding: var(--spacing-1) var(--spacing-2);
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: var(--radius-default);
  color: var(--color-info-light);
  cursor: pointer;
  font-size: 0.8em;
  transition: all var(--duration-200) var(--ease-out);
}

.score-card .score-header .card-refresh-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.5);
  color: var(--color-info);
}

.score-card .score-header .card-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.score-card.security-card .score-header i { color: var(--color-error); }
.score-card.performance-card .score-header i { color: var(--color-warning); }
.score-card.redis-card .score-header i { color: var(--chart-green); }
.score-card.health-card .score-header i { color: var(--color-error-light); }
.score-card.quality-card .score-header i { color: var(--chart-indigo); }

.score-card .score-loading {
  display: flex;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--color-info-light);
  font-size: 1.5em;
}

.score-card .score-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: rgba(239, 68, 68, 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-error-light);
  font-size: 0.85em;
}

.score-card .score-error i { color: var(--color-error); }

.score-card .score-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.score-card .score-details {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  justify-content: center;
  margin-top: var(--spacing-2);
}

.score-card .detail-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-default);
  font-size: 0.8em;
}

.score-card .detail-item.critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.score-card .detail-item.warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.score-card .detail-item.info {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
}

.score-card .score-empty {
  display: flex;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  font-style: italic;
}

/* Quality Metrics (#3073) */
.quality-metrics {
  width: 100%;
  margin-top: var(--spacing-3);
}

.quality-metric {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1-5);
}

.quality-metric .metric-label {
  width: 110px;
  font-size: 0.8em;
  color: var(--text-muted);
  text-align: right;
}

.quality-metric .metric-bar {
  flex: 1;
  height: 6px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.quality-metric .metric-fill {
  height: 100%;
  border-radius: var(--radius-default);
  transition: width var(--duration-500) var(--ease-out);
}

.quality-metric .metric-fill.score-high { background: var(--chart-green); }
.quality-metric .metric-fill.score-medium { background: var(--color-warning); }
.quality-metric .metric-fill.score-low { background: var(--color-error); }

.quality-metric .metric-value {
  width: 30px;
  font-size: 0.8em;
  color: var(--text-secondary);
  font-weight: 600;
}

.quality-trend {
  margin-top: var(--spacing-2);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-default);
  font-size: 0.8em;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.quality-trend.trend-improving {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-success-light);
}

.quality-trend.trend-stable {
  background: rgba(59, 130, 246, 0.15);
  color: var(--color-info-light);
}

.quality-trend.trend-declining {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error-light);
}

/* Suggestions Section (#3073) */
.suggestions-section {
  margin-top: var(--spacing-6);
  padding: var(--spacing-5);
  background: rgba(30, 41, 59, 0.4);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.suggestions-section h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
  font-size: 1.05em;
  font-weight: 600;
}

.suggestions-section h4 i { color: var(--color-warning); }

.suggestions-count {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: rgba(245, 158, 11, 0.2);
  border-radius: var(--radius-xl);
  font-size: 0.75em;
  color: var(--color-warning-light);
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.suggestion-item {
  padding: var(--spacing-3-5) var(--spacing-4);
  background: rgba(17, 24, 39, 0.5);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--text-tertiary);
}

.suggestion-item.priority-high { border-left-color: var(--color-error); }
.suggestion-item.priority-medium { border-left-color: var(--color-warning); }
.suggestion-item.priority-low { border-left-color: var(--chart-green); }

.suggestion-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1-5);
}

.suggestion-type-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-default);
  font-size: 0.75em;
  color: var(--chart-indigo-light);
  text-transform: capitalize;
}

.suggestion-priority {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.7em;
  font-weight: 600;
  text-transform: uppercase;
}

.suggestion-priority.priority-high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.suggestion-priority.priority-medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.suggestion-priority.priority-low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.suggestion-title {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.95em;
  margin-bottom: var(--spacing-1);
}

.suggestion-description {
  color: var(--text-secondary);
  font-size: 0.85em;
  line-height: 1.5;
  margin-bottom: var(--spacing-1-5);
}

.suggestion-impact {
  font-size: 0.8em;
  color: var(--text-muted);
}

.suggestion-impact i {
  color: var(--chart-green);
  margin-right: var(--spacing-1);
}

/* Analysis History Section (#3073) */
.analysis-history-section {
  margin-top: var(--spacing-6);
  padding: var(--spacing-5);
  background: rgba(30, 41, 59, 0.4);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.analysis-history-section h4 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
  font-size: 1.05em;
  font-weight: 600;
}

.analysis-history-section h4 i { color: var(--chart-blue); }

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  max-height: 300px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: rgba(17, 24, 39, 0.5);
  border-radius: var(--radius-md);
  transition: background var(--duration-200) var(--ease-out);
}

.history-item:hover {
  background: rgba(17, 24, 39, 0.8);
}

.history-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
}

.history-language {
  font-size: 0.85em;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}

.history-filename {
  font-size: 0.75em;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.history-score {
  font-size: 1.2em;
  font-weight: 700;
  min-width: 40px;
  text-align: center;
}

.history-score.score-high { color: var(--chart-green); }
.history-score.score-medium { color: var(--color-warning); }
.history-score.score-low { color: var(--color-error); }

.history-time {
  font-size: 0.75em;
  color: var(--text-tertiary);
  white-space: nowrap;
}

/* View Details Button */
.view-details-btn {
  width: 100%;
  margin-top: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-4);
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(99, 102, 241, 0.4);
  border-radius: var(--radius-md);
  color: var(--chart-indigo-light);
  font-size: 0.85em;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-out);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
}

.view-details-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.3);
  border-color: rgba(99, 102, 241, 0.6);
  color: var(--chart-indigo-light);
}

.view-details-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Findings Panel Styles */
.findings-panel {
  margin-top: var(--spacing-4);
  background: rgba(30, 41, 59, 0.6);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
  overflow: hidden;
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    max-height: 2000px;
    transform: translateY(0);
  }
}

.findings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  background: rgba(30, 41, 59, 0.8);
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.findings-header h4 {
  margin: var(--spacing-0);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-primary);
  font-size: 1.1em;
  font-weight: 600;
}

.security-findings-panel .findings-header h4 i { color: var(--color-error-light); }
.performance-findings-panel .findings-header h4 i { color: var(--color-warning-light); }
.redis-findings-panel .findings-header h4 i { color: var(--color-info); }

.findings-count {
  padding: var(--spacing-1) var(--spacing-3);
  background: rgba(71, 85, 105, 0.5);
  border-radius: var(--radius-2xl);
  color: var(--text-muted);
  font-size: 0.85em;
  font-weight: 500;
}

.findings-loading,
.findings-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-10) var(--spacing-5);
  color: var(--text-muted);
  font-size: 0.95em;
}

.findings-empty i {
  color: var(--chart-green);
  font-size: 1.2em;
}

.findings-list {
  padding: var(--spacing-3);
  max-height: 500px;
  overflow-y: auto;
}

.finding-item {
  background: rgba(15, 23, 42, 0.6);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5) var(--spacing-4);
  margin-bottom: var(--spacing-2-5);
  border-left: 4px solid var(--text-tertiary);
  transition: all var(--duration-200) var(--ease-out);
}

.finding-item:last-child { margin-bottom: var(--spacing-0); }
.finding-item:hover { background: rgba(15, 23, 42, 0.8); }

.finding-item.severity-critical {
  border-left-color: var(--color-error);
  background: rgba(239, 68, 68, 0.08);
}

.finding-item.severity-high {
  border-left-color: var(--chart-orange);
  background: rgba(249, 115, 22, 0.08);
}

.finding-item.severity-medium {
  border-left-color: var(--color-warning);
  background: rgba(234, 179, 8, 0.08);
}

.finding-item.severity-low {
  border-left-color: var(--chart-green);
  background: rgba(34, 197, 94, 0.08);
}

.finding-item.severity-info {
  border-left-color: var(--chart-blue);
  background: rgba(59, 130, 246, 0.08);
}

.finding-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-2);
  flex-wrap: wrap;
}

.finding-severity {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.75em;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.finding-severity.severity-critical {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.finding-severity.severity-high {
  background: rgba(249, 115, 22, 0.3);
  color: var(--chart-orange-light);
}

.finding-severity.severity-medium {
  background: rgba(234, 179, 8, 0.3);
  color: var(--color-warning-light);
}

.finding-severity.severity-low {
  background: rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.finding-severity.severity-info {
  background: rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.finding-type {
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 0.9em;
}

.finding-category {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: rgba(71, 85, 105, 0.5);
  border-radius: var(--radius-default);
  font-size: 0.75em;
  color: var(--text-muted);
}

.finding-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  line-height: 1.5;
  margin-bottom: var(--spacing-2-5);
}

.finding-location {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  color: var(--text-tertiary);
  font-size: 0.85em;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.finding-location i { color: var(--chart-indigo); }

.finding-location .function-name {
  color: var(--chart-indigo-light);
  font-style: italic;
}

.finding-recommendation {
  margin-top: var(--spacing-2-5);
  padding: var(--spacing-2-5) var(--spacing-3);
  background: rgba(34, 197, 94, 0.1);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--chart-green);
  color: var(--color-success-light);
  font-size: 0.85em;
  line-height: 1.4;
}

.finding-recommendation i {
  color: var(--chart-green);
  margin-right: var(--spacing-1-5);
}

.finding-owasp {
  margin-top: var(--spacing-2);
  color: var(--text-muted);
  font-size: 0.8em;
}

.finding-owasp i {
  color: var(--chart-orange);
  margin-right: var(--spacing-1);
}
</style>
