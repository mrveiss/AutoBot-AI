// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeIntelAnalysis
 *
 * Encapsulates Code Intelligence analysis state and operations:
 * security/performance/redis scores, findings, code smells,
 * environment analysis, ownership, cross-language analysis,
 * bug prediction, config duplicates, and API endpoint coverage.
 *
 * Issues #2228, #2230: Extracted from CodebaseAnalytics.vue
 */

import {
  ref,
  reactive,
  computed,
  type Ref,
  type ComputedRef,
} from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
import { createLogger } from '@/utils/debugUtils'
import type {
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
} from '@/types/codeIntelligence'

const logger = createLogger('useCodeIntelAnalysis')

// --- Type definitions ---

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
  severity_breakdown: Record<string, number>
  issue_type_breakdown: Record<string, number>
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
  code_snippet?: string
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
  code_snippet?: string
  recommendation?: string
}

interface ApiEndpointInfo {
  path: string
  method?: string
  function_name?: string
  expected_path?: string
  actual_path?: string
  file_path?: string
  line_number?: number
  [key: string]: unknown
}

interface ApiUsageInfo {
  endpoint?: ApiEndpointInfo
  call_count?: number
  [key: string]: unknown
}

interface ApiEndpointAnalysisResult {
  coverage_percentage: number
  backend_endpoints: number
  frontend_calls: number
  used_endpoints: number
  orphaned_endpoints: number
  missing_endpoints: number
  orphaned: ApiEndpointInfo[]
  missing: ApiEndpointInfo[]
  used?: ApiUsageInfo[]
  scan_timestamp?: string | number | Date
  [key: string]: unknown
}

interface ConfigDuplicatesResult {
  duplicates_found: number
  duplicates: Array<{
    value: string
    locations: Array<{ file: string; line: number }>
  }>
  report: string
}

interface BugPredictionFile {
  file_path: string
  risk_score: number
  risk_level: string
  factors: Record<string, number>
  prevention_tips?: string[]
  suggested_tests?: string[]
}

interface BugPredictionResult {
  timestamp: string
  total_files: number
  analyzed_files: number
  high_risk_count: number
  files: BugPredictionFile[]
}

interface TopRiskFactor {
  name: string
  count: number
  severity: 'critical' | 'high' | 'medium' | 'low'
}

interface EnvRecommendation {
  env_var_name: string
  default_value: string
  description: string
  category: string
  priority: string
}

interface EnvironmentAnalysisResult {
  total_hardcoded_values: number
  high_priority_count: number
  recommendations_count: number
  categories: Record<string, number>
  analysis_time_seconds: number
  hardcoded_values: Array<{
    file: string
    line: number
    variable_name?: string
    value: string
    type: string
    severity: string
    suggested_env_var: string
    context?: string
    current_usage?: string
  }>
  recommendations: EnvRecommendation[]
  is_truncated?: boolean
}

interface OwnershipContributor {
  name: string
  email?: string
  lines: number
  percentage: number
}

interface FileOwnership {
  file_path: string
  total_lines: number
  primary_owner: string | null
  ownership_percentage: number
  bus_factor: number
  knowledge_risk: string
  last_modified: string | null
  contributors: OwnershipContributor[]
}

interface DirectoryOwnership {
  directory_path: string
  total_files: number
  total_lines: number
  primary_owner: string | null
  ownership_percentage: number
  bus_factor: number
  knowledge_risk: string
  contributors: OwnershipContributor[]
}

interface ExpertiseScore {
  author_name: string
  author_email: string
  total_lines: number
  total_commits: number
  files_owned: number
  directories_owned: number
  expertise_areas: string[]
  recency_score: number
  impact_score: number
  overall_score: number
}

interface KnowledgeGap {
  area: string
  gap_type: string
  risk_level: string
  description: string
  recommendation: string
  affected_lines: number
}

interface OwnershipMetrics {
  total_lines_analyzed: number
  total_files_analyzed: number
  overall_bus_factor: number
  bus_factor_distribution: Record<string, number>
  knowledge_risk_distribution: Record<string, number>
  top_contributors: Array<{
    name: string
    lines: number
    score: number
  }>
  ownership_concentration: number
  team_coverage: number
}

interface OwnershipSummary {
  total_files: number
  total_directories: number
  total_contributors: number
  knowledge_gaps_count: number
  critical_gaps: number
  high_risk_gaps: number
}

