// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useAnalyticsDataFetchers
 *
 * Encapsulates all analytics data fetching: chart data, unified report,
 * call graph, codebase stats, problems, declarations, duplicates, hardcodes,
 * dependency/import-tree task loaders, and cached/full scan orchestration.
 *
 * Issues #2228, #2230: Extracted from CodebaseAnalytics.vue.
 * Issue #5112: the 14x GET-fetcher boilerplate routes through
 * `useFetchEndpoint`. Every call-site opts in to source scoping with an
 * explicit `scopeToSource: true`; `/api/unified/report` is the one
 * exception that stays global. Domain types live in `./analyticsTypes`.
 * Issue #5174: migrated off the deprecated `useAnalyticsEndpoint` alias
 * to the rehomed `@/composables/api/useFetchEndpoint`.
 */

import { ref, reactive, computed, watch, type Ref, type ComputedRef } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useAnalyticsScanRunner } from '@/composables/useAnalyticsScanRunner'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import type { ToastType } from '@/composables/useToast'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { runTimed } from '@/composables/api/useTimedNotify'
import {
  CODE_SMELL_TYPES,
  type Problem,
  type DuplicateCode,
  type Declaration,
  type HardcodedValue,
  type ChartData,
  type DependencyGraph,
  type ImportTreeNode,
  type UnifiedReportData,
  type OrphanedFunction,
} from './analyticsTypes'

export * from './analyticsTypes'

const logger = createLogger('useAnalyticsDataFetchers')

interface CallGraphPayload {
  call_graph: DependencyGraph
  summary: Record<string, unknown> | null
  orphaned_functions: OrphanedFunction[]
}

export interface UseAnalyticsDataFetchersDeps {
  rootPath: Ref<string>
  sourceIdParam: ComputedRef<string>
  sourceIdQuery: ComputedRef<Record<string, string>>
  withSourceId: (url: string) => string
  analyzing: Ref<boolean>
  t: (key: string, params?: Record<string, unknown>) => string
  showToast: (msg: string, type?: ToastType, duration?: number) => number | void
  notify: (msg: string, type?: ToastType) => void
}

