// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodebaseDataLoaders
 *
 * Extracts data-loading functions from CodebaseAnalytics.vue.
 * Each loader fetches data from a backend endpoint and populates
 * a reactive ref. Callers provide the refs and helpers.
 *
 * Issue #1469: Decompose CodebaseAnalytics.vue
 */

import { type Ref, type ComputedRef } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCodebaseDataLoaders')

/** Options bag for the composable. */
interface DataLoaderOptions {
  rootPath: Ref<string>
  withSourceId: (url: string) => string
  sourceIdQuery: ComputedRef<Record<string, string>>
}

/**
 * Call graph data loader.
 * Returns an object with the load function and reactive refs.
 */
export function useCallGraphLoader(opts: DataLoaderOptions) {
  const { withSourceId } = opts

  async function loadCallGraphData(
    callGraphData: Ref<{ nodes: unknown[]; edges: unknown[] }>,
    callGraphSummary: Ref<Record<string, unknown> | null>,
    callGraphOrphaned: Ref<unknown[]>,
    callGraphLoading: Ref<boolean>,
    callGraphError: Ref<string>,
  ) {
    callGraphLoading.value = true
    callGraphError.value = ''

    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/analytics/call-graph`,
        ),
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
        },
      )

      if (!response.ok) {
        throw new Error(
          `Call graph endpoint returned ${response.status}`,
        )
      }

      const data = await response.json()

      if (data.status === 'success' && data.call_graph) {
        callGraphData.value = data.call_graph
        callGraphSummary.value = data.summary
        callGraphOrphaned.value = data.orphaned_functions || []
        logger.debug('Call graph loaded:', {
          nodes: data.call_graph.nodes?.length || 0,
          edges: data.call_graph.edges?.length || 0,
          orphaned: data.orphaned_functions?.length || 0,
          summary: data.summary,
        })
      } else if (data.status === 'no_data') {
        callGraphData.value = { nodes: [], edges: [] }
        callGraphSummary.value = null
        callGraphOrphaned.value = []
        logger.debug('No call graph data - run indexing first')
      }
    } catch (error: unknown) {
      logger.error('Failed to load call graph:', error)
      callGraphError.value =
        error instanceof Error ? error.message : String(error)
    } finally {
      callGraphLoading.value = false
    }
  }

  return { loadCallGraphData }
}

/**
 * Chart data loader.
 */
export function useChartDataLoader(opts: DataLoaderOptions) {
  const { withSourceId } = opts

  async function loadChartData(
    chartData: Ref<unknown>,
    chartDataLoading: Ref<boolean>,
    chartDataError: Ref<string>,
  ) {
    chartDataLoading.value = true
    chartDataError.value = ''

    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/analytics/charts`,
        ),
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
        },
      )

      if (!response.ok) {
        throw new Error(
          `Chart data endpoint returned ${response.status}`,
        )
      }

      const data = await response.json()

      if (data.status === 'success' && data.chart_data) {
        chartData.value = data.chart_data
        logger.debug('Chart data loaded:', {
          problemTypes: data.chart_data.problem_types?.length || 0,
          severities: data.chart_data.severity_counts?.length || 0,
          raceConditions: data.chart_data.race_conditions?.length || 0,
          topFiles: data.chart_data.top_files?.length || 0,
        })
      } else if (data.status === 'no_data') {
        chartData.value = null
        logger.debug('No chart data available - run indexing first')
      }
    } catch (error: unknown) {
      logger.error('Failed to load chart data:', error)
      chartDataError.value =
        error instanceof Error ? error.message : String(error)
    } finally {
      chartDataLoading.value = false
    }
  }

  return { loadChartData }
}

/**
 * Unified report loader.
 */
export function useUnifiedReportLoader() {
  async function loadUnifiedReport(
    unifiedReport: Ref<unknown>,
    unifiedReportLoading: Ref<boolean>,
    unifiedReportError: Ref<string>,
  ) {
    unifiedReportLoading.value = true
    unifiedReportError.value = ''

    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        `${backendUrl}/api/unified/report`,
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
        },
      )

      if (!response.ok) {
        throw new Error(
          `Unified report endpoint returned ${response.status}`,
        )
      }

      const data = await response.json()

      if (data.status === 'success') {
        unifiedReport.value = data
        logger.debug('Unified report loaded:', {
          healthScore: data.summary?.health_score,
          grade: data.summary?.grade,
          totalIssues: data.summary?.total_issues,
          categories: Object.keys(data.categories || {}).length,
        })
      } else if (data.status === 'no_data') {
        unifiedReport.value = null
        logger.debug(
          'No unified report data - run indexing first',
        )
      }
    } catch (error: unknown) {
      logger.error('Failed to load unified report:', error)
      unifiedReportError.value =
        error instanceof Error ? error.message : String(error)
    } finally {
      unifiedReportLoading.value = false
    }
  }

  return { loadUnifiedReport }
}

