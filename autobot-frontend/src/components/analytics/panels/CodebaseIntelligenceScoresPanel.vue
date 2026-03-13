<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #1469: Extracted from CodebaseAnalytics.vue — Code Intelligence Scores section (#538,#566) -->
<template>
  <div class="code-intelligence-scores-section analytics-section">
    <h3>
      <i class="fas fa-shield-alt"></i> {{ $t('analytics.codebase.intelligence.scoresTitle') }}
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
              : 'fas fa-sync-alt'
          "
        ></i>
      </button>
    </h3>

    <div class="scores-grid">
      <!-- Security Score Card -->
      <div class="score-card security-card">
        <div class="score-header">
          <i class="fas fa-shield-alt"></i>
          <span>{{ $t('analytics.codebase.intelligence.security') }}</span>
          <button
            @click="emit('refresh-security')"
            :disabled="securityLoading"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshSecurity')"
          >
            <i :class="securityLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>
        <div v-if="securityLoading" class="score-loading">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
        <div v-else-if="securityError" class="score-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ securityError }}</span>
        </div>
        <div v-else-if="securityScore" class="score-content">
          <div class="score-value" :class="getScoreClass(securityScore.security_score)">
            {{ securityScore.security_score }}
          </div>
          <div class="score-grade" :class="getGradeClass(securityScore.grade)">
            {{ securityScore.grade }}
          </div>
          <div class="score-status">{{ securityScore.status_message }}</div>
          <div class="score-details">
            <span class="detail-item critical" v-if="securityScore.critical_issues > 0">
              <i class="fas fa-times-circle"></i> {{ securityScore.critical_issues }} critical
            </span>
            <span class="detail-item warning" v-if="securityScore.high_issues > 0">
              <i class="fas fa-exclamation-circle"></i> {{ securityScore.high_issues }} high
            </span>
            <span class="detail-item info">
              <i class="fas fa-file-code"></i> {{ securityScore.files_analyzed }} files
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
                  ? 'fas fa-chevron-up'
                  : 'fas fa-chevron-down'
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
          <i class="fas fa-tachometer-alt"></i>
          <span>{{ $t('analytics.codebase.intelligence.performanceLabel') }}</span>
          <button
            @click="emit('refresh-performance')"
            :disabled="performanceLoading"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshPerformance')"
          >
            <i :class="performanceLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>
        <div v-if="performanceLoading" class="score-loading">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
        <div v-else-if="performanceError" class="score-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ performanceError }}</span>
        </div>
        <div v-else-if="performanceScore" class="score-content">
          <div class="score-value" :class="getScoreClass(performanceScore.performance_score)">
            {{ performanceScore.performance_score }}
          </div>
          <div class="score-grade" :class="getGradeClass(performanceScore.grade)">
            {{ performanceScore.grade }}
          </div>
          <div class="score-status">{{ performanceScore.status_message }}</div>
          <div class="score-details">
            <span class="detail-item warning" v-if="performanceScore.total_issues > 0">
              <i class="fas fa-exclamation-triangle"></i> {{ performanceScore.total_issues }} issues
            </span>
            <span class="detail-item info">
              <i class="fas fa-file-code"></i> {{ performanceScore.files_analyzed }} files
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
                  ? 'fas fa-chevron-up'
                  : 'fas fa-chevron-down'
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
          <i class="fas fa-database"></i>
          <span>{{ $t('analytics.codebase.intelligence.redisUsage') }}</span>
          <button
            @click="emit('refresh-redis')"
            :disabled="redisLoading"
            class="card-refresh-btn"
            :title="$t('analytics.codebase.intelligence.refreshRedis')"
          >
            <i :class="redisLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>
        <div v-if="redisLoading" class="score-loading">
          <i class="fas fa-spinner fa-spin"></i>
        </div>
        <div v-else-if="redisError" class="score-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ redisError }}</span>
        </div>
        <div v-else-if="redisHealth" class="score-content">
          <div class="score-value" :class="getScoreClass(redisHealth.redis_health_score)">
            {{ redisHealth.redis_health_score }}
          </div>
          <div class="score-grade" :class="getGradeClass(redisHealth.grade)">
            {{ redisHealth.grade }}
          </div>
          <div class="score-status">{{ redisHealth.status_message }}</div>
          <div class="score-details">
            <span class="detail-item warning" v-if="redisHealth.total_issues > 0">
              <i class="fas fa-exclamation-triangle"></i> {{ redisHealth.total_issues }} issues
            </span>
            <span class="detail-item info">
              <i class="fas fa-file-code"></i> {{ redisHealth.total_files }} files
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
                  ? 'fas fa-chevron-up'
                  : 'fas fa-chevron-down'
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
    </div>

    <!-- Expandable Security Findings Panel -->
    <div v-if="showSecurityDetails" class="findings-panel security-findings-panel">
      <div class="findings-header">
        <h4>
          <i class="fas fa-shield-alt"></i>
          {{ $t('analytics.codebase.intelligence.securityFindings') }}
        </h4>
        <span class="findings-count">{{ securityFindings?.length ?? 0 }} findings</span>
      </div>
      <div v-if="securityFindingsLoading" class="findings-loading">
        <i class="fas fa-spinner fa-spin"></i>
        {{ $t('analytics.codebase.intelligence.loadingSecurityFindings') }}
      </div>
      <div v-else-if="!securityFindings?.length" class="findings-empty">
        <i class="fas fa-check-circle"></i>
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
            <i class="fas fa-file-code"></i>
            {{ finding.file_path }}
            <span v-if="finding.line">:{{ finding.line }}</span>
          </div>
          <div v-if="finding.recommendation" class="finding-recommendation">
            <i class="fas fa-lightbulb"></i> {{ finding.recommendation }}
          </div>
          <div v-if="finding.owasp_category" class="finding-owasp">
            <i class="fas fa-tag"></i> OWASP: {{ finding.owasp_category }}
          </div>
        </div>
      </div>
    </div>

    <!-- Expandable Performance Findings Panel -->
    <div v-if="showPerformanceDetails" class="findings-panel performance-findings-panel">
      <div class="findings-header">
        <h4>
          <i class="fas fa-tachometer-alt"></i>
          {{ $t('analytics.codebase.intelligence.performanceIssues') }}
        </h4>
        <span class="findings-count">{{ performanceFindings?.length ?? 0 }} issues</span>
      </div>
      <div v-if="performanceFindingsLoading" class="findings-loading">
        <i class="fas fa-spinner fa-spin"></i>
        {{ $t('analytics.codebase.intelligence.loadingPerformanceIssues') }}
      </div>
      <div v-else-if="!performanceFindings?.length" class="findings-empty">
        <i class="fas fa-check-circle"></i>
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
            <i class="fas fa-file-code"></i>
            {{ finding.file_path }}
            <span v-if="finding.line">:{{ finding.line }}</span>
            <span v-if="finding.function_name" class="function-name">
              in {{ finding.function_name }}()
            </span>
          </div>
          <div v-if="finding.recommendation" class="finding-recommendation">
            <i class="fas fa-lightbulb"></i> {{ finding.recommendation }}
          </div>
        </div>
      </div>
    </div>

    <!-- Expandable Redis Optimizations Panel -->
    <div v-if="showRedisDetails" class="findings-panel redis-findings-panel">
      <div class="findings-header">
        <h4>
          <i class="fas fa-database"></i>
          {{ $t('analytics.codebase.intelligence.redisOptimizations') }}
        </h4>
        <span class="findings-count">{{ redisOptimizations?.length ?? 0 }} suggestions</span>
      </div>
      <div v-if="redisOptimizationsLoading" class="findings-loading">
        <i class="fas fa-spinner fa-spin"></i>
        {{ $t('analytics.codebase.intelligence.loadingRedisOptimizations') }}
      </div>
      <div v-else-if="!redisOptimizations?.length" class="findings-empty">
        <i class="fas fa-check-circle"></i>
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
            <i class="fas fa-file-code"></i>
            {{ opt.file_path }}
            <span v-if="opt.line">:{{ opt.line }}</span>
          </div>
          <div v-if="opt.recommendation" class="finding-recommendation">
            <i class="fas fa-lightbulb"></i> {{ opt.recommendation }}
          </div>
        </div>
      </div>
    </div>

    <EmptyState
      v-if="!rootPath && !securityScore && !performanceScore && !redisHealth"
      icon="fas fa-shield-alt"
      :message="$t('analytics.codebase.intelligence.noScoresData')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'

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
  category?: string
  description: string
  file_path: string
  line?: number
  recommendation?: string
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
}>()

