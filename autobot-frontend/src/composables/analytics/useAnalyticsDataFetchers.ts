// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useAnalyticsDataFetchers
 *
 * Encapsulates all analytics data fetching: chart data, unified report,
 * call graph, codebase stats, problems, declarations, duplicates, hardcodes,
 * dependency/import-tree task loaders, and cached/full scan orchestration.
 *
 * Issues #2228, #2230: Extracted from CodebaseAnalytics.vue
 */

import { ref, reactive, computed, type Ref, type ComputedRef } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useAnalyticsScanRunner } from '@/composables/useAnalyticsScanRunner'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useAnalyticsDataFetchers')

// --- Type definitions ---

export interface Problem {
  severity: string
  type: string
  message: string
  description?: string
  file_path: string
  line?: number
  line_number?: number
  category?: string
  suggestion?: string
}

export interface DuplicateCode {
  similarity: number
  lines: number
  file1: string
  file2: string
  start1?: number
  start2?: number
}

export interface Declaration {
  type: string
  name: string
  file_path: string
  line?: number
  line_number?: number
  is_exported?: boolean
}

export interface HardcodedValue {
  file: string
  line: number
  variable_name?: string
  value: string
  type: string
  severity: string
  suggested_env_var: string
  context?: string
  current_usage?: string
}

export interface RefactoringSuggestion {
  type: string
  severity: string
  description: string
  file_path: string
  line?: number
  suggestion: string
}

export interface ChartDataItem {
  name: string
  value: number
  type?: string
  [key: string]: unknown
}

export interface ChartDataSummary {
  total_problems?: number
  unique_problem_types?: number
  files_with_problems?: number
  race_condition_count?: number
}

export interface ChartData {
  summary?: ChartDataSummary
  problem_types?: ChartDataItem[]
  severity_counts?: ChartDataItem[]
  race_conditions?: ChartDataItem[]
  top_files?: ChartDataItem[]
  [key: string]: unknown
}

export interface DependencyNode {
  id: string
  name: string
  type?: string
}

export interface DependencyEdge {
  source: string
  target: string
  type?: string
}

export interface ModuleData {
  name: string
  path?: string
  import_count: number
  [key: string]: unknown
}

export interface ExternalDependency {
  name: string
  usage_count?: number
  [key: string]: unknown
}

export type CircularDependency =
  | string[]
  | {
      modules: string[]
      cycle?: string[]
      length?: number
      severity?: string
    }

export interface DependencySummary {
  total_modules?: number
  total_import_relationships?: number
  external_dependency_count?: number
  circular_dependency_count?: number
}

export interface DependencyGraph {
  nodes: DependencyNode[]
  edges: DependencyEdge[]
  summary?: DependencySummary
  modules?: ModuleData[]
  external_dependencies?: ExternalDependency[]
  circular_dependencies?: CircularDependency[]
  import_relationships?: DependencyEdge[]
}

export interface ImportTreeNode {
  name: string
  path: string
  children?: ImportTreeNode[]
  imports?: string[]
}

export interface UnifiedReportData {
  categories: Record<string, Problem[]>
  summary: {
    total: number
    by_severity: Record<string, number>
    by_category: Record<string, number>
  }
  timestamp: string
}

interface OrphanedFunction {
  id: string
  name: string
  full_name: string
  module: string
  class: string | null
  file: string
  line: number
  is_async: boolean
}

// Issue #609: Code smell types for filtering
const CODE_SMELL_TYPES = new Set([
  'long_function',
  'debug_code',
  'race_condition',
  'technical_debt_bug',
  'technical_debt_todo',
  'technical_debt_fixme',
  'technical_debt_deprecated',
  'performance_nested_loop_complexity',
  'performance_quadratic_complexity',
  'performance_n_plus_one_query',
  'performance_blocking_io_in_async',
  'performance_excessive_string_concat',
  'performance_list_for_lookup',
  'performance_repeated_computation',
  'performance_repeated_file_open',
  'performance_sequential_awaits',
  'performance_unbatched_api_calls',
])