/**
 * Environment analysis loader.
 */
export function useEnvironmentLoader(opts: DataLoaderOptions) {
  const { rootPath, withSourceId } = opts

  interface EnvironmentAnalysisResult {
    total_hardcoded_values: number
    high_priority_count: number
    recommendations_count: number
    categories: Record<string, number>
    analysis_time_seconds: number
    hardcoded_values: unknown[]
    recommendations: unknown[]
    is_truncated?: boolean
  }

  async function loadEnvironmentAnalysis(
    environmentAnalysis: Ref<EnvironmentAnalysisResult | null>,
    loadingEnvAnalysis: Ref<boolean>,
    envAnalysisError: Ref<string>,
    useAiFiltering: Ref<boolean>,
    aiFilteringModel: Ref<string>,
    aiFilteringPriority: Ref<string>,
    llmFilteringResult: Ref<unknown>,
  ) {
    if (!rootPath.value) return
    loadingEnvAnalysis.value = true
    envAnalysisError.value = ''
    llmFilteringResult.value = null

    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      let url = `${backendUrl}/api/analytics/codebase/env-analysis?path=${encodeURIComponent(rootPath.value)}`
      if (useAiFiltering.value) {
        url += `&use_llm_filter=true`
        url += `&llm_model=${encodeURIComponent(aiFilteringModel.value)}`
        url += `&filter_priority=${encodeURIComponent(aiFilteringPriority.value)}`
      }
      url = withSourceId(url)

      const response = await fetchWithAuth(url, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error(
          `Environment analysis endpoint returned ${response.status}`,
        )
      }

      const data = await response.json()
      if (data.status === 'success') {
        environmentAnalysis.value = {
          total_hardcoded_values:
            data.total_hardcoded_values || 0,
          high_priority_count: data.high_priority_count || 0,
          recommendations_count:
            data.recommendations_count || 0,
          categories: data.categories || {},
          analysis_time_seconds:
            data.analysis_time_seconds || 0,
          hardcoded_values: data.hardcoded_values || [],
          recommendations: data.recommendations || [],
        }
        if (data.llm_filtering) {
          llmFilteringResult.value = data.llm_filtering
          logger.info(
            'LLM filtering applied:',
            data.llm_filtering,
          )
        }
      } else if (data.status === 'no_data') {
        environmentAnalysis.value = null
        logger.debug(
          'No environment analysis data - run indexing first',
        )
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error(
        'Failed to load environment analysis:',
        error,
      )
      envAnalysisError.value = errorMessage
    } finally {
      loadingEnvAnalysis.value = false
    }
  }

  return { loadEnvironmentAnalysis }
}

/**
 * Redis health loader.
 */
export function useRedisHealthLoader(opts: DataLoaderOptions) {
  const { rootPath } = opts

  interface RedisHealthResult {
    redis_health_score: number
    grade: string
    status_message: string
    total_files: number
    total_issues: number
    files_with_issues: number
  }

  async function loadRedisHealth(
    redisHealth: Ref<RedisHealthResult | null>,
    loadingRedisHealth: Ref<boolean>,
    redisHealthError: Ref<string>,
  ) {
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
            'Analysis timed out - codebase too large for real-time scan',
          )
        }
        const detail = await response
          .json()
          .catch(() => null)
        throw new Error(
          detail?.detail ||
            `Redis health endpoint returned ${response.status}`,
        )
      }

      const data = await response.json()
      if (data.status === 'success') {
        redisHealth.value = {
          redis_health_score:
            data.health_score ??
            data.redis_health_score ??
            0,
          grade: data.grade || 'N/A',
          status_message: data.status_message || '',
          total_files: data.total_files || 0,
          total_issues:
            data.total_optimizations ||
            data.total_issues ||
            0,
          files_with_issues: data.files_with_issues || 0,
        }
      } else if (data.status === 'no_data') {
        redisHealth.value = null
        logger.debug(
          'No Redis health data - run indexing first',
        )
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

  return { loadRedisHealth }
}

/**
 * Cross-language analysis loader.
 */
