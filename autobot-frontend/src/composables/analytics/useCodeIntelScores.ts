// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeIntelScores
 *
 * Security, performance, and Redis health scores plus detailed findings
 * and toggle logic. Extracted from useCodeIntelAnalysis (Issue #2260).
 * Migrated from useAnalyticsFetch to useFetchEndpoint (Issue #5208).
 *
 * /code-intelligence/* endpoints are NOT source-scoped (they take the raw
 * repo path directly), so every migrated endpoint keeps the default
 * `scopeToSource: false`.
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  SecurityScoreResult,
  PerformanceScoreResult,
  RedisHealthResult,
  SecurityFindingDetail,
  PerformanceFindingDetail,
  RedisOptimization,
} from './codeIntelTypes'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useCodeIntelScores')

interface PerfScoreRaw {
  status: string
  performance_score?: number
  grade?: string
  status_message?: string
  total_issues?: number
  files_analyzed?: number
  severity_breakdown?: Record<string, number>
  issue_type_breakdown?: Record<string, number>
}

interface FindingsRaw<T> {
  status: string
  findings?: T[]
}

export function useCodeIntelScores(deps: UseCodeIntelAnalysisDeps) {
  const { rootPath, withSourceId } = deps

  // --- Security score (useTaskLoader — polling, different pattern) ---

  const {
    data: securityScore,
    loading: loadingSecurityScore,
    error: securityScoreError,
    load: _loadSecurityScoreTask,
  } = useTaskLoader<SecurityScoreResult>(
    `${getApiBase()}/code-intelligence/security/score`,
    (r) => {
      if (r.status === 'success') {
        return {
          security_score: (r.security_score as number) || 0,
          grade: (r.grade as string) || 'N/A',
          risk_level: (r.risk_level as string) || 'unknown',
          status_message: (r.status_message as string) || '',
          total_findings: (r.total_findings as number) || 0,
          critical_issues: (r.critical_issues as number) || 0,
          high_issues: (r.high_issues as number) || 0,
          files_analyzed: (r.files_analyzed as number) || 0,
          severity_breakdown:
            (r.severity_breakdown as Record<string, number>) || {},
          owasp_breakdown:
            (r.owasp_breakdown as Record<string, number>) || {},
        }
      }
      return undefined
    },
  )

  // --- Performance score (GET; scopeToSource: false for /code-intelligence/*) ---

  const performanceScoreEndpoint = useFetchEndpoint<
    PerfScoreRaw,
    PerformanceScoreResult
  >({
    path: '/api/code-intelligence/performance/score',
    pickData: (r) =>
      r.status === 'success'
        ? {
            performance_score: r.performance_score ?? 0,
            grade: r.grade ?? 'N/A',
            status_message: r.status_message ?? '',
            total_issues: r.total_issues ?? 0,
            files_analyzed: r.files_analyzed ?? 0,
            severity_breakdown: r.severity_breakdown ?? {},
            issue_type_breakdown: r.issue_type_breakdown ?? {},
          }
        : null,
  })

  // --- Redis health (hand-rolled — complex 504 timeout handling, not migrated) ---

  const redisHealth = ref<RedisHealthResult | null>(null)
  const loadingRedisHealth = ref(false)
  const redisHealthError = ref('')

  // --- Detailed findings (POST with body factory) ---

  const securityFindingsEndpoint = useFetchEndpoint<
    FindingsRaw<SecurityFindingDetail>,
    SecurityFindingDetail[]
  >({
    path: '/api/code-intelligence/security/analyze',
    method: 'POST',
    body: () => ({ path: rootPath.value }),
    pickData: (r) => (r.status === 'success' && r.findings ? r.findings : []),
  })
  const showSecurityDetails = ref(false)

  const performanceFindingsEndpoint = useFetchEndpoint<
    FindingsRaw<PerformanceFindingDetail>,
    PerformanceFindingDetail[]
  >({
    path: '/api/code-intelligence/performance/analyze',
    method: 'POST',
    body: () => ({ path: rootPath.value }),
    pickData: (r) => (r.status === 'success' && r.findings ? r.findings : []),
  })
  const showPerformanceDetails = ref(false)

  const redisOptimizationsEndpoint = useFetchEndpoint<
    FindingsRaw<RedisOptimization>,
    RedisOptimization[]
  >({
    path: '/api/code-intelligence/redis/analyze',
    method: 'POST',
    body: () => ({ path: rootPath.value }),
    pickData: (r) => (r.status === 'success' && r.findings ? r.findings : []),
  })
  const showRedisDetails = ref(false)

  // --- Score loaders ---

  const loadSecurityScore = async () => {
    if (!rootPath.value) return
    await _loadSecurityScoreTask(undefined, { path: rootPath.value })
  }

  const loadPerformanceScore = async () => {
    if (!rootPath.value) return
    await performanceScoreEndpoint.load({ path: rootPath.value })
  }

  const loadRedisHealth = async () => {
    if (!rootPath.value) return
    if (
      rootPath.value === '/opt/autobot' ||
      rootPath.value.includes('/data/code-sources/')
    ) {
      logger.debug(
        'Skipping Redis health scan for large/remote path:',
        rootPath.value,
      )
      return
    }
    loadingRedisHealth.value = true
    redisHealthError.value = ''
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const url = withSourceId(
        `${backendUrl}/api/code-intelligence/redis/health-score?path=${encodeURIComponent(rootPath.value)}`,
      )
      const response = await fetchWithAuth(url, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        if (response.status === 504) {
          throw new Error(
            'Analysis timed out -- codebase too large for real-time scan',
          )
        }
        const detail = await response.json().catch(() => null)
        throw new Error(
          detail?.detail ||
            `Redis health endpoint returned ${response.status}`,
        )
      }
      const data = await response.json()
      if (data.status === 'success') {
        redisHealth.value = {
          redis_health_score:
            data.health_score ?? data.redis_health_score ?? 0,
          grade: data.grade || 'N/A',
          status_message: data.status_message || '',
          total_files: data.total_files || 0,
          total_issues:
            data.total_optimizations || data.total_issues || 0,
          files_with_issues: data.files_with_issues || 0,
        }
      } else if (data.status === 'no_data') {
        redisHealth.value = null
        logger.debug('No Redis health data - run indexing first')
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Failed to load Redis health:', error)
      redisHealthError.value = errorMessage
    } finally {
      loadingRedisHealth.value = false
    }
  }

  // --- Detailed findings loaders ---

  const loadSecurityFindings = async () => {
    if (!rootPath.value) return
    await securityFindingsEndpoint.load()
  }

  const loadPerformanceFindings = async () => {
    if (!rootPath.value) return
    await performanceFindingsEndpoint.load()
  }

  const loadRedisOptimizations = async () => {
    if (!rootPath.value) return
    await redisOptimizationsEndpoint.load()
  }

  // --- Toggle functions ---

  const toggleSecurityDetails = async () => {
    showSecurityDetails.value = !showSecurityDetails.value
    if (
      showSecurityDetails.value &&
      !securityFindingsEndpoint.data.value?.length
    ) {
      await loadSecurityFindings()
    }
  }

  const togglePerformanceDetails = async () => {
    showPerformanceDetails.value = !showPerformanceDetails.value
    if (
      showPerformanceDetails.value &&
      !performanceFindingsEndpoint.data.value?.length
    ) {
      await loadPerformanceFindings()
    }
  }

  const toggleRedisDetails = async () => {
    showRedisDetails.value = !showRedisDetails.value
    if (
      showRedisDetails.value &&
      !redisOptimizationsEndpoint.data.value?.length
    ) {
      await loadRedisOptimizations()
    }
  }

  // --- Cached security score loader (hand-rolled — out of scope) ---

  const loadCachedSecurityScore = async () => {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      `${backendUrl}/api/code-intelligence/security/score/cached`,
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.security_score !== undefined) {
      securityScore.value = {
        security_score: data.security_score ?? 0,
        grade: data.grade ?? 'N/A',
        risk_level: data.risk_level ?? 'unknown',
        status_message: data.status_message ?? '',
        total_findings: data.total_findings ?? 0,
        critical_issues: data.critical_issues ?? 0,
        high_issues: data.high_issues ?? 0,
        files_analyzed: data.files_analyzed ?? 0,
        severity_breakdown: data.severity_breakdown ?? {},
        owasp_breakdown: data.owasp_breakdown ?? {},
      }
    }
  }

  return {
    // Scores
    securityScore,
    loadingSecurityScore,
    securityScoreError,
    performanceScore: performanceScoreEndpoint.data,
    loadingPerformanceScore: performanceScoreEndpoint.loading,
    performanceScoreError: performanceScoreEndpoint.error,
    redisHealth,
    loadingRedisHealth,
    redisHealthError,
    loadSecurityScore,
    loadPerformanceScore,
    loadRedisHealth,
    // Detailed findings
    securityFindings: securityFindingsEndpoint.data,
    loadingSecurityFindings: securityFindingsEndpoint.loading,
    showSecurityDetails,
    performanceFindings: performanceFindingsEndpoint.data,
    loadingPerformanceFindings: performanceFindingsEndpoint.loading,
    showPerformanceDetails,
    redisOptimizations: redisOptimizationsEndpoint.data,
    loadingRedisOptimizations: redisOptimizationsEndpoint.loading,
    showRedisDetails,
    loadSecurityFindings,
    loadPerformanceFindings,
    loadRedisOptimizations,
    toggleSecurityDetails,
    togglePerformanceDetails,
    toggleRedisDetails,
    // Cached
    loadCachedSecurityScore,
  }
}
