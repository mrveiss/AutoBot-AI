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
