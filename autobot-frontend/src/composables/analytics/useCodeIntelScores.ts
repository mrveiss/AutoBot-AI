// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useCodeIntelScores
 *
 * Security, performance, and Redis health scores plus detailed findings
 * and toggle logic. Extracted from useCodeIntelAnalysis (Issue #2260).
 * Migrated from useAnalyticsFetch to useFetchEndpoint (Issue #5208).
 *
 * Most `/code-intelligence/*` endpoints take the raw repo path directly
 * (no `source_id` needed), so they keep the default `scopeToSource: false`.
 * The Redis health endpoint is the exception — the pre-migration code
 * wrapped its URL with `withSourceId()`, so its migrated form passes
 * `scopeToSource: true` to preserve parity.
 *
 * #5235 additionally routes the two remaining hand-rolled fetchers
 * (`loadRedisHealth`, `loadCachedSecurityScore`) through `useFetchEndpoint`,
 * using the new `onResponse` hook for 504 / `detail` error extraction.
 * The file no longer imports `fetchWithAuth` or `appConfig`.
 */

import { ref } from 'vue'
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

  // --- Redis health (#5235: migrated via useFetchEndpoint `onResponse`) ---

  interface RedisHealthRaw {
    status: string
    health_score?: number
    redis_health_score?: number
    grade?: string
    status_message?: string
    total_files?: number
    total_issues?: number
    total_optimizations?: number
    files_with_issues?: number
  }

  const redisHealthEndpoint = useFetchEndpoint<RedisHealthRaw, RedisHealthResult>(
    {
      path: '/api/code-intelligence/redis/health-score',
      scopeToSource: true,
      label: 'Redis health endpoint',
      pickData: (r) =>
        r.status === 'success'
          ? {
              redis_health_score:
                r.health_score ?? r.redis_health_score ?? 0,
              grade: r.grade || 'N/A',
              status_message: r.status_message || '',
              total_files: r.total_files || 0,
              total_issues: r.total_optimizations || r.total_issues || 0,
              files_with_issues: r.files_with_issues || 0,
            }
          : null,
      onNoData: () =>
        logger.debug('No Redis health data - run indexing first'),
      onResponse: async (response) => {
        if (response.status === 504) {
          return 'Analysis timed out -- codebase too large for real-time scan'
        }
        const detail = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null
        return detail?.detail
      },
    },
    { withSourceId },
  )

  const redisHealth = redisHealthEndpoint.data
  const loadingRedisHealth = redisHealthEndpoint.loading
  const redisHealthError = redisHealthEndpoint.error

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
    await redisHealthEndpoint.load({ path: rootPath.value })
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

  // --- Cached security score loader (#5235: best-effort read; on failure
  // the useTaskLoader-backed `securityScore` ref is left untouched) ---

  interface CachedSecurityScoreRaw {
    status: string
    security_score?: number
    grade?: string
    risk_level?: string
    status_message?: string
    total_findings?: number
    critical_issues?: number
    high_issues?: number
    files_analyzed?: number
    severity_breakdown?: Record<string, number>
    owasp_breakdown?: Record<string, number>
  }

  const cachedSecurityScoreEndpoint = useFetchEndpoint<
    CachedSecurityScoreRaw,
    SecurityScoreResult
  >({
    path: '/api/code-intelligence/security/score/cached',
    label: 'Cached security score',
    pickData: (r) =>
      r.status === 'success' && r.security_score !== undefined
        ? {
            security_score: r.security_score ?? 0,
            grade: r.grade ?? 'N/A',
            risk_level: r.risk_level ?? 'unknown',
            status_message: r.status_message ?? '',
            total_findings: r.total_findings ?? 0,
            critical_issues: r.critical_issues ?? 0,
            high_issues: r.high_issues ?? 0,
            files_analyzed: r.files_analyzed ?? 0,
            severity_breakdown: r.severity_breakdown ?? {},
            owasp_breakdown: r.owasp_breakdown ?? {},
          }
        : null,
    // Mutate the useTaskLoader-backed `securityScore` ref only on a
    // successful cached read. On no_data / error / !ok, leave it alone
    // so a prior live-scan result remains visible.
    onSuccess: (picked) => {
      securityScore.value = picked
    },
  })

  const loadCachedSecurityScore = () => cachedSecurityScoreEndpoint.load()

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