export function useCrossLanguageLoader(opts: DataLoaderOptions) {
  const { withSourceId } = opts

  function mapCrossLanguageSummary(
    summary: Record<string, unknown>,
  ) {
    const files = summary.files_analyzed as
      | Record<string, number>
      | undefined
    const issues = summary.issues as
      | Record<string, number>
      | undefined
    const perf = summary.performance as
      | Record<string, number>
      | undefined
    return {
      analysis_id: summary.analysis_id,
      scan_timestamp: summary.scan_timestamp,
      python_files_analyzed: files?.python || 0,
      typescript_files_analyzed: files?.typescript || 0,
      vue_files_analyzed: files?.vue || 0,
      total_patterns: issues?.total || 0,
      critical_issues: issues?.critical || 0,
      high_issues: issues?.high || 0,
      medium_issues: issues?.medium || 0,
      low_issues: issues?.low || 0,
      dto_mismatches: [] as unknown[],
      validation_duplications: [] as unknown[],
      api_contract_mismatches: [] as unknown[],
      pattern_matches: [] as unknown[],
      analysis_time_ms: perf?.analysis_time_ms || 0,
    }
  }

  async function loadCrossLanguageDetails(
    crossLanguageAnalysis: Ref<Record<string, unknown> | null>,
  ) {
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')

      const dtoResponse = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/dto-mismatches`,
        ),
      )
      if (dtoResponse.ok) {
        const dtoData = await dtoResponse.json()
        if (
          dtoData.status === 'success' &&
          crossLanguageAnalysis.value
        ) {
          ;(crossLanguageAnalysis.value as Record<string, unknown>).dto_mismatches =
            dtoData.mismatches || []
        }
      }

      const apiResponse = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/api-mismatches`,
        ),
      )
      if (apiResponse.ok) {
        const apiData = await apiResponse.json()
        if (
          apiData.status === 'success' &&
          crossLanguageAnalysis.value
        ) {
          const orphaned = (apiData.orphaned || []).map(
            (m: Record<string, unknown>) => ({
              ...m,
              mismatch_type: 'orphaned_endpoint',
            }),
          )
          const missing = (apiData.missing || []).map(
            (m: Record<string, unknown>) => ({
              ...m,
              mismatch_type: 'missing_endpoint',
            }),
          )
          ;(crossLanguageAnalysis.value as Record<string, unknown>).api_contract_mismatches =
            [...missing, ...orphaned]
        }
      }

      const valResponse = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/validation-duplications`,
        ),
      )
      if (valResponse.ok) {
        const valData = await valResponse.json()
        if (
          valData.status === 'success' &&
          crossLanguageAnalysis.value
        ) {
          ;(crossLanguageAnalysis.value as Record<string, unknown>).validation_duplications =
            valData.duplications || []
        }
      }

      const matchResponse = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/semantic-matches?min_similarity=0.7&limit=20`,
        ),
      )
      if (matchResponse.ok) {
        const matchData = await matchResponse.json()
        if (
          matchData.status === 'success' &&
          crossLanguageAnalysis.value
        ) {
          ;(crossLanguageAnalysis.value as Record<string, unknown>).pattern_matches =
            matchData.matches || []
        }
      }
    } catch (error: unknown) {
      logger.warn(
        'Failed to load some cross-language details:',
        error,
      )
    }
  }

  return {
    mapCrossLanguageSummary,
    loadCrossLanguageDetails,
  }
}

/**
 * Cached result loaders — fetch from GET /cached endpoints.
 * Issue #1540: No new analysis triggered.
 */
export function useCachedLoaders(opts: DataLoaderOptions) {
  const { withSourceId } = opts

  async function loadCachedDuplicates(
    duplicateAnalysis: Ref<unknown[]>,
  ) {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      withSourceId(
        `${backendUrl}/api/analytics/codebase/duplicates/cached`,
      ),
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (
      data.status === 'success' &&
      Array.isArray(data.duplicates)
    ) {
      duplicateAnalysis.value = data.duplicates
    }
  }

  async function loadCachedDependencies(
    dependencyData: Ref<unknown>,
  ) {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      withSourceId(
        `${backendUrl}/api/analytics/codebase/analytics/dependencies/cached`,
      ),
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.dependency_data) {
      dependencyData.value = data.dependency_data
    }
  }

  async function loadCachedImportTree(
    importTreeData: Ref<unknown>,
  ) {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      withSourceId(
        `${backendUrl}/api/analytics/codebase/analytics/import-tree/cached`,
      ),
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.import_tree) {
      importTreeData.value = data.import_tree
    }
  }

  async function loadCachedBugPrediction(
    bugPredictionResult: Ref<Record<string, unknown> | null>,
  ) {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      `${backendUrl}/api/analytics/bug-prediction/cached`,
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.files) {
      bugPredictionResult.value = data as Record<
        string,
        unknown
      >
    }
  }

  async function loadCachedSecurityScore(
    securityScore: Ref<unknown>,
  ) {
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
    loadCachedDuplicates,
    loadCachedDependencies,
    loadCachedImportTree,
    loadCachedBugPrediction,
    loadCachedSecurityScore,
  }
}
