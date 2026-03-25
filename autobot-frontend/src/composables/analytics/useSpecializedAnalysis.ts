// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useSpecializedAnalysis
 *
 * API endpoint analysis, config duplicates, environment analysis,
 * ownership analysis, and cross-language analysis.
 * Extracted from useCodeIntelAnalysis (Issue #2260).
 */

import { ref, reactive } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  ApiEndpointAnalysisResult,
  ConfigDuplicatesResult,
  EnvironmentAnalysisResult,
  OwnershipAnalysisResult,
  OwnershipSummary,
  FileOwnership,
  DirectoryOwnership,
  ExpertiseScore,
  KnowledgeGap,
  OwnershipMetrics,
  CrossLanguageAnalysisResult,
} from './codeIntelTypes'

const logger = createLogger('useSpecializedAnalysis')

export function useSpecializedAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { rootPath, sourceIdQuery, withSourceId, t, notify } = deps

  // --- API endpoints (useAnalyticsFetch) ---

  const {
    data: apiEndpointAnalysis,
    loading: loadingApiEndpoints,
    error: apiEndpointsError,
    load: _loadApiEndpoints,
  } = useAnalyticsFetch<ApiEndpointAnalysisResult>(
    '/api/analytics/codebase/endpoint-analysis',
    (r) => {
      if (r.status === 'success' && r.analysis) {
        return r.analysis as unknown as ApiEndpointAnalysisResult
      }
      return undefined
    },
  )

  const expandedApiEndpointGroups = reactive({
    orphaned: false,
    missing: false,
    used: false,
  })

  // --- Config duplicates (useAnalyticsFetch) ---

  const {
    data: configDuplicatesAnalysis,
    loading: loadingConfigDuplicates,
    error: configDuplicatesError,
    load: _loadConfigDuplicates,
  } = useAnalyticsFetch<ConfigDuplicatesResult>(
    '/api/analytics/codebase/config-duplicates',
    (r) => {
      if (r.status === 'success') {
        return {
          duplicates_found: (r.duplicates_found as number) || 0,
          duplicates:
            (r.duplicates as ConfigDuplicatesResult['duplicates']) ||
            [],
          report: (r.report as string) || '',
        }
      }
      return undefined
    },
  )

  // --- Environment analysis ---

  const environmentAnalysis =
    ref<EnvironmentAnalysisResult | null>(null)
  const loadingEnvAnalysis = ref(false)
  const envAnalysisError = ref('')
  const useAiFiltering = ref(false)
  const aiFilteringModel = ref('llama3.2:1b')
  const aiFilteringPriority = ref('high')
  const llmFilteringResult = ref<{
    enabled: boolean
    model: string
    original_count: number
    filtered_count: number
    reduction_percent: number
    filter_priority: string | null
  } | null>(null)

  // --- Ownership (useAnalyticsFetch) ---

  const {
    data: ownershipAnalysis,
    loading: loadingOwnership,
    error: ownershipError,
    load: _loadOwnership,
  } = useAnalyticsFetch<OwnershipAnalysisResult>(
    '/api/analytics/codebase/ownership/analysis',
    (r) => {
      if (r.status === 'success') {
        return {
          status: r.status as string,
          analysis_time_seconds:
            (r.analysis_time_seconds as number) || 0,
          summary: (r.summary as OwnershipSummary) || {
            total_files: 0,
            total_directories: 0,
            total_contributors: 0,
            knowledge_gaps_count: 0,
            critical_gaps: 0,
            high_risk_gaps: 0,
          },
          file_ownership:
            (r.file_ownership as FileOwnership[]) || [],
          directory_ownership:
            (r.directory_ownership as DirectoryOwnership[]) || [],
          expertise_scores:
            (r.expertise_scores as ExpertiseScore[]) || [],
          knowledge_gaps:
            (r.knowledge_gaps as KnowledgeGap[]) || [],
          metrics: (r.metrics as OwnershipMetrics) || {
            total_lines_analyzed: 0,
            total_files_analyzed: 0,
            overall_bus_factor: 1,
            bus_factor_distribution: {},
            knowledge_risk_distribution: {},
            top_contributors: [],
            ownership_concentration: 0,
            team_coverage: 0,
          },
        }
      }
      if (r.status === 'error') return undefined
      return undefined
    },
  )

  const ownershipViewMode = ref<
    'overview' | 'files' | 'contributors' | 'gaps'
  >('overview')

  // --- Cross-language analysis ---

  const crossLanguageAnalysis =
    ref<CrossLanguageAnalysisResult | null>(null)
  const loadingCrossLanguage = ref(false)
  const crossLanguageError = ref('')
  const expandedCrossLanguageGroups = reactive({
    dtoMismatches: false,
    apiMismatches: false,
    validationDups: false,
    semanticMatches: false,
  })

  // --- API endpoint functions ---

  const loadApiEndpointAnalysis = () =>
    _loadApiEndpoints(sourceIdQuery.value)

  const getApiEndpointCoverage = async () => {
    loadingApiEndpoints.value = true
    apiEndpointsError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/endpoint-analysis`,
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
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      if (data.status === 'success' && data.analysis) {
        apiEndpointAnalysis.value = data.analysis
        const coverage =
          data.analysis.coverage_percentage?.toFixed(1) || 0
        const orphaned = data.analysis.orphaned_endpoints || 0
        const missing = data.analysis.missing_endpoints || 0
        notify(
          t('analytics.codebase.notify.apiCoverageResult', {
            coverage,
            orphaned,
            missing,
            time: responseTime,
          }),
          'success',
        )
      } else {
        throw new Error('Invalid response format')
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('API Endpoint analysis failed:', error)
      apiEndpointsError.value = errorMessage
      notify(
        t('analytics.codebase.notify.apiAnalysisFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      loadingApiEndpoints.value = false
    }
  }

  const getCoverageClass = (percentage: number): string => {
    if (!percentage || percentage < 50) return 'critical'
    if (percentage < 75) return 'warning'
    if (percentage < 90) return 'info'
    return 'success'
  }

  // --- Config duplicates function ---

  const loadConfigDuplicates = () =>
    _loadConfigDuplicates(sourceIdQuery.value)

  // --- Environment analysis function ---

  const loadEnvironmentAnalysis = async () => {
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

  // --- Ownership analysis function ---

  const loadOwnershipAnalysis = async () => {
    if (!rootPath.value) return
    await _loadOwnership({
      path: rootPath.value,
      ...sourceIdQuery.value,
    })
  }

  // --- Cross-language analysis functions ---

  function _mapCrossLanguageSummary(
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

  async function _fetchCrossLanguageSection(
    backendUrl: string,
    endpoint: string,
    extractFn: (data: Record<string, unknown>) => unknown[],
  ): Promise<unknown[]> {
    const response = await fetchWithAuth(
      withSourceId(`${backendUrl}/api/analytics/codebase/cross-language/${endpoint}`),
    )
    if (!response.ok) return []
    const data = await response.json()
    if (data.status !== 'success') return []
    return extractFn(data)
  }

  const loadCrossLanguageDetails = async () => {
    if (!crossLanguageAnalysis.value) return
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const analysis = crossLanguageAnalysis.value

      analysis.dto_mismatches = await _fetchCrossLanguageSection(
        backendUrl, 'dto-mismatches',
        (d) => (d.mismatches as unknown[]) || [],
      )
      analysis.api_contract_mismatches = await _fetchCrossLanguageSection(
        backendUrl, 'api-mismatches',
        (d) => {
          const orphaned = ((d.orphaned as unknown[]) || []).map(
            (m) => ({ ...(m as Record<string, unknown>), mismatch_type: 'orphaned_endpoint' }),
          )
          const missing = ((d.missing as unknown[]) || []).map(
            (m) => ({ ...(m as Record<string, unknown>), mismatch_type: 'missing_endpoint' }),
          )
          return [...missing, ...orphaned]
        },
      )
      analysis.validation_duplications = await _fetchCrossLanguageSection(
        backendUrl, 'validation-duplications',
        (d) => (d.duplications as unknown[]) || [],
      )
      analysis.pattern_matches = await _fetchCrossLanguageSection(
        backendUrl, 'semantic-matches?min_similarity=0.7&limit=20',
        (d) => (d.matches as unknown[]) || [],
      )
    } catch (error: unknown) {
      logger.warn(
        'Failed to load some cross-language details:',
        error,
      )
    }
  }

  function _handleCrossLanguageSuccess(
    summary: Record<string, unknown>,
    responseTime: number,
  ) {
    crossLanguageAnalysis.value = _mapCrossLanguageSummary(
      summary,
    ) as CrossLanguageAnalysisResult
    const issues = summary.issues as Record<string, number> | undefined
    notify(
      t('analytics.codebase.notify.crossLanguageResult', {
        total: issues?.total || 0,
        critical: issues?.critical || 0,
        high: issues?.high || 0,
        time: responseTime,
      }),
      'success',
    )
  }

  const getCrossLanguageAnalysis = async () => {
    loadingCrossLanguage.value = true
    crossLanguageError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/summary`,
        ),
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      if (data.status === 'success' && data.summary) {
        _handleCrossLanguageSuccess(data.summary, Date.now() - startTime)
        await loadCrossLanguageDetails()
      } else if (data.status === 'empty') {
        crossLanguageAnalysis.value = null
        logger.info('Cross-language analysis: No cached data available')
      } else {
        throw new Error('Invalid response format')
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Cross-language analysis failed:', error)
      crossLanguageError.value = errorMessage
      notify(
        t('analytics.codebase.notify.crossLanguageFailed', {
          error: errorMessage,
          time: Date.now() - startTime,
        }),
        'error',
      )
    } finally {
      loadingCrossLanguage.value = false
    }
  }

  const runCrossLanguageAnalysis = async () => {
    loadingCrossLanguage.value = true
    crossLanguageError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/analyze`,
        ),
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            use_llm: true,
            use_cache: true,
          }),
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      if (data.status === 'success') {
        notify(
          t(
            'analytics.codebase.notify.crossLanguageScanComplete',
            { time: responseTime },
          ),
          'success',
        )
        await getCrossLanguageAnalysis()
      } else {
        throw new Error(data.message || 'Analysis failed')
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Cross-language analysis scan failed:', error)
      crossLanguageError.value = errorMessage
      notify(
        t(
          'analytics.codebase.notify.crossLanguageScanFailed',
          { error: errorMessage, time: responseTime },
        ),
        'error',
      )
    } finally {
      loadingCrossLanguage.value = false
    }
  }

  const getCrossLanguageSeverityClass = (
    severity: string,
  ): string => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return 'critical'
      case 'high':
        return 'warning'
      case 'medium':
        return 'info'
      case 'low':
        return 'success'
      default:
        return 'info'
    }
  }

  return {
    // API endpoints
    apiEndpointAnalysis,
    loadingApiEndpoints,
    apiEndpointsError,
    expandedApiEndpointGroups,
    loadApiEndpointAnalysis,
    getApiEndpointCoverage,
    getCoverageClass,
    // Config duplicates
    configDuplicatesAnalysis,
    loadingConfigDuplicates,
    configDuplicatesError,
    loadConfigDuplicates,
    // Environment
    environmentAnalysis,
    loadingEnvAnalysis,
    envAnalysisError,
    useAiFiltering,
    aiFilteringModel,
    aiFilteringPriority,
    llmFilteringResult,
    loadEnvironmentAnalysis,
    // Ownership
    ownershipAnalysis,
    loadingOwnership,
    ownershipError,
    ownershipViewMode,
    loadOwnershipAnalysis,
    // Cross-language
    crossLanguageAnalysis,
    loadingCrossLanguage,
    crossLanguageError,
    expandedCrossLanguageGroups,
    getCrossLanguageAnalysis,
    runCrossLanguageAnalysis,
    getCrossLanguageSeverityClass,
  }
}