export interface UseAnalyticsDataFetchersDeps {
  rootPath: Ref<string>
  sourceIdParam: ComputedRef<string>
  sourceIdQuery: ComputedRef<Record<string, string>>
  withSourceId: (url: string) => string
  analyzing: Ref<boolean>
  t: (key: string, params?: Record<string, unknown>) => string
  showToast: (msg: string, type?: string, duration?: number) => void
  notify: (msg: string, type?: string) => void
}

export function useAnalyticsDataFetchers(
  deps: UseAnalyticsDataFetchersDeps,
) {
  const {
    rootPath,
    sourceIdQuery,
    withSourceId,
    t,
    showToast,
    notify,
  } = deps

  // --- Task loaders (#1304/#1321) ---

  const {
    data: dependencyData,
    loading: dependencyLoading,
    error: dependencyError,
    load: _loadDependencyTask,
  } = useTaskLoader<DependencyGraph>(
    `${getApiBase()}/analytics/codebase/analytics/dependencies`,
    (r) => {
      if (r.status === 'success' && r.dependency_data) {
        return r.dependency_data as unknown as DependencyGraph
      }
      return undefined
    },
  )

  const {
    data: importTreeData,
    loading: importTreeLoading,
    error: importTreeError,
    load: _loadImportTreeTask,
  } = useTaskLoader<ImportTreeNode[]>(
    `${getApiBase()}/analytics/codebase/analytics/import-tree`,
    (r) => {
      if (r.status === 'success' && r.import_tree) {
        return r.import_tree as unknown as ImportTreeNode[]
      }
      return r.status === 'no_data'
        ? ([] as ImportTreeNode[])
        : undefined
    },
  )

  const dupTask = useBackgroundTask(
    `${getApiBase()}/analytics/codebase/duplicates`,
  )

  const scanRunner = useAnalyticsScanRunner()

  // --- Reactive state ---

  const codebaseStats = ref<Record<string, unknown> | null>(null)
  const problemsReport = ref<Problem[]>([])
  const duplicateAnalysis = ref<DuplicateCode[]>([])
  const declarationAnalysis = ref<Declaration[]>([])
  const hardcodeAnalysis = ref<HardcodedValue[]>([])
  const refactoringSuggestions = ref<RefactoringSuggestion[]>([])

  const chartData = ref<ChartData | null>(null)
  const chartDataLoading = ref(false)
  const chartDataError = ref('')

  const unifiedReport = ref<UnifiedReportData | null>(null)
  const unifiedReportLoading = ref(false)
  const unifiedReportError = ref('')
  const selectedCategory = ref('all')

  const callGraphData = ref<DependencyGraph>({
    nodes: [],
    edges: [],
  })
  const callGraphSummary = ref<Record<string, unknown> | null>(null)
  const callGraphOrphaned = ref<OrphanedFunction[]>([])
  const callGraphLoading = ref(false)
  const callGraphError = ref('')

  const loadingProgress = reactive({
    declarations: false,
    duplicates: false,
    hardcodes: false,
    problems: false,
  })

  const showAllProblems = ref(false)
  const showAllDeclarations = ref(false)
  const showAllDuplicates = ref(false)

  const progressPercent = ref(0)
  const progressStatus = ref('Ready')

  // --- Computed ---

  const hasAnyResults = computed(() => {
    return !!(
      codebaseStats.value ||
      problemsReport.value.length > 0 ||
      declarationAnalysis.value.length > 0 ||
      duplicateAnalysis.value.length > 0
    )
  })

  const availableCategories = computed(() => {
    if (!unifiedReport.value?.categories) return []
    const categories = unifiedReport.value.categories
    return Object.keys(categories).map((key) => ({
      id: key,
      name: key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c: string) => c.toUpperCase()),
      count: Array.isArray(categories[key])
        ? categories[key].length
        : 0,
    }))
  })

  const codeSmellsFromProblems = computed(() => {
    if (!problemsReport.value || problemsReport.value.length === 0)
      return []
    return problemsReport.value.filter(
      (p) => p.type && CODE_SMELL_TYPES.has(p.type),
    )
  })

  const codeSmellsForPanel = computed(() =>
    codeSmellsFromProblems.value.map((p) => ({
      severity: p.severity,
      description: p.description || p.message,
      file_path: p.file_path,
      line_number: p.line_number ?? p.line,
      suggestion: p.suggestion,
      smell_type: p.type,
    })),
  )

  const declarationsForPanel = computed(() =>
    declarationAnalysis.value.map((d) => ({
      name: d.name,
      file_path: d.file_path,
      line_number: d.line_number ?? d.line ?? 0,
      is_exported: d.is_exported ?? false,
      declaration_type: d.type,
    })),
  )

  // --- Data loaders ---

  const loadChartData = async () => {
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
          problemTypes:
            data.chart_data.problem_types?.length || 0,
          severities:
            data.chart_data.severity_counts?.length || 0,
          raceConditions:
            data.chart_data.race_conditions?.length || 0,
          topFiles: data.chart_data.top_files?.length || 0,
        })
      } else if (data.status === 'no_data') {
        chartData.value = null
        logger.debug(
          'No chart data available - run indexing first',
        )
      }
    } catch (error: unknown) {
      logger.error('Failed to load chart data:', error)
      chartDataError.value =
        error instanceof Error ? error.message : String(error)
    } finally {
      chartDataLoading.value = false
    }
  }

  const loadUnifiedReport = async () => {
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

  const loadCallGraphData = async () => {
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
        callGraphOrphaned.value =
          data.orphaned_functions || []
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
        logger.debug(
          'No call graph data - run indexing first',
        )
      }
    } catch (error: unknown) {
      logger.error('Failed to load call graph:', error)
      callGraphError.value =
        error instanceof Error ? error.message : String(error)
    } finally {
      callGraphLoading.value = false
    }
  }

  const handleFileNavigate = (filePath: string) => {
    logger.debug('Navigate to file:', filePath)
    showToast(
      t('analytics.codebase.notify.selected', { item: filePath }),
      'info',
      2000,
    )
  }

  const handleFunctionSelect = (funcId: string) => {
    logger.debug('Selected function:', funcId)
    showToast(
      t('analytics.codebase.notify.selected', { item: funcId }),
      'info',
      2000,
    )
  }

  const loadDeclarations = async () => {
    loadingProgress.declarations = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const declarationsEndpoint = withSourceId(
        `${backendUrl}/api/analytics/codebase/declarations`,
      )
      const response = await fetchWithAuth(declarationsEndpoint, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        throw new Error(
          `Declarations endpoint returned ${response.status}`,
        )
      }
      const data = await response.json()
      declarationAnalysis.value = data.declarations || []
    } catch (error: unknown) {
      logger.error('Failed to load declarations:', error)
    } finally {
      loadingProgress.declarations = false
    }
  }

  const loadDuplicates = async () => {
    loadingProgress.duplicates = true
    try {
      const ok = await dupTask.start(
        undefined,
        sourceIdQuery.value,
      )
      if (ok && dupTask.result.value) {
        const data = dupTask.result.value as Record<
          string,
          unknown
        >
        duplicateAnalysis.value = Array.isArray(data.duplicates)
          ? (data.duplicates as DuplicateCode[])
          : []
      }
    } catch (error: unknown) {
      logger.error('Failed to load duplicates:', error)
    } finally {
      loadingProgress.duplicates = false
    }
  }

  const loadHardcodes = async () => {
    loadingProgress.hardcodes = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const hardcodesEndpoint = withSourceId(
        `${backendUrl}/api/analytics/codebase/hardcodes`,
      )
      const response = await fetchWithAuth(hardcodesEndpoint, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        throw new Error(
          `Hardcodes endpoint returned ${response.status}`,
        )
      }
      const data = await response.json()
      hardcodeAnalysis.value = data.hardcodes || []
    } catch (error: unknown) {
      logger.error('Failed to load hardcodes:', error)
    } finally {
      loadingProgress.hardcodes = false
    }
  }

  const loadDependencyData = () => _loadDependencyTask()
  const loadImportTreeData = () => _loadImportTreeTask()

  // --- Fetch project root from config ---

  const loadProjectRoot = async () => {
    const saved = localStorage.getItem('codebase-analytics-path')
    if (saved) {
      logger.debug(
        'Using saved path from localStorage:',
        saved,
      )
      return
    }
    try {
      const projectRoot = await appConfig.getProjectRoot()
      if (projectRoot) {
        rootPath.value = projectRoot
      } else {
        logger.warn(
          'Project root not found in config, using default',
        )
      }
    } catch (error: unknown) {
      logger.error('Failed to load project root:', error)
      progressStatus.value = t(
        'analytics.codebase.status.enterProjectPath',
      )
    }
  }

  // --- Debug button fetch functions ---

  const getCodebaseStats = async () => {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const statsEndpoint = `${backendUrl}/api/analytics/codebase/stats`
      const response = await fetchWithAuth(statsEndpoint)
      if (!response.ok) {
        throw new Error(
          `Stats endpoint returned ${response.status}`,
        )
      }
      const data = await response.json()
      if (data.status === 'success' && data.stats) {
        codebaseStats.value = data.stats
      } else if (
        data.status === 'no_data' ||
        data.status === 'indexing'
      ) {
        codebaseStats.value = null
        logger.debug(
          'No codebase stats - run indexing first',
        )
      }
    } catch (error: unknown) {
      logger.error('Failed to get stats:', error)
    }
  }

  const getProblemsReport = async () => {
    loadingProgress.problems = true
    progressStatus.value = t(
      'analytics.codebase.status.analyzingProblems',
    )
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const problemsEndpoint = `${backendUrl}/api/analytics/codebase/problems`
      const response = await fetchWithAuth(problemsEndpoint)
      if (!response.ok) {
        throw new Error(
          `Problems endpoint returned ${response.status}`,
        )
      }
      const data = await response.json()
      if (data.status === 'no_data') {
        problemsReport.value = []
        logger.debug(
          'No problems report - run indexing first',
        )
      } else {
        problemsReport.value = data.problems || []
      }
    } catch (error: unknown) {
      logger.error('Failed to get problems:', error)
    } finally {
      loadingProgress.problems = false
    }
  }

  const getDeclarationsData = async () => {
    const startTime = Date.now()
    loadingProgress.declarations = true
    progressStatus.value = t(
      'analytics.codebase.status.processingDeclarations',
    )
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const declarationsEndpoint = withSourceId(
        `${backendUrl}/api/analytics/codebase/declarations`,
      )
      const response = await fetchWithAuth(declarationsEndpoint, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      declarationAnalysis.value = data.declarations || []
      notify(
        t('analytics.codebase.notify.declarationsFound', {
          count: declarationAnalysis.value.length,
          time: responseTime,
        }),
        'success',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Declarations failed:', error)
      notify(
        t('analytics.codebase.notify.declarationsFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      loadingProgress.declarations = false
      progressStatus.value = t(
        'analytics.codebase.status.ready',
      )
    }
  }

  const getDuplicatesData = async () => {
    loadingProgress.duplicates = true
    progressStatus.value = t(
      'analytics.codebase.status.findingDuplicates',
    )
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const duplicatesEndpoint = withSourceId(
        `${backendUrl}/api/analytics/codebase/duplicates`,
      )
      const response = await fetchWithAuth(duplicatesEndpoint, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      duplicateAnalysis.value = data.duplicates || []
      notify(
        t('analytics.codebase.notify.duplicatesFound', {
          count: duplicateAnalysis.value.length,
          time: responseTime,
        }),
        'success',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Duplicates failed:', error)
      notify(
        t('analytics.codebase.notify.duplicatesFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      loadingProgress.duplicates = false
      progressStatus.value = t(
        'analytics.codebase.status.ready',
      )
    }
  }

  const getHardcodesData = async () => {
    loadingProgress.hardcodes = true
    progressStatus.value = t(
      'analytics.codebase.status.detectingHardcodes',
    )
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const hardcodesEndpoint = withSourceId(
        `${backendUrl}/api/analytics/codebase/hardcodes`,
      )
      const response = await fetchWithAuth(hardcodesEndpoint, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      hardcodeAnalysis.value = data.hardcodes || []
      const hardcodeCount = hardcodeAnalysis.value.length
      const hardcodeTypes =
        hardcodeCount > 0
          ? [
              ...new Set(
                hardcodeAnalysis.value.map((h) => h.type),
              ),
            ].join(', ')
          : 'none'
      notify(
        t('analytics.codebase.notify.hardcodesFound', {
          count: hardcodeCount,
          types: hardcodeTypes,
          time: responseTime,
        }),
        'success',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Hardcodes failed:', error)
      notify(
        t('analytics.codebase.notify.hardcodesFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      loadingProgress.hardcodes = false
      progressStatus.value = t(
        'analytics.codebase.status.ready',
      )
    }
  }

  // --- Cached loaders (#1540) ---

  const loadCachedDuplicates = async () => {
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
      duplicateAnalysis.value =
        data.duplicates as DuplicateCode[]
    }
  }

  const loadCachedDependencies = async () => {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      withSourceId(
        `${backendUrl}/api/analytics/codebase/analytics/dependencies/cached`,
      ),
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.dependency_data) {
      dependencyData.value =
        data.dependency_data as unknown as DependencyGraph
    }
  }

  const loadCachedImportTree = async () => {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      withSourceId(
        `${backendUrl}/api/analytics/codebase/analytics/import-tree/cached`,
      ),
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status === 'success' && data.import_tree) {
      importTreeData.value =
        data.import_tree as unknown as ImportTreeNode[]
    }
  }

  // --- Scan orchestration ---

  const loadCachedAnalyticsData = async (
    extraScans: Array<{
      id: string
      label: string
      run: () => Promise<void>
    }>,
  ) => {
    try {
      await scanRunner.runAll([
        {
          id: 'stats',
          label: t('analytics.codebase.scans.stats'),
          run: () => getCodebaseStats(),
        },
        {
          id: 'problems',
          label: t('analytics.codebase.scans.problems'),
          run: () => getProblemsReport(),
        },
        {
          id: 'declarations',
          label: t('analytics.codebase.scans.declarations'),
          run: () => loadDeclarations(),
        },
        {
          id: 'duplicates',
          label: t('analytics.codebase.scans.duplicates'),
          run: () => loadCachedDuplicates(),
        },
        {
          id: 'hardcodes',
          label: t('analytics.codebase.scans.hardcodes'),
          run: () => loadHardcodes(),
        },
        {
          id: 'charts',
          label: t('analytics.codebase.scans.charts'),
          run: () => loadChartData(),
        },
        {
          id: 'dependencies',
          label: t('analytics.codebase.scans.dependencies'),
          run: () => loadCachedDependencies(),
        },
        {
          id: 'imports',
          label: t('analytics.codebase.scans.imports'),
          run: () => loadCachedImportTree(),
        },
        {
          id: 'callgraph',
          label: t('analytics.codebase.scans.callGraph'),
          run: () => loadCallGraphData(),
        },
        ...extraScans,
      ])

      if (scanRunner.failedCount.value > 0) {
        progressStatus.value = t(
          'analytics.codebase.status.loadPartialFailed',
          {
            failed: scanRunner.failedCount.value,
            total: scanRunner.totalCount.value,
          },
        )
      } else {
        progressStatus.value = t(
          'analytics.codebase.status.loadComplete',
        )
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error(
        'Failed to load cached analytics data:',
        error,
      )
      progressStatus.value = t(
        'analytics.codebase.status.loadFailed',
        { error: errorMessage },
      )
    }
  }

  const runAllAnalysisScans = async (
    extraScans: Array<{
      id: string
      label: string
      run: () => Promise<void>
    }>,
  ) => {
    try {
      await scanRunner.runAll([
        {
          id: 'stats',
          label: t('analytics.codebase.scans.stats'),
          run: () => getCodebaseStats(),
        },
        {
          id: 'problems',
          label: t('analytics.codebase.scans.problems'),
          run: () => getProblemsReport(),
        },
        {
          id: 'declarations',
          label: t('analytics.codebase.scans.declarations'),
          run: () => loadDeclarations(),
        },
        {
          id: 'duplicates',
          label: t('analytics.codebase.scans.duplicates'),
          run: () => loadDuplicates(),
        },
        {
          id: 'hardcodes',
          label: t('analytics.codebase.scans.hardcodes'),
          run: () => loadHardcodes(),
        },
        {
          id: 'charts',
          label: t('analytics.codebase.scans.charts'),
          run: () => loadChartData(),
        },
        {
          id: 'dependencies',
          label: t('analytics.codebase.scans.dependencies'),
          run: () => loadDependencyData(),
        },
        {
          id: 'imports',
          label: t('analytics.codebase.scans.imports'),
          run: () => loadImportTreeData(),
        },
        {
          id: 'callgraph',
          label: t('analytics.codebase.scans.callGraph'),
          run: () => loadCallGraphData(),
        },
        ...extraScans,
      ])

      if (scanRunner.failedCount.value > 0) {
        progressStatus.value = t(
          'analytics.codebase.status.loadPartialFailed',
          {
            failed: scanRunner.failedCount.value,
            total: scanRunner.totalCount.value,
          },
        )
      } else {
        progressStatus.value = t(
          'analytics.codebase.status.loadComplete',
        )
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error(
        'Failed to load codebase analytics data:',
        error,
      )
      progressStatus.value = t(
        'analytics.codebase.status.loadFailed',
        { error: errorMessage },
      )
    }
  }

  return {
    // Task loaders
    dependencyData,
    dependencyLoading,
    dependencyError,
    importTreeData,
    importTreeLoading,
    importTreeError,
    dupTask,
    scanRunner,
    // State
    codebaseStats,
    problemsReport,
    duplicateAnalysis,
    declarationAnalysis,
    hardcodeAnalysis,
    refactoringSuggestions,
    chartData,
    chartDataLoading,
    chartDataError,
    unifiedReport,
    unifiedReportLoading,
    unifiedReportError,
    selectedCategory,
    callGraphData,
    callGraphSummary,
    callGraphOrphaned,
    callGraphLoading,
    callGraphError,
    loadingProgress,
    showAllProblems,
    showAllDeclarations,
    showAllDuplicates,
    progressPercent,
    progressStatus,
    // Computed
    hasAnyResults,
    availableCategories,
    codeSmellsFromProblems,
    codeSmellsForPanel,
    declarationsForPanel,
    // Data loaders
    loadChartData,
    loadUnifiedReport,
    loadCallGraphData,
    handleFileNavigate,
    handleFunctionSelect,
    loadDeclarations,
    loadDuplicates,
    loadHardcodes,
    loadDependencyData,
    loadImportTreeData,
    loadProjectRoot,
    getCodebaseStats,
    getProblemsReport,
    getDeclarationsData,
    getDuplicatesData,
    getHardcodesData,
    // Cached loaders
    loadCachedDuplicates,
    loadCachedDependencies,
    loadCachedImportTree,
    // Scan orchestration
    loadCachedAnalyticsData,
    runAllAnalysisScans,
  }
}