export function useAnalyticsDataFetchers(deps: UseAnalyticsDataFetchersDeps) {
  const { rootPath, sourceIdQuery, withSourceId, t, showToast, notify } = deps

  // --- Task loaders (#1304/#1321) ---

  const {
    data: dependencyData,
    loading: dependencyLoading,
    error: dependencyError,
    load: _loadDependencyTask,
  } = useTaskLoader<DependencyGraph>(
    `${getApiBase()}/analytics/codebase/analytics/dependencies`,
    (r) =>
      r.status === 'success' && r.dependency_data
        ? (r.dependency_data as unknown as DependencyGraph)
        : undefined,
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
      return r.status === 'no_data' ? ([] as ImportTreeNode[]) : undefined
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
  const unifiedReport = ref<UnifiedReportData | null>(null)
  const selectedCategory = ref('all')
  const callGraphData = ref<DependencyGraph>({ nodes: [], edges: [] })
  const callGraphSummary = ref<Record<string, unknown> | null>(null)
  const callGraphOrphaned = ref<OrphanedFunction[]>([])

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

  // --- Generic endpoint-backed fetchers (#5112) ---

  const chartEndpoint = useFetchEndpoint<
    { status: string; chart_data?: ChartData },
    ChartData
  >(
    {
      path: '/api/analytics/codebase/analytics/charts',
      scopeToSource: true,
      label: 'Chart data endpoint',
      pickData: (raw) =>
        raw.status === 'success' && raw.chart_data ? raw.chart_data : null,
      onSuccess: (d) =>
        logger.debug('Chart data loaded:', {
          problemTypes: d.problem_types?.length || 0,
          severities: d.severity_counts?.length || 0,
          raceConditions: d.race_conditions?.length || 0,
          topFiles: d.top_files?.length || 0,
        }),
      onNoData: () =>
        logger.debug('No chart data available - run indexing first'),
    },
    { withSourceId },
  )

  const unifiedEndpoint = useFetchEndpoint<
    UnifiedReportData & { status: string },
    UnifiedReportData
  >(
    {
      path: '/api/unified/report',
      scopeToSource: false, // global report — not source-scoped
      label: 'Unified report endpoint',
      pickData: (raw) => (raw.status === 'success' ? raw : null),
      onSuccess: (d) =>
        logger.debug('Unified report loaded:', {
          categories: Object.keys(d.categories || {}).length,
          summary: d.summary,
        }),
      onNoData: () =>
        logger.debug('No unified report data - run indexing first'),
    },
    { withSourceId },
  )
  // Mirror to the historical `unifiedReport` ref shape consumers expect.
  watch(unifiedEndpoint.data, (v) => { unifiedReport.value = v })

  const callGraphEndpoint = useFetchEndpoint<
    {
      status: string
      call_graph?: DependencyGraph
      summary?: Record<string, unknown>
      orphaned_functions?: OrphanedFunction[]
    },
    CallGraphPayload
  >(
    {
      path: '/api/analytics/codebase/analytics/call-graph',
      scopeToSource: true,
      label: 'Call graph endpoint',
      pickData: (raw) =>
        raw.status === 'success' && raw.call_graph
          ? {
              call_graph: raw.call_graph,
              summary: raw.summary ?? null,
              orphaned_functions: raw.orphaned_functions ?? [],
            }
          : null,
      onSuccess: (p) => {
        callGraphData.value = p.call_graph
        callGraphSummary.value = p.summary
        callGraphOrphaned.value = p.orphaned_functions
      },
      onNoData: () => {
        callGraphData.value = { nodes: [], edges: [] }
        callGraphSummary.value = null
        callGraphOrphaned.value = []
      },
    },
    { withSourceId },
  )

  // --- Silent loaders (populate array state, no toasts) ---

  const declarationsSilent = useFetchEndpoint<
    { declarations?: Declaration[] },
    Declaration[]
  >(
    {
      path: '/api/analytics/codebase/declarations',
      scopeToSource: true,
      label: 'Declarations endpoint',
      pickData: (raw) => raw.declarations ?? [],
      onSuccess: (d) => { declarationAnalysis.value = d },
    },
    { withSourceId },
  )

  const hardcodesSilent = useFetchEndpoint<
    { hardcodes?: HardcodedValue[] },
    HardcodedValue[]
  >(
    {
      path: '/api/analytics/codebase/hardcodes',
      scopeToSource: true,
      label: 'Hardcodes endpoint',
      pickData: (raw) => raw.hardcodes ?? [],
      onSuccess: (d) => { hardcodeAnalysis.value = d },
    },
    { withSourceId },
  )

  const duplicatesSilent = useFetchEndpoint<
    { duplicates?: DuplicateCode[] },
    DuplicateCode[]
  >(
    {
      path: '/api/analytics/codebase/duplicates',
      scopeToSource: true,
      label: 'Duplicates endpoint',
      pickData: (raw) => raw.duplicates ?? [],
      onSuccess: (d) => { duplicateAnalysis.value = d },
    },
    { withSourceId },
  )

  const statsEndpoint = useFetchEndpoint<
    { status: string; stats?: Record<string, unknown> },
    Record<string, unknown>
  >(
    {
      path: '/api/analytics/codebase/stats',
      scopeToSource: true,
      label: 'Stats endpoint',
      pickData: (raw) =>
        raw.status === 'success' && raw.stats ? raw.stats : null,
      onSuccess: (d) => { codebaseStats.value = d },
      onNoData: () => {
        codebaseStats.value = null
        logger.debug('No codebase stats - run indexing first')
      },
    },
    { withSourceId },
  )

  const problemsEndpoint = useFetchEndpoint<
    { status?: string; problems?: Problem[] },
    Problem[]
  >(
    {
      path: '/api/analytics/codebase/problems',
      scopeToSource: true,
      label: 'Problems endpoint',
      pickData: (raw) => (raw.status === 'no_data' ? [] : raw.problems ?? []),
      onSuccess: (d) => { problemsReport.value = d },
    },
    { withSourceId },
  )

  const cachedDuplicatesEndpoint = useFetchEndpoint<
    { status: string; duplicates?: DuplicateCode[] },
    DuplicateCode[]
  >(
    {
      path: '/api/analytics/codebase/duplicates/cached',
      scopeToSource: true,
      label: 'Cached duplicates endpoint',
      pickData: (raw) =>
        raw.status === 'success' && Array.isArray(raw.duplicates)
          ? raw.duplicates
          : null,
      onSuccess: (d) => { duplicateAnalysis.value = d },
    },
    { withSourceId },
  )

  const cachedDependenciesEndpoint = useFetchEndpoint<
    { status: string; dependency_data?: unknown },
    DependencyGraph
  >(
    {
      path: '/api/analytics/codebase/analytics/dependencies/cached',
      scopeToSource: true,
      label: 'Cached dependencies endpoint',
      pickData: (raw) =>
        raw.status === 'success' && raw.dependency_data
          ? (raw.dependency_data as DependencyGraph)
          : null,
      onSuccess: (d) => { dependencyData.value = d },
    },
    { withSourceId },
  )

  const cachedImportTreeEndpoint = useFetchEndpoint<
    { status: string; import_tree?: unknown },
    ImportTreeNode[]
  >(
    {
      path: '/api/analytics/codebase/analytics/import-tree/cached',
      scopeToSource: true,
      label: 'Cached import tree endpoint',
      pickData: (raw) =>
        raw.status === 'success' && raw.import_tree
          ? (raw.import_tree as ImportTreeNode[])
          : null,
      onSuccess: (d) => { importTreeData.value = d },
    },
    { withSourceId },
  )

  // --- Loader wrappers: maintain legacy progress flags + status labels ---

  const loadChartData = () => chartEndpoint.load()
  const loadUnifiedReport = () => unifiedEndpoint.load()
  const loadCallGraphData = () => callGraphEndpoint.load()
  const getCodebaseStats = () => statsEndpoint.load()
  const loadCachedDuplicates = () => cachedDuplicatesEndpoint.load()
  const loadCachedDependencies = () => cachedDependenciesEndpoint.load()
  const loadCachedImportTree = () => cachedImportTreeEndpoint.load()
  const loadDependencyData = () => _loadDependencyTask()
  const loadImportTreeData = () => _loadImportTreeTask()

  const loadDeclarations = async () => {
    loadingProgress.declarations = true
    try {
      await declarationsSilent.load()
    } finally {
      loadingProgress.declarations = false
    }
  }

  const loadHardcodes = async () => {
    loadingProgress.hardcodes = true
    try {
      await hardcodesSilent.load()
    } finally {
      loadingProgress.hardcodes = false
    }
  }

  const loadDuplicates = async () => {
    loadingProgress.duplicates = true
    try {
      const ok = await dupTask.start(undefined, sourceIdQuery.value)
      if (ok && dupTask.result.value) {
        const data = dupTask.result.value as Record<string, unknown>
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

  const getProblemsReport = async () => {
    loadingProgress.problems = true
    progressStatus.value = t('analytics.codebase.status.analyzingProblems')
    try {
      await problemsEndpoint.load()
    } finally {
      loadingProgress.problems = false
    }
  }

  /**
   * Shared wrapper for the three toast-emitting loaders. Preserves the
   * count + timing + (for hardcodes) types summary shown to the user.
   * Timing + try/catch kernel lives in `runTimed` (#5153 D-2).
   */
  const notifyTimed = async (
    flag: 'declarations' | 'duplicates' | 'hardcodes',
    statusKey: string,
    runner: () => Promise<
      { count: number; extra?: Record<string, unknown> } | null
    >,
    foundKey: string,
    failedKey: string,
  ) => {
    loadingProgress[flag] = true
    progressStatus.value = t(statusKey)
    await runTimed(
      runner,
      (result, time) => {
        if (result === null) {
          notify(t(failedKey, { error: 'request failed', time }), 'error')
          return
        }
        notify(
          t(foundKey, { count: result.count, time, ...result.extra }),
          'success',
        )
      },
      (errorMessage, time, err) => {
        logger.error(`${flag} failed:`, err)
        notify(t(failedKey, { error: errorMessage, time }), 'error')
      },
    )
    loadingProgress[flag] = false
    progressStatus.value = t('analytics.codebase.status.ready')
  }

  const getDeclarationsData = () =>
    notifyTimed(
      'declarations',
      'analytics.codebase.status.processingDeclarations',
      async () => {
        await declarationsSilent.load()
        if (declarationsSilent.error.value) return null
        return { count: declarationAnalysis.value.length }
      },
      'analytics.codebase.notify.declarationsFound',
      'analytics.codebase.notify.declarationsFailed',
    )

  const getDuplicatesData = () =>
    notifyTimed(
      'duplicates',
      'analytics.codebase.status.findingDuplicates',
      async () => {
        await duplicatesSilent.load()
        if (duplicatesSilent.error.value) return null
        return { count: duplicateAnalysis.value.length }
      },
      'analytics.codebase.notify.duplicatesFound',
      'analytics.codebase.notify.duplicatesFailed',
    )

  const getHardcodesData = () =>
    notifyTimed(
      'hardcodes',
      'analytics.codebase.status.detectingHardcodes',
      async () => {
        await hardcodesSilent.load()
        if (hardcodesSilent.error.value) return null
        const types =
          hardcodeAnalysis.value.length > 0
            ? [...new Set(hardcodeAnalysis.value.map((h) => h.type))].join(
                ', ',
              )
            : 'none'
        return { count: hardcodeAnalysis.value.length, extra: { types } }
      },
      'analytics.codebase.notify.hardcodesFound',
      'analytics.codebase.notify.hardcodesFailed',
    )

  // --- Computed ---

  const hasAnyResults = computed(
    () =>
      !!(
        codebaseStats.value ||
        problemsReport.value.length > 0 ||
        declarationAnalysis.value.length > 0 ||
        duplicateAnalysis.value.length > 0
      ),
  )

  const availableCategories = computed(() => {
    if (!unifiedReport.value?.categories) return []
    const categories = unifiedReport.value.categories
    return Object.keys(categories).map((key) => ({
      id: key,
      name: key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c: string) => c.toUpperCase()),
      count: Array.isArray(categories[key]) ? categories[key].length : 0,
    }))
  })

  const codeSmellsFromProblems = computed(() =>
    !problemsReport.value || problemsReport.value.length === 0
      ? []
      : problemsReport.value.filter(
          (p) => p.type && CODE_SMELL_TYPES.has(p.type),
        ),
  )

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

  // --- Config load ---

  const loadProjectRoot = async () => {
    const saved = localStorage.getItem('codebase-analytics-path')
    if (saved) {
      logger.debug('Using saved path from localStorage:', saved)
      return
    }
    try {
      const projectRoot = await appConfig.getProjectRoot()
      if (projectRoot) {
        rootPath.value = projectRoot
      } else {
        logger.warn('Project root not found in config, using default')
      }
    } catch (error: unknown) {
      logger.error('Failed to load project root:', error)
      progressStatus.value = t('analytics.codebase.status.enterProjectPath')
    }
  }

  // --- Scan orchestration ---

  const buildScanList = (useFullScans: boolean) => [
    { id: 'stats', label: t('analytics.codebase.scans.stats'), run: getCodebaseStats },
    { id: 'problems', label: t('analytics.codebase.scans.problems'), run: getProblemsReport },
    { id: 'declarations', label: t('analytics.codebase.scans.declarations'), run: loadDeclarations },
    {
      id: 'duplicates',
      label: t('analytics.codebase.scans.duplicates'),
      run: () => (useFullScans ? loadDuplicates() : loadCachedDuplicates()),
    },
    { id: 'hardcodes', label: t('analytics.codebase.scans.hardcodes'), run: loadHardcodes },
    { id: 'charts', label: t('analytics.codebase.scans.charts'), run: loadChartData },
    {
      id: 'dependencies',
      label: t('analytics.codebase.scans.dependencies'),
      run: useFullScans
        ? async () => { await loadDependencyData() }
        : () => loadCachedDependencies(),
    },
    {
      id: 'imports',
      label: t('analytics.codebase.scans.imports'),
      run: useFullScans
        ? async () => { await loadImportTreeData() }
        : () => loadCachedImportTree(),
    },
    { id: 'callgraph', label: t('analytics.codebase.scans.callGraph'), run: loadCallGraphData },
  ]

  const runScans = async (
    useFullScans: boolean,
    extraScans: Array<{ id: string; label: string; run: () => Promise<void> }>,
    failLogPrefix: string,
  ) => {
    try {
      await scanRunner.runAll([...buildScanList(useFullScans), ...extraScans])
      if (scanRunner.failedCount.value > 0) {
        progressStatus.value = t(
          'analytics.codebase.status.loadPartialFailed',
          { failed: scanRunner.failedCount.value, total: scanRunner.totalCount.value },
        )
      } else {
        progressStatus.value = t('analytics.codebase.status.loadComplete')
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error(failLogPrefix, error)
      progressStatus.value = t('analytics.codebase.status.loadFailed', {
        error: errorMessage,
      })
    }
  }

  const loadCachedAnalyticsData = (
    extraScans: Array<{ id: string; label: string; run: () => Promise<void> }>,
  ) => runScans(false, extraScans, 'Failed to load cached analytics data:')

  const runAllAnalysisScans = (
    extraScans: Array<{ id: string; label: string; run: () => Promise<void> }>,
  ) => runScans(true, extraScans, 'Failed to load codebase analytics data:')

  // --- Navigation helpers ---

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
    chartData: chartEndpoint.data,
    chartDataLoading: chartEndpoint.loading,
    chartDataError: chartEndpoint.error,
    unifiedReport,
    unifiedReportLoading: unifiedEndpoint.loading,
    unifiedReportError: unifiedEndpoint.error,
    selectedCategory,
    callGraphData,
    callGraphSummary,
    callGraphOrphaned,
    callGraphLoading: callGraphEndpoint.loading,
    callGraphError: callGraphEndpoint.error,
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
