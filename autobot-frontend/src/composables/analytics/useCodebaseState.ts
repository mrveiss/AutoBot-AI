// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Composable: useCodebaseState
 * All reactive state declarations for CodebaseAnalytics.vue.
 * Issue #2228/#2230: Extracted from CodebaseAnalytics.vue script section.
 */
import { ref, reactive, computed } from 'vue'
import { useRoute } from 'vue-router'
import type {
  CodeSource, Problem, DuplicateCode, Declaration, HardcodedValue,
  RefactoringSuggestion, CodeSmellsReportData, CodeHealthScoreData,
  SystemOverviewData, CommunicationPatternsData, CodeQualityData,
  PerformanceMetricsData, ChartData, UnifiedReportData, DependencyGraph,
  OrphanedFunction, CrossLanguageAnalysisResult, EnvironmentAnalysisResult,
  LlmFilteringResult, RedisHealthResult, JobPhasesData, JobBatchesData,
  JobStatsData, PatternAnalysisComponent,
} from '@/types/codebaseAnalytics'

const STORAGE_KEY_PATH = 'codebase-analytics-path'

export function useCodebaseState() {
  const route = useRoute()
  const savedPath = localStorage.getItem(STORAGE_KEY_PATH)
  const rootPath = ref(savedPath || '/opt/autobot')

  const sources = ref<CodeSource[]>([])
  const selectedSource = ref<CodeSource | null>(null)
  const showSourceManager = ref(false)
  const showAddSourceModal = ref(false)
  const showShareSourceModal = ref(false)
  const editTargetSource = ref<CodeSource | null>(null)
  const shareTargetSource = ref<CodeSource | null>(null)
  const showKnowledgeBaseOptIn = ref(false)
  const knowledgeBaseAdding = ref(false)

  const sourceIdParam = computed(() => {
    const sid = selectedSource.value?.id || (route.params.sourceId as string)
    return sid ? `source_id=${encodeURIComponent(sid)}` : ''
  })
  function withSourceId(url: string): string {
    if (!sourceIdParam.value) return url
    const sep = url.includes('?') ? '&' : '?'
    return `${url}${sep}${sourceIdParam.value}`
  }
  const sourceIdQuery = computed((): Record<string, string> => {
    const sid = selectedSource.value?.id || (route.params.sourceId as string)
    return sid ? { source_id: sid } : {}
  })

  const analyzing = ref(false)
  const progressPercent = ref(0)
  const progressStatus = ref('Ready')
  const realTimeEnabled = ref(false)
  const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)
  const currentJobId = ref<string | null>(null)
  const currentJobStatus = ref<string | null>(null)
  const jobPollingInterval = ref<ReturnType<typeof setInterval> | null>(null)
  const jobPhases = ref<JobPhasesData | null>(null)
  const jobBatches = ref<JobBatchesData | null>(null)
  const jobStats = ref<JobStatsData | null>(null)

  const codebaseStats = ref<Record<string, unknown> | null>(null)
  const problemsReport = ref<Problem[]>([])
  const duplicateAnalysis = ref<DuplicateCode[]>([])
  const declarationAnalysis = ref<Declaration[]>([])
  const hardcodeAnalysis = ref<HardcodedValue[]>([])
  const refactoringSuggestions = ref<RefactoringSuggestion[]>([])

  const codeSmellsReport = ref<CodeSmellsReportData | null>(null)
  const codeHealthScore = ref<CodeHealthScoreData | null>(null)
  const analyzingCodeSmells = ref(false)
  const codeSmellsAnalysisType = ref('')
  const exportingReport = ref(false)
  const clearingCache = ref(false)

  const systemOverview = ref<SystemOverviewData | null>(null)
  const communicationPatterns = ref<CommunicationPatternsData | null>(null)
  const codeQuality = ref<CodeQualityData | null>(null)
  const performanceMetrics = ref<PerformanceMetricsData | null>(null)

  const chartData = ref<ChartData | null>(null)
  const chartDataLoading = ref(false)
  const chartDataError = ref('')
  const unifiedReport = ref<UnifiedReportData | null>(null)
  const unifiedReportLoading = ref(false)
  const unifiedReportError = ref('')
  const selectedCategory = ref('all')

  const callGraphData = ref<DependencyGraph>({ nodes: [], edges: [] })
  const callGraphSummary = ref<Record<string, unknown> | null>(null)
  const callGraphOrphaned = ref<OrphanedFunction[]>([])
  const callGraphLoading = ref(false)
  const callGraphError = ref('')

  const crossLanguageAnalysis = ref<CrossLanguageAnalysisResult | null>(null)
  const loadingCrossLanguage = ref(false)
  const crossLanguageError = ref('')
  const expandedCrossLanguageGroups = reactive({ dtoMismatches: false, apiMismatches: false, validationDups: false, semanticMatches: false })

  const environmentAnalysis = ref<EnvironmentAnalysisResult | null>(null)
  const loadingEnvAnalysis = ref(false)
  const envAnalysisError = ref('')
  const useAiFiltering = ref(false)
  const aiFilteringModel = ref('llama3.2:1b')
  const aiFilteringPriority = ref('high')
  const llmFilteringResult = ref<LlmFilteringResult | null>(null)

  const redisHealth = ref<RedisHealthResult | null>(null)
  const loadingRedisHealth = ref(false)
  const redisHealthError = ref('')

  const loadingProgress = reactive({ declarations: false, duplicates: false, hardcodes: false, problems: false })
  const showAllProblems = ref(false)
  const showAllDeclarations = ref(false)
  const showAllDuplicates = ref(false)
  const expandedApiEndpointGroups = reactive({ orphaned: false, missing: false, used: false })
  const patternAnalysisRef = ref<PatternAnalysisComponent | null>(null)

  const codeIntelFindingsLoading = ref(false)
  const codeIntelFindingsFetched = ref({ security: false, performance: false, redis: false })
  const showSecurityDetails = ref(false)
  const showPerformanceDetails = ref(false)
  const showRedisDetails = ref(false)

  const bugRiskFilter = ref<'all' | 'high' | 'medium' | 'low'>('all')
  const BUG_RISK_PAGE_SIZE = 50
  const bugRiskVisibleCount = ref(BUG_RISK_PAGE_SIZE)
  const expandedBugRiskFiles = ref<Set<string>>(new Set())
  const ownershipViewMode = ref<'overview' | 'files' | 'contributors' | 'gaps'>('overview')

  return {
    STORAGE_KEY_PATH, rootPath, sources, selectedSource, showSourceManager,
    showAddSourceModal, showShareSourceModal, editTargetSource, shareTargetSource,
    showKnowledgeBaseOptIn, knowledgeBaseAdding, sourceIdParam, withSourceId,
    sourceIdQuery, analyzing, progressPercent, progressStatus, realTimeEnabled,
    refreshInterval, currentJobId, currentJobStatus, jobPollingInterval, jobPhases,
    jobBatches, jobStats, codebaseStats, problemsReport, duplicateAnalysis,
    declarationAnalysis, hardcodeAnalysis, refactoringSuggestions, codeSmellsReport,
    codeHealthScore, analyzingCodeSmells, codeSmellsAnalysisType, exportingReport,
    clearingCache, systemOverview, communicationPatterns, codeQuality, performanceMetrics,
    chartData, chartDataLoading, chartDataError, unifiedReport, unifiedReportLoading,
    unifiedReportError, selectedCategory, callGraphData, callGraphSummary,
    callGraphOrphaned, callGraphLoading, callGraphError, crossLanguageAnalysis,
    loadingCrossLanguage, crossLanguageError, expandedCrossLanguageGroups,
    environmentAnalysis, loadingEnvAnalysis, envAnalysisError, useAiFiltering,
    aiFilteringModel, aiFilteringPriority, llmFilteringResult, redisHealth,
    loadingRedisHealth, redisHealthError, loadingProgress, showAllProblems,
    showAllDeclarations, showAllDuplicates, expandedApiEndpointGroups,
    patternAnalysisRef, codeIntelFindingsLoading, codeIntelFindingsFetched,
    showSecurityDetails, showPerformanceDetails, showRedisDetails, bugRiskFilter,
    BUG_RISK_PAGE_SIZE, bugRiskVisibleCount, expandedBugRiskFiles, ownershipViewMode,
  }
}