interface OwnershipAnalysisResult {
  status: string
  analysis_time_seconds: number
  summary: OwnershipSummary
  file_ownership: FileOwnership[]
  directory_ownership: DirectoryOwnership[]
  expertise_scores: ExpertiseScore[]
  knowledge_gaps: KnowledgeGap[]
  metrics: OwnershipMetrics
}

interface PatternLocation {
  file_path: string
  line_start: number
  line_end: number
  language: string
}

interface DTOMismatch {
  mismatch_id: string
  backend_type: string
  frontend_type: string
  field_name: string
  mismatch_type: string
  severity: string
  recommendation: string
  backend_location?: PatternLocation
  frontend_location?: PatternLocation
}

interface ValidationDuplication {
  duplication_id: string
  validation_type: string
  similarity_score: number
  severity: string
  recommendation: string
  python_location?: PatternLocation
  typescript_location?: PatternLocation
}

interface APIContractMismatch {
  mismatch_id: string
  endpoint_path: string
  http_method: string
  mismatch_type: string
  severity: string
  details: string
  recommendation: string
  backend_location?: PatternLocation
  frontend_location?: PatternLocation
}

interface PatternMatch {
  pattern_id: string
  similarity_score: number
  match_type: string
  confidence: number
  source_location?: PatternLocation
  target_location?: PatternLocation
  metadata?: Record<string, string>
}

interface CrossLanguageAnalysisResult {
  analysis_id: string
  scan_timestamp: string
  python_files_analyzed: number
  typescript_files_analyzed: number
  vue_files_analyzed: number
  total_patterns: number
  critical_issues: number
  high_issues: number
  medium_issues: number
  low_issues: number
  dto_mismatches: DTOMismatch[]
  validation_duplications: ValidationDuplication[]
  api_contract_mismatches: APIContractMismatch[]
  pattern_matches: PatternMatch[]
  analysis_time_ms: number
}

interface CodeSmellsReportData {
  smells: Array<{
    type: string
    severity: string
    message: string
    file_path: string
    line?: number
  }>
  summary?: Record<string, unknown>
  [key: string]: unknown
}

interface CodeHealthScoreData {
  grade: string
  health_score: number
  breakdown?: Record<string, unknown>
  [key: string]: unknown
}

export interface UseCodeIntelAnalysisDeps {
  rootPath: Ref<string>
  sourceIdParam: ComputedRef<string>
  sourceIdQuery: ComputedRef<Record<string, string>>
  withSourceId: (url: string) => string
  analyzing: Ref<boolean>
  t: (key: string, params?: Record<string, unknown>) => string
  showToast: (msg: string, type?: string, duration?: number) => void
  notify: (msg: string, type?: string) => void
}