const emit = defineEmits<{
  'refresh-all': []
  'refresh-security': []
  'refresh-performance': []
  'refresh-redis': []
  'load-security-findings': []
  'load-performance-findings': []
  'load-redis-optimizations': []
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

function getGradeClass(grade: string): string {
  const g = grade?.toUpperCase() || ''
  if (g === 'A' || g === 'A+') return 'grade-a'
  if (g === 'B' || g === 'B+') return 'grade-b'
  if (g === 'C' || g === 'C+') return 'grade-c'
  if (g === 'D' || g === 'D+') return 'grade-d'
  return 'grade-f'
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
</script>

<style scoped>
.code-intelligence-scores-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.code-intelligence-scores-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 20px;
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
  gap: 20px;
}

.score-card {
  background: rgba(17, 24, 39, 0.6);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(71, 85, 105, 0.4);
  transition: all 0.2s ease;
}

.score-card:hover {
  border-color: rgba(71, 85, 105, 0.7);
  background: rgba(17, 24, 39, 0.8);
}

.score-card .score-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  font-size: 1.1em;
  font-weight: 600;
  color: var(--text-secondary);
}

.score-card .score-header .card-refresh-btn {
  margin-left: auto;
  padding: 4px 8px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 4px;
  color: var(--color-info-light);
  cursor: pointer;
  font-size: 0.8em;
  transition: all 0.2s ease;
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

.score-card.security-card .score-header i {
  color: var(--color-error);
}

.score-card.performance-card .score-header i {
  color: var(--color-warning);
}

.score-card.redis-card .score-header i {
  color: var(--chart-green);
}

.score-card .score-loading {
  display: flex;
  justify-content: center;
  padding: 30px;
  color: var(--color-info-light);
  font-size: 1.5em;
}

.score-card .score-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 8px;
  color: var(--color-error-light);
  font-size: 0.85em;
}

