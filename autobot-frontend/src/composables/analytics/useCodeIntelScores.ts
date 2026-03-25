// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeIntelScores
 *
 * Security, performance, and Redis health scores plus detailed findings
 * and toggle logic. Extracted from useCodeIntelAnalysis (Issue #2260).
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
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

const logger = createLogger('useCodeIntelScores')

export function useCodeIntelScores(deps: UseCodeIntelAnalysisDeps) {
  const { rootPath } = deps

  // --- Security score (useTaskLoader) ---

  const {
    data: securityScore,
    loading: loadingSecurityScore,
    error: securityScoreError,
    load: _loadSecurityScoreTask,
  } = useTaskLoader<SecurityScoreResult>(
    '/api/code-intelligence/security/score',
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

  // --- Performance score (useAnalyticsFetch) ---

  const {
    data: performanceScore,
    loading: loadingPerformanceScore,
    error: performanceScoreError,
    load: _loadPerformanceScore,
  } = useAnalyticsFetch<PerformanceScoreResult>(
    '/api/code-intelligence/performance/score',
    (r) => {
      if (r.status === 'success') {
        return {
          performance_score: (r.performance_score as number) || 0,
          grade: (r.grade as string) || 'N/A',
          status_message: (r.status_message as string) || '',
          total_issues: (r.total_issues as number) || 0,
          files_analyzed: (r.files_analyzed as number) || 0,
          severity_breakdown:
            (r.severity_breakdown as Record<string, number>) || {},
          issue_type_breakdown:
            (r.issue_type_breakdown as Record<string, number>) || {},
        }
      }
      if (r.status === 'no_data') return undefined
      return undefined
    },
  )

  // --- Redis health ---

  const redisHealth = ref<RedisHealthResult | null>(null)
  const loadingRedisHealth = ref(false)
  const redisHealthError = ref('')

  // --- Detailed findings (useAnalyticsFetch POST) ---

  const {
    data: securityFindings,
    loading: loadingSecurityFindings,
    load: _loadSecurityFindings,
  } = useAnalyticsFetch<SecurityFindingDetail[]>(
    '/api/code-intelligence/security/analyze',
    (r) =>
      r.status === 'success' && r.findings
        ? (r.findings as unknown as SecurityFindingDetail[])
        : [],
    { method: 'POST' },
  )
  const showSecurityDetails = ref(false)

  const {
    data: performanceFindings,
    loading: loadingPerformanceFindings,
    load: _loadPerformanceFindings,
  } = useAnalyticsFetch<PerformanceFindingDetail[]>(
    '/api/code-intelligence/performance/analyze',
    (r) =>
      r.status === 'success' && r.findings
        ? (r.findings as unknown as PerformanceFindingDetail[])
        : [],
    { method: 'POST' },
  )
  const showPerformanceDetails = ref(false)

  const {
    data: redisOptimizations,
    loading: loadingRedisOptimizations,
    load: _loadRedisOptimizations,
  } = useAnalyticsFetch<RedisOptimization[]>(
    '/api/code-intelligence/redis/analyze',
    (r) =>
      r.status === 'success' && r.findings
        ? (r.findings as unknown as RedisOptimization[])
        : [],
    { method: 'POST' },
  )
  const showRedisDetails = ref(false)

  // --- Score loaders ---

  const loadSecurityScore = async () => {
    if (!rootPath.value) return
    await _loadSecurityScoreTask(undefined, {
      path: rootPath.value,
    })
  }

  const loadPerformanceScore = async () => {
    if (!rootPath.value) return
    await _loadPerformanceScore({ path: rootPath.value })
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
      const response = await fetchWithAuth(
        `${backendUrl}/api/code-intelligence/redis/health-score?path=${encodeURIComponent(rootPath.value)}`,
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
        },
      )
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
    await _loadSecurityFindings(undefined, { path: rootPath.value })
  }

  const loadPerformanceFindings = async () => {
    if (!rootPath.value) return
    await _loadPerformanceFindings(undefined, { path: rootPath.value })
  }

  const loadRedisOptimizations = async () => {
    if (!rootPath.value) return
    await _loadRedisOptimizations(undefined, { path: rootPath.value })
  }

  // --- Toggle functions ---

  const toggleSecurityDetails = async () => {
    showSecurityDetails.value = !showSecurityDetails.value
    if (showSecurityDetails.value && !securityFindings.value?.length) {
      await loadSecurityFindings()
    }
  }

  const togglePerformanceDetails = async () => {
    showPerformanceDetails.value = !showPerformanceDetails.value
    if (
      showPerformanceDetails.value &&
      !performanceFindings.value?.length
    ) {
      await loadPerformanceFindings()
    }
  }

  const toggleRedisDetails = async () => {
    showRedisDetails.value = !showRedisDetails.value
    if (showRedisDetails.value && !redisOptimizations.value?.length) {
      await loadRedisOptimizations()
    }
  }

  // --- Cached security score loader ---

  const loadCachedSecurityScore = async () => {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      `${backendUrl}/api/code-intelligence/security/score/cached`,
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (
      data.status === 'success' &&
      data.security_score !== undefined
    ) {
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
    performanceScore,
    loadingPerformanceScore,
    performanceScoreError,
    redisHealth,
    loadingRedisHealth,
    redisHealthError,
    loadSecurityScore,
    loadPerformanceScore,
    loadRedisHealth,
    // Detailed findings
    securityFindings,
    loadingSecurityFindings,
    showSecurityDetails,
    performanceFindings,
    loadingPerformanceFindings,
    showPerformanceDetails,
    redisOptimizations,
    loadingRedisOptimizations,
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