export function useCodeIntelAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const {
    rootPath,
    sourceIdQuery,
    withSourceId,
    analyzing,
    t,
    notify,
  } = deps

  // --- useCodeIntelligence composable ---

  const {
    isLoading: codeIntelLoading,
    suggestions: codeIntelSuggestions,
    analyzeCode: codeIntelAnalyzeCode,
    getSuggestions: codeIntelGetSuggestions,
    batchAnalyze: codeIntelBatchAnalyze,
  } = useCodeIntelligence()

  const codeIntelSecurityFindings = ref<SecurityFinding[]>([])
  const codeIntelPerformanceFindings = ref<PerformanceFinding[]>(
    [],
  )
  const codeIntelRedisFindings = ref<
    RedisOptimizationFinding[]
  >([])
  const codeIntelFindingsLoading = ref(false)
  const codeIntelFindingsFetched = ref({
    security: false,
    performance: false,
    redis: false,
  })

  const codeIntelTotalFindings = computed(
    () => codeIntelSuggestions.value.length,
  )

  // --- Code smells state ---

  const codeSmellsReport = ref<CodeSmellsReportData | null>(null)
  const codeHealthScore = ref<CodeHealthScoreData | null>(null)
  const analyzingCodeSmells = ref(false)
  const codeSmellsAnalysisType = ref('')
  const exportingReport = ref(false)
  const clearingCache = ref(false)

  const codeSmellsProgressTitle = computed(() => {
    return codeSmellsAnalysisType.value === 'health'
      ? t('analytics.codebase.progress.calculatingHealth')
      : t('analytics.codebase.progress.analyzingSmells')
  })

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
          security_score:
            (r.security_score as number) || 0,
          grade: (r.grade as string) || 'N/A',
          risk_level: (r.risk_level as string) || 'unknown',
          status_message:
            (r.status_message as string) || '',
          total_findings:
            (r.total_findings as number) || 0,
          critical_issues:
            (r.critical_issues as number) || 0,
          high_issues: (r.high_issues as number) || 0,
          files_analyzed:
            (r.files_analyzed as number) || 0,
          severity_breakdown:
            (r.severity_breakdown as Record<
              string,
              number
            >) || {},
          owasp_breakdown:
            (r.owasp_breakdown as Record<
              string,
              number
            >) || {},
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
          performance_score:
            (r.performance_score as number) || 0,
          grade: (r.grade as string) || 'N/A',
          status_message:
            (r.status_message as string) || '',
          total_issues: (r.total_issues as number) || 0,
          files_analyzed:
            (r.files_analyzed as number) || 0,
          severity_breakdown:
            (r.severity_breakdown as Record<
              string,
              number
            >) || {},
          issue_type_breakdown:
            (r.issue_type_breakdown as Record<
              string,
              number
            >) || {},
        }
      }
      if (r.status === 'no_data') return undefined
      return undefined
    },
  )

  // Redis health
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
          duplicates_found:
            (r.duplicates_found as number) || 0,
          duplicates:
            (r.duplicates as ConfigDuplicatesResult['duplicates']) ||
            [],
          report: (r.report as string) || '',
        }
      }
      return undefined
    },
  )

  // --- Bug prediction (useBackgroundTask) ---

  const bugPredictionTask = useBackgroundTask(
    '/api/analytics/bug-prediction',
  )
  const bugPredictionAnalysis =
    computed<BugPredictionResult | null>(() => {
      const r = bugPredictionTask.result.value
      if (!r || r.status === 'no_data') return null
      return {
        timestamp:
          (r.timestamp as string) ||
          new Date().toISOString(),
        total_files: (r.total_files as number) || 0,
        analyzed_files: (r.analyzed_files as number) || 0,
        high_risk_count:
          (r.high_risk_count as number) || 0,
        files: (r.files as BugPredictionFile[]) || [],
      }
    })
  const loadingBugPrediction = bugPredictionTask.running
  const bugPredictionError = bugPredictionTask.error

  // Bug risk UI state
  const bugRiskFilter = ref<
    'all' | 'high' | 'medium' | 'low'
  >('all')
  const BUG_RISK_PAGE_SIZE = 50
  const bugRiskVisibleCount = ref(BUG_RISK_PAGE_SIZE)
  const expandedBugRiskFiles = ref<Set<string>>(new Set())

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
            (r.directory_ownership as DirectoryOwnership[]) ||
            [],
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

  // --- Functions ---

  async function runCodeIntelligenceAnalysis() {
    if (!rootPath.value) return
    logger.info(
      'Running Code Intelligence analysis on:',
      rootPath.value,
    )
    codeIntelFindingsFetched.value = {
      security: false,
      performance: false,
      redis: false,
    }
    codeIntelFindingsLoading.value = true
    try {
      await codeIntelAnalyzeCode({ code: rootPath.value })
      await codeIntelGetSuggestions(rootPath.value)
      codeIntelFindingsFetched.value = {
        security: true,
        performance: true,
        redis: true,
      }
      notify(
        t(
          'analytics.codebase.notify.codeIntelComplete',
          { count: codeIntelTotalFindings.value },
        ),
        'success',
      )
    } catch (e) {
      logger.error(
        'Code Intelligence analysis failed:',
        e,
      )
      notify(
        t('analytics.codebase.notify.codeIntelFailed'),
        'error',
      )
    } finally {
      codeIntelFindingsLoading.value = false
    }
  }

  async function handleFileScan(
    filePath: string,
    _types: {
      security: boolean
      performance: boolean
      redis: boolean
    },
  ) {
    codeIntelFindingsLoading.value = true
    try {
      const results = await codeIntelBatchAnalyze([
        { code: filePath, filename: filePath },
      ])
      if (results.length > 0) {
        codeIntelFindingsFetched.value = {
          security: true,
          performance: true,
          redis: true,
        }
        notify(
          t(
            'analytics.codebase.notify.fileScanComplete',
            { count: results.length },
          ),
          'info',
        )
      } else {
        notify(
          t(
            'analytics.codebase.notify.fileScanNoIssues',
          ),
          'success',
        )
      }
    } catch (e) {
      logger.error('File scan failed:', e)
      notify(
        t('analytics.codebase.notify.fileScanFailed'),
        'error',
      )
    } finally {
      codeIntelFindingsLoading.value = false
    }
  }

  const runCodeSmellAnalysis = async () => {
    const startTime = Date.now()
    codeSmellsAnalysisType.value = 'smells'
    const analysisPath = rootPath.value
    if (analysisPath.includes('/data/code-sources/')) {
      notify(
        t(
          'analytics.codebase.notify.codeIntelLocalPathRequired',
        ),
        'warning',
      )
      return
    }
    analyzingCodeSmells.value = true
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        `${backendUrl}/api/code-intelligence/analyze`,
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            path: analysisPath,
            exclude_dirs: [
              'node_modules',
              '.venv',
              '__pycache__',
              '.git',
              'archives',
            ],
            min_severity: 'low',
          }),
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(
          `Status ${response.status}: ${errorText}`,
        )
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      codeSmellsReport.value = data.report
      const totalIssues =
        data.report?.anti_patterns?.length || 0
      const filesAnalyzed =
        data.report?.total_files || 0
      notify(
        t(
          'analytics.codebase.notify.codeSmellsFound',
          {
            count: totalIssues,
            files: filesAnalyzed,
            time: responseTime,
          },
        ),
        totalIssues > 0 ? 'warning' : 'success',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error('Code smell analysis failed:', error)
      notify(
        t(
          'analytics.codebase.notify.codeSmellsFailed',
          { error: errorMessage, time: responseTime },
        ),
        'error',
      )
    } finally {
      analyzingCodeSmells.value = false
    }
  }

  const getCodeHealthScore = async () => {
    const startTime = Date.now()
    codeSmellsAnalysisType.value = 'health'
    const analysisPath = rootPath.value
    if (analysisPath.includes('/data/code-sources/')) {
      notify(
        t(
          'analytics.codebase.notify.healthScoreLocalPathRequired',
        ),
        'warning',
      )
      return
    }
    analyzingCodeSmells.value = true
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')
      const healthEndpoint = `${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(analysisPath)}`
      const response = await fetchWithAuth(healthEndpoint, {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(
          `Status ${response.status}: ${errorText}`,
        )
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      codeHealthScore.value = data
      const score = data.health_score || 0
      const grade = data.grade || 'N/A'
      const issues = data.total_issues || 0
      notify(
        t(
          'analytics.codebase.notify.healthScoreResult',
          { score, grade, issues, time: responseTime },
        ),
        score >= 70 ? 'success' : 'warning',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error('Health score failed:', error)
      notify(
        t(
          'analytics.codebase.notify.healthScoreFailed',
          { error: errorMessage, time: responseTime },
        ),
        'error',
      )
    } finally {
      analyzingCodeSmells.value = false
    }
  }

  // Score loaders
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
      const backendUrl =
        await appConfig.getServiceUrl('backend')
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
          files_with_issues:
            data.files_with_issues || 0,
        }
      } else if (data.status === 'no_data') {
        redisHealth.value = null
        logger.debug(
          'No Redis health data - run indexing first',
        )
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error('Failed to load Redis health:', error)
      redisHealthError.value = errorMessage
    } finally {
      loadingRedisHealth.value = false
    }
  }

  // Detailed findings loaders
  const loadSecurityFindings = async () => {
    if (!rootPath.value) return
    await _loadSecurityFindings(undefined, {
      path: rootPath.value,
    })
  }

  const loadPerformanceFindings = async () => {
    if (!rootPath.value) return
    await _loadPerformanceFindings(undefined, {
      path: rootPath.value,
    })
  }

  const loadRedisOptimizations = async () => {
    if (!rootPath.value) return
    await _loadRedisOptimizations(undefined, {
      path: rootPath.value,
    })
  }

  const toggleSecurityDetails = async () => {
    showSecurityDetails.value = !showSecurityDetails.value
    if (
      showSecurityDetails.value &&
      !securityFindings.value?.length
    ) {
      await loadSecurityFindings()
    }
  }

  const togglePerformanceDetails = async () => {
    showPerformanceDetails.value =
      !showPerformanceDetails.value
    if (
      showPerformanceDetails.value &&
      !performanceFindings.value?.length
    ) {
      await loadPerformanceFindings()
    }
  }

  const toggleRedisDetails = async () => {
    showRedisDetails.value = !showRedisDetails.value
    if (
      showRedisDetails.value &&
      !redisOptimizations.value?.length
    ) {
      await loadRedisOptimizations()
    }
  }

  // Config duplicates
  const loadConfigDuplicates = () =>
    _loadConfigDuplicates(sourceIdQuery.value)

  // Bug prediction
  const loadBugPrediction = () =>
    bugPredictionTask.start()

  const loadCachedBugPrediction = async () => {
    const backendUrl =
      await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      `${backendUrl}/api/analytics/bug-prediction/cached`,
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.files) {
      bugPredictionTask.result.value =
        data as Record<string, unknown>
    }
  }

  const loadCachedSecurityScore = async () => {
    const backendUrl =
      await appConfig.getServiceUrl('backend')
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
        severity_breakdown:
          data.severity_breakdown ?? {},
        owasp_breakdown: data.owasp_breakdown ?? {},
      }
    }
  }

  // API endpoint analysis
  const loadApiEndpointAnalysis = () =>
    _loadApiEndpoints(sourceIdQuery.value)

  const getApiEndpointCoverage = async () => {
    loadingApiEndpoints.value = true
    apiEndpointsError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')
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
        throw new Error(
          `Status ${response.status}: ${errorText}`,
        )
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      if (data.status === 'success' && data.analysis) {
        apiEndpointAnalysis.value = data.analysis
        const coverage =
          data.analysis.coverage_percentage?.toFixed(
            1,
          ) || 0
        const orphaned =
          data.analysis.orphaned_endpoints || 0
        const missing =
          data.analysis.missing_endpoints || 0
        notify(
          t(
            'analytics.codebase.notify.apiCoverageResult',
            {
              coverage,
              orphaned,
              missing,
              time: responseTime,
            },
          ),
          'success',
        )
      } else {
        throw new Error('Invalid response format')
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error(
        'API Endpoint analysis failed:',
        error,
      )
      apiEndpointsError.value = errorMessage
      notify(
        t(
          'analytics.codebase.notify.apiAnalysisFailed',
          { error: errorMessage, time: responseTime },
        ),
        'error',
      )
    } finally {
      loadingApiEndpoints.value = false
    }
  }

  // Environment analysis
  const loadEnvironmentAnalysis = async () => {
    if (!rootPath.value) return
    loadingEnvAnalysis.value = true
    envAnalysisError.value = ''
    llmFilteringResult.value = null
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')
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
          high_priority_count:
            data.high_priority_count || 0,
          recommendations_count:
            data.recommendations_count || 0,
          categories: data.categories || {},
          analysis_time_seconds:
            data.analysis_time_seconds || 0,
          hardcoded_values:
            data.hardcoded_values || [],
          recommendations:
            data.recommendations || [],
        }
        if (data.llm_filtering) {
          llmFilteringResult.value =
            data.llm_filtering
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
        error instanceof Error
          ? error.message
          : String(error)
      logger.error(
        'Failed to load environment analysis:',
        error,
      )
      envAnalysisError.value = errorMessage
    } finally {
      loadingEnvAnalysis.value = false
    }
  }

  // Ownership analysis
  const loadOwnershipAnalysis = async () => {
    if (!rootPath.value) return
    await _loadOwnership({
      path: rootPath.value,
      ...sourceIdQuery.value,
    })
  }

  // Cross-language analysis
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

  const loadCrossLanguageDetails = async () => {
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
          crossLanguageAnalysis.value.dto_mismatches =
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
          const orphaned = (
            apiData.orphaned || []
          ).map(
            (m: Record<string, unknown>) => ({
              ...m,
              mismatch_type: 'orphaned_endpoint',
            }),
          )
          const missing = (
            apiData.missing || []
          ).map(
            (m: Record<string, unknown>) => ({
              ...m,
              mismatch_type: 'missing_endpoint',
            }),
          )
          crossLanguageAnalysis.value.api_contract_mismatches =
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
          crossLanguageAnalysis.value.validation_duplications =
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
          crossLanguageAnalysis.value.pattern_matches =
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

  const getCrossLanguageAnalysis = async () => {
    loadingCrossLanguage.value = true
    crossLanguageError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/summary`,
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
        throw new Error(
          `Status ${response.status}: ${errorText}`,
        )
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      if (data.status === 'success' && data.summary) {
        crossLanguageAnalysis.value =
          _mapCrossLanguageSummary(
            data.summary,
          ) as CrossLanguageAnalysisResult
        const issues = data.summary.issues as
          | Record<string, number>
          | undefined
        notify(
          t(
            'analytics.codebase.notify.crossLanguageResult',
            {
              total: issues?.total || 0,
              critical: issues?.critical || 0,
              high: issues?.high || 0,
              time: responseTime,
            },
          ),
          'success',
        )
        await loadCrossLanguageDetails()
      } else if (data.status === 'empty') {
        crossLanguageAnalysis.value = null
        logger.info(
          'Cross-language analysis: No cached data available',
        )
      } else {
        throw new Error('Invalid response format')
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error(
        'Cross-language analysis failed:',
        error,
      )
      crossLanguageError.value = errorMessage
      notify(
        t(
          'analytics.codebase.notify.crossLanguageFailed',
          {
            error: errorMessage,
            time: responseTime,
          },
        ),
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
      const backendUrl =
        await appConfig.getServiceUrl('backend')
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
        throw new Error(
          `Status ${response.status}: ${errorText}`,
        )
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
        throw new Error(
          data.message || 'Analysis failed',
        )
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error(
        'Cross-language analysis scan failed:',
        error,
      )
      crossLanguageError.value = errorMessage
      notify(
        t(
          'analytics.codebase.notify.crossLanguageScanFailed',
          {
            error: errorMessage,
            time: responseTime,
          },
        ),
        'error',
      )
    } finally {
      loadingCrossLanguage.value = false
    }
  }

  // Bug risk helpers
  function getAtRiskFilesCount(): number {
    if (!bugPredictionAnalysis.value) return 0
    return bugPredictionAnalysis.value.files.filter(
      (f) => f.risk_score >= 40,
    ).length
  }

  function toggleBugRiskFilter(
    filter: 'high' | 'medium' | 'low',
  ): void {
    bugRiskFilter.value =
      bugRiskFilter.value === filter ? 'all' : filter
    bugRiskVisibleCount.value = BUG_RISK_PAGE_SIZE
  }

  function toggleBugRiskFileExpand(
    filePath: string,
  ): void {
    if (expandedBugRiskFiles.value.has(filePath)) {
      expandedBugRiskFiles.value.delete(filePath)
    } else {
      expandedBugRiskFiles.value.add(filePath)
    }
    expandedBugRiskFiles.value = new Set(
      expandedBugRiskFiles.value,
    )
  }

  function getFilteredBugRiskFiles(): BugPredictionFile[] {
    if (!bugPredictionAnalysis.value) return []
    const files = bugPredictionAnalysis.value.files
    let filtered: BugPredictionFile[]
    switch (bugRiskFilter.value) {
      case 'high':
        filtered = files.filter(
          (f) => f.risk_score >= 60,
        )
        break
      case 'medium':
        filtered = files.filter(
          (f) =>
            f.risk_score >= 40 && f.risk_score < 60,
        )
        break
      case 'low':
        filtered = files.filter(
          (f) => f.risk_score < 40,
        )
        break
      case 'all':
      default:
        filtered = [...files]
        break
    }
    return filtered.sort(
      (a, b) => b.risk_score - a.risk_score,
    )
  }

  function getTopRiskFactors(): TopRiskFactor[] {
    if (!bugPredictionAnalysis.value) return []
    const factorCounts: Record<string, number> = {
      complexity: 0,
      change_frequency: 0,
      file_size: 0,
      bug_history: 0,
      test_coverage: 0,
    }
    for (const file of bugPredictionAnalysis.value
      .files) {
      if (!file.factors) continue
      if (file.factors.complexity >= 80)
        factorCounts.complexity++
      if (file.factors.change_frequency >= 80)
        factorCounts.change_frequency++
      if (file.factors.file_size >= 70)
        factorCounts.file_size++
      if (file.factors.bug_history > 0)
        factorCounts.bug_history++
      if (file.factors.test_coverage === 50)
        factorCounts.test_coverage++
    }
    const factors: TopRiskFactor[] = Object.entries(
      factorCounts,
    )
      .filter(([, count]) => count > 0)
      .map(([name, count]) => ({
        name,
        count,
        severity: _getSeverityForFactor(name, count),
      }))
      .sort((a, b) => b.count - a.count)
    return factors.slice(0, 4)
  }

  function _getSeverityForFactor(
    factor: string,
    count: number,
  ): 'critical' | 'high' | 'medium' | 'low' {
    if (factor === 'bug_history' && count > 0)
      return 'critical'
    if (count > 50) return 'high'
    if (count > 20) return 'medium'
    return 'low'
  }

  function getRiskFactorIcon(factor: string): string {
    const icons: Record<string, string> = {
      complexity: 'fas fa-project-diagram',
      change_frequency: 'fas fa-history',
      file_size: 'fas fa-file-alt',
      bug_history: 'fas fa-bug',
      test_coverage: 'fas fa-vial',
      dependency_count: 'fas fa-sitemap',
    }
    return icons[factor] || 'fas fa-exclamation-circle'
  }

  function getRiskFactorDescription(
    factor: string,
  ): string {
    const descriptions: Record<string, string> = {
      complexity: t(
        'analytics.codebase.bugPrediction.factors.complexity',
      ),
      change_frequency: t(
        'analytics.codebase.bugPrediction.factors.changeFrequency',
      ),
      file_size: t(
        'analytics.codebase.bugPrediction.factors.fileSize',
      ),
      bug_history: t(
        'analytics.codebase.bugPrediction.factors.bugHistory',
      ),
      test_coverage: t(
        'analytics.codebase.bugPrediction.factors.testCoverage',
      ),
      dependency_count: t(
        'analytics.codebase.bugPrediction.factors.dependencyCount',
      ),
    }
    return (
      descriptions[factor] ||
      t(
        'analytics.codebase.bugPrediction.factors.default',
      )
    )
  }

  function getFactorBarClass(value: number): string {
    if (value >= 80) return 'bar-critical'
    if (value >= 50) return 'bar-warning'
    return 'bar-ok'
  }

  const getCoverageClass = (
    percentage: number,
  ): string => {
    if (!percentage || percentage < 50) return 'critical'
    if (percentage < 75) return 'warning'
    if (percentage < 90) return 'info'
    return 'success'
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

  // Cache clearing
  const clearCache = async (
    withSourceIdFn: (url: string) => string,
    localStateResetFn: () => void,
  ) => {
    clearingCache.value = true
    try {
      const backendUrl =
        await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceIdFn(
          `${backendUrl}/api/analytics/codebase/cache`,
        ),
        {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
          },
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(
          `Status ${response.status}: ${errorText}`,
        )
      }
      const result = await response.json()
      localStateResetFn()
      notify(
        t(
          'analytics.codebase.notify.cacheCleared',
          { count: result.deleted_keys || 0 },
        ),
        'success',
      )
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error)
      logger.error('Cache clear failed:', error)
      notify(
        t(
          'analytics.codebase.notify.cacheClearFailed',
          { error: errorMessage },
        ),
        'error',
      )
    } finally {
      clearingCache.value = false
    }
  }

  return {
    // Code Intelligence
    codeIntelLoading,
    codeIntelSuggestions,
    codeIntelSecurityFindings,
    codeIntelPerformanceFindings,
    codeIntelRedisFindings,
    codeIntelFindingsLoading,
    codeIntelFindingsFetched,
    codeIntelTotalFindings,
    runCodeIntelligenceAnalysis,
    handleFileScan,
    // Code smells
    codeSmellsReport,
    codeHealthScore,
    analyzingCodeSmells,
    codeSmellsAnalysisType,
    codeSmellsProgressTitle,
    exportingReport,
    clearingCache,
    runCodeSmellAnalysis,
    getCodeHealthScore,
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
    // Bug prediction
    bugPredictionTask,
    bugPredictionAnalysis,
    loadingBugPrediction,
    bugPredictionError,
    bugRiskFilter,
    bugRiskVisibleCount,
    expandedBugRiskFiles,
    loadBugPrediction,
    loadCachedBugPrediction,
    loadCachedSecurityScore,
    getAtRiskFilesCount,
    toggleBugRiskFilter,
    toggleBugRiskFileExpand,
    getFilteredBugRiskFiles,
    getTopRiskFactors,
    getRiskFactorIcon,
    getRiskFactorDescription,
    getFactorBarClass,
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
    // Cache
    clearCache,
  }
}