.score-card .score-error i {
  color: var(--color-error);
}

.score-card .score-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.score-card .score-value {
  font-size: 3em;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 8px;
}

.score-card .score-value.score-high {
  color: var(--chart-green);
}

.score-card .score-value.score-medium {
  color: var(--color-warning);
}

.score-card .score-value.score-low {
  color: var(--color-error);
}

.score-card .score-grade {
  font-size: 1.5em;
  font-weight: 700;
  padding: 4px 16px;
  border-radius: 8px;
  margin-bottom: 10px;
}

.score-card .score-grade.grade-a {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.score-card .score-grade.grade-b {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-success-light);
}

.score-card .score-grade.grade-c {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.score-card .score-grade.grade-d {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error-light);
}

.score-card .score-grade.grade-f {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.score-card .score-status {
  color: var(--text-muted);
  font-size: 0.9em;
  margin-bottom: 12px;
}

.score-card .score-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.score-card .detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 4px;
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
  padding: 30px;
  color: var(--text-tertiary);
  font-style: italic;
}

/* Issue #566: View Details Button */
.view-details-btn {
  width: 100%;
  margin-top: 12px;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(99, 102, 241, 0.4);
  border-radius: 6px;
  color: var(--chart-indigo-light);
  font-size: 0.85em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
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

/* Issue #566: Findings Panel Styles */
.findings-panel {
  margin-top: 16px;
  background: rgba(30, 41, 59, 0.6);
  border-radius: 12px;
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
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.8);
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.findings-header h4 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 1.1em;
  font-weight: 600;
}

.security-findings-panel .findings-header h4 i { color: var(--color-error-light); }
.performance-findings-panel .findings-header h4 i { color: var(--color-warning-light); }
.redis-findings-panel .findings-header h4 i { color: var(--color-info); }

.findings-count {
  padding: 4px 12px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 20px;
  color: var(--text-muted);
  font-size: 0.85em;
  font-weight: 500;
}

.findings-loading,
.findings-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: var(--text-muted);
  font-size: 0.95em;
}

.findings-empty i {
  color: var(--chart-green);
  font-size: 1.2em;
}

.findings-list {
  padding: 12px;
  max-height: 500px;
  overflow-y: auto;
}

.finding-item {
  background: rgba(15, 23, 42, 0.6);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 10px;
  border-left: 4px solid var(--text-tertiary);
  transition: all 0.2s ease;
}

.finding-item:last-child {
  margin-bottom: 0;
}

.finding-item:hover {
  background: rgba(15, 23, 42, 0.8);
}

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
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.finding-severity {
  padding: 2px 8px;
  border-radius: 4px;
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
  padding: 2px 8px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 4px;
  font-size: 0.75em;
  color: var(--text-muted);
}

.finding-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  line-height: 1.5;
  margin-bottom: 10px;
}

.finding-location {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-tertiary);
  font-size: 0.85em;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.finding-location i {
  color: var(--chart-indigo);
}

.finding-location .function-name {
  color: var(--chart-indigo-light);
  font-style: italic;
}

.finding-recommendation {
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 6px;
  border-left: 3px solid var(--chart-green);
  color: var(--color-success-light);
  font-size: 0.85em;
  line-height: 1.4;
}

.finding-recommendation i {
  color: var(--chart-green);
  margin-right: 6px;
}

.finding-owasp {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 0.8em;
}

.finding-owasp i {
  color: var(--chart-orange);
  margin-right: 4px;
}

/* Issue #538: Environment Analysis Section */

</style>
