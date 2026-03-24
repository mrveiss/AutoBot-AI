<template>
  <div class="codebase-analytics">
    <!-- Issue #1469: Header + Debug Controls (extracted) -->
    <CodebaseAnalyticsHeader
      :analyzing="analyzing"
      :scan-runner-running="scanRunner.running.value"
      :root-path="rootPath"
      :selected-source="selectedSource"
      :loading-api-endpoints="loadingApiEndpoints"
      :analyzing-code-smells="analyzingCodeSmells"
      :exporting-report="exportingReport"
      :clearing-cache="clearingCache"
      @index-codebase="indexCodebase"
      @stop="handleStop"
      @run-full-analysis="runFullAnalysis"
      @test-declarations="getDeclarationsData"
      @test-duplicates="getDuplicatesData"
      @test-hardcodes="getHardcodesData"
      @test-npu="testNpuConnection"
      @test-data-state="testDataState"
      @reset-state="resetState"
      @test-all-endpoints="testAllEndpoints"
      @get-api-coverage="getApiEndpointCoverage"
      @run-code-smells="runCodeSmellAnalysis"
      @get-health-score="getCodeHealthScore"
      @export-report="exportReport()"
      @clear-cache="clearCache"
    />

    <!-- Issue #1469: Progress tracking (extracted) -->
    <CodebaseProgressPanel
      :analyzing="analyzing"
      :analyzing-code-smells="analyzingCodeSmells"
      :progress-percent="progressPercent"
      :progress-status="progressStatus"
      :current-job-id="currentJobId"
      :job-phases="jobPhases"
      :job-batches="jobBatches"
      :job-stats="jobStats"
      :code-smells-progress-title="codeSmellsProgressTitle"
      :scan-runner-running="scanRunner.running.value"
      :scan-runner-results="scanRunner.results.value"
      :scan-runner-completed-count="scanRunner.completedCount.value"
      :scan-runner-total-count="scanRunner.totalCount.value"
      :scan-runner-progress="scanRunner.progress.value"
    />

    <!-- Empty state when no cached results exist (#1458) -->
    <div v-if="!analyzing && !scanRunner.running.value && !hasAnyResults" class="empty-state-container">
      <EmptyState
        icon="fas fa-database"
        :title="$t('analytics.codebase.empty.title')"
        :message="$t('analytics.codebase.empty.description')"
      >
        <template #actions>
          <button @click="indexCodebase" class="btn-primary btn-lg">
            <i class="fas fa-database"></i>
            {{ $t('analytics.codebase.buttons.indexNow') }}
          </button>
        </template>
      </EmptyState>
    </div>

    <!-- Enhanced Analytics Dashboard Cards (#1469) -->
    <CodebaseOverviewPanel
      :system-overview="systemOverview"
      :communication-patterns="communicationPatterns"
      :code-quality="codeQuality"
      :performance-metrics="performanceMetrics"
      @load-system-overview="loadSystemOverview"
      @load-communication-patterns="loadCommunicationPatterns"
      @load-code-quality="loadCodeQuality"
      @load-performance-metrics="loadPerformanceMetrics"
    />

    <!-- Traditional Analytics Section -->
    <div class="analytics-section">
      <!-- Real-time Toggle -->
      <div class="real-time-controls">
        <label class="toggle-switch">
          <input type="checkbox" v-model="realTimeEnabled" @change="toggleRealTime">
          <span class="toggle-slider"></span>
          {{ $t('analytics.codebase.actions.realTimeUpdates') }}
        </label>
        <button @click="refreshAllMetrics" class="refresh-all-btn">
          <i class="fas fa-sync-alt"></i> {{ $t('analytics.codebase.actions.refreshAll') }}
        </button>
      </div>

      <!-- Issue #1469: Stats + Charts section (extracted) -->
      <CodebaseChartsSection
        :codebase-stats="codebaseStats"
        :chart-data="chartData"
        :chart-data-loading="chartDataLoading"
        :chart-data-error="chartDataError"
        :unified-report-loading="unifiedReportLoading"
        :unified-report-error="unifiedReportError"
        :selected-category="selectedCategory"
        :available-categories="availableCategories"
        :analyzing="analyzing"
        @export-section="(section, fmt) => exportSection(section as SectionType, fmt)"
        @load-unified-report="loadUnifiedReport"
        @load-chart-data="loadChartData"
        @update:selected-category="selectedCategory = $event"
        @index-codebase="indexCodebase"
      />

      <!-- Dependency Analysis, Import Tree, Function Call Graph (#1469) -->
      <CodebaseDependenciesPanel
        :dependency-data="dependencyData"
        :dependency-loading="dependencyLoading"
        :dependency-error="dependencyError"
        :import-tree-data="importTreeData ?? []"
        :import-tree-loading="importTreeLoading"
        :import-tree-error="importTreeError"
        :call-graph-data="callGraphData"
        :call-graph-summary="callGraphSummary"
        :call-graph-orphaned="callGraphOrphaned"
        :call-graph-loading="callGraphLoading"
        :call-graph-error="callGraphError"
        @load-dependency-data="loadDependencyData"
        @load-import-tree="loadImportTreeData"
        @load-call-graph="loadCallGraphData"
        @file-navigate="handleFileNavigate"
        @function-select="handleFunctionSelect"
      />

      <!-- Issue #1469: Problems Report (extracted) -->
      <CodebaseProblemsPanel
        :problems-report="problemsReport"
        @export="(fmt) => exportSection('problems', fmt)"
      />

      <!-- Code Intelligence: Anti-Pattern / Code Smells Report (#1469, #184) -->
      <CodeSmellsSection
        :smells="codeSmellsForPanel"
        :code-health-score="codeHealthScore"
        @export="(fmt) => exportSection('code-smells', fmt)"
      />

      <!-- Code Intelligence Analysis (#1469, #566) -->
      <CodebaseSecurityPanel
        :security-findings="codeIntelSecurityFindings"
        :performance-findings="codeIntelPerformanceFindings"
        :redis-findings="codeIntelRedisFindings"
        :findings-loading="codeIntelFindingsLoading"
        :analysis-loading="codeIntelLoading"
        :total-findings="codeIntelTotalFindings"
        @run-analysis="runCodeIntelligenceAnalysis"
        @scan-file="handleFileScan"
      />

      <!-- Duplicate Code Analysis (#1469, #184) -->
      <DuplicatesSection
        :duplicates="duplicateAnalysis"
        @export="(fmt) => exportSection('duplicates', fmt)"
      />

      <!-- Function Declarations (#1469, #184) -->
      <DeclarationsSection
        :declarations="declarationsForPanel"
        @export="(fmt) => exportSection('declarations', fmt)"
      />

      <!-- Issue #527: API Endpoint Checker Section (#1469: extracted to CodebaseApiEndpointsPanel) -->
      <CodebaseApiEndpointsPanel
        :analysis="apiEndpointAnalysis"
        :loading="loadingApiEndpoints"
        :error="apiEndpointsError"
        @refresh="getApiEndpointCoverage"
        @export="(fmt) => exportSection('api-endpoints', fmt)"
      />

            <!-- Issue #244: Cross-Language Pattern Analysis Section (#1469: extracted to CodebaseCrossLanguagePanel) -->
      <CodebaseCrossLanguagePanel
        :analysis="crossLanguageAnalysis"
        :loading="loadingCrossLanguage"
        :error="crossLanguageError"
        @refresh="getCrossLanguageAnalysis"
        @run-full-scan="runCrossLanguageAnalysis"
        @export="(fmt) => exportSection('cross-language', fmt)"
      />

            <!-- Issue #208: Code Pattern Analysis Section -->
      <PatternAnalysis
        ref="patternAnalysisRef"
        :root-path="rootPath"
        :auto-load="true"
        @analysis-complete="onPatternAnalysisComplete"
        @error="onPatternAnalysisError"
      />

      <!-- Issue #538: Config Duplicates Detection Section (#1469: extracted to CodebaseConfigDuplicatesPanel) -->
      <CodebaseConfigDuplicatesPanel
        :analysis="configDuplicatesAnalysis"
        :loading="loadingConfigDuplicates"
        :error="configDuplicatesError"
        @refresh="loadConfigDuplicates"
        @export="(fmt) => exportSection('config-duplicates', fmt)"
      />

            <!-- Issue #538: Bug Prediction Section (#1469: extracted to CodebaseBugPredictionPanel) -->
      <CodebaseBugPredictionPanel
        :analysis="bugPredictionAnalysis"
        :loading="loadingBugPrediction"
        :error="bugPredictionError"
        :was-interrupted="bugPredictionTask.wasInterrupted.value"
        :task-current-step="bugPredictionTask.taskStatus.value?.current_step"
        :task-progress="bugPredictionTask.taskStatus.value?.progress"
        @refresh="loadBugPrediction"
        @export="(fmt) => exportSection('bug-prediction', fmt)"
      />

            <!-- Issue #538: Code Intelligence Scores Section (#1469: extracted to CodebaseIntelligenceScoresPanel) -->
      <CodebaseIntelligenceScoresPanel
        :root-path="rootPath"
        :security-score="securityScore"
        :security-loading="loadingSecurityScore"
        :security-error="securityScoreError"
        :security-findings="securityFindings"
        :security-findings-loading="loadingSecurityFindings"
        :performance-score="performanceScore"
        :performance-loading="loadingPerformanceScore"
        :performance-error="performanceScoreError"
        :performance-findings="performanceFindings"
        :performance-findings-loading="loadingPerformanceFindings"
        :redis-health="redisHealth"
        :redis-loading="loadingRedisHealth"
        :redis-error="redisHealthError"
        :redis-optimizations="redisOptimizations"
        :redis-optimizations-loading="loadingRedisOptimizations"
        @refresh-all="() => { loadSecurityScore(); loadPerformanceScore(); loadRedisHealth() }"
        @refresh-security="loadSecurityScore"
        @refresh-performance="loadPerformanceScore"
        @refresh-redis="loadRedisHealth"
        @load-security-findings="loadSecurityFindings"
        @load-performance-findings="loadPerformanceFindings"
        @load-redis-optimizations="loadRedisOptimizations"
      />

            <!-- Issue #538: Environment Analysis Section (#1469: extracted to CodebaseEnvironmentPanel) -->
      <CodebaseEnvironmentPanel
        :analysis="environmentAnalysis"
        :loading="loadingEnvAnalysis"
        :error="envAnalysisError"
        :use-ai-filtering="useAiFiltering"
        :ai-filtering-model="aiFilteringModel"
        :ai-filtering-priority="aiFilteringPriority"
        :llm-filtering-result="llmFilteringResult"
        @refresh="loadEnvironmentAnalysis"
        @export="(fmt) => exportSection('environment', fmt)"
        @update:use-ai-filtering="useAiFiltering = $event"
        @update:ai-filtering-priority="aiFilteringPriority = $event"
      />

            <!-- Issue #248: Code Ownership and Expertise Map Section (#1469: extracted to CodebaseOwnershipPanel) -->
      <CodebaseOwnershipPanel
        :analysis="ownershipAnalysis"
        :loading="loadingOwnership"
        :error="ownershipError"
        @refresh="loadOwnershipAnalysis"
        @export="(fmt) => exportSection('ownership', fmt)"
      />
    </div>

    <!-- Issue #1133: Knowledge Base Opt-in Banner -->
    <div v-if="showKnowledgeBaseOptIn" class="kb-optin-banner">
      <div class="kb-optin-content">
        <i class="fas fa-book"></i>
        <div class="kb-optin-text">
          <strong>{{ $t('analytics.codebase.knowledgeBase.indexingComplete') }}</strong>
          {{ $t('analytics.codebase.knowledgeBase.addDescription') }}
        </div>
        <button
          class="kb-optin-btn"
          @click="addToKnowledgeBase"
          :disabled="knowledgeBaseAdding"
        >
          <i :class="knowledgeBaseAdding ? 'fas fa-spinner fa-spin' : 'fas fa-plus'"></i>
          {{ knowledgeBaseAdding ? $t('analytics.codebase.knowledgeBase.adding') : $t('analytics.codebase.knowledgeBase.addToKnowledgeBase') }}
        </button>
        <button class="kb-optin-dismiss" @click="showKnowledgeBaseOptIn = false" :aria-label="$t('analytics.codebase.actions.dismiss')">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>

    <!-- Issue #1133: Source Manager Panel -->
    <SourceManager
      v-if="showSourceManager"
      :selected-source-id="selectedSource?.id ?? null"
      :visible="showSourceManager"
      @select-source="handleSelectSource"
      @open-add-source="showAddSourceModal = true; showSourceManager = false"
      @edit-source="handleEditSource"
      @share-source="handleShareSource"
      @close="showSourceManager = false"
    />

    <!-- Issue #1133: Add / Edit Source Modal -->
    <AddSourceModal
      v-if="showAddSourceModal"
      :visible="showAddSourceModal"
      :source="editTargetSource"
      @saved="handleSourceSaved"
      @close="showAddSourceModal = false; editTargetSource = null"
    />

    <!-- Issue #1133: Share Source Modal -->
    <ShareSourceModal
      v-if="showShareSourceModal"
      :visible="showShareSourceModal"
      :source="shareTargetSource"
      @saved="handleShareSaved"
      @close="showShareSourceModal = false; shareTargetSource = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import EmptyState from '@/components/ui/EmptyState.vue'
import PatternAnalysis from '@/components/analytics/PatternAnalysis.vue'
import { useToast } from '@/composables/useToast'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
import { useAnalyticsScanRunner } from '@/composables/useAnalyticsScanRunner'
import { useCodebaseExport, type SectionType } from '@/composables/analytics/useCodebaseExport'
import { useCodebaseState } from '@/composables/analytics/useCodebaseState'
import { useCodebaseIndexing } from '@/composables/analytics/useCodebaseIndexing'
import { useCodebaseSourceRegistry } from '@/composables/analytics/useCodebaseSourceRegistry'
import {
  useCallGraphLoader,
  useChartDataLoader,
  useUnifiedReportLoader,
  useEnvironmentLoader,
  useRedisHealthLoader,
  useCrossLanguageLoader,
  useCachedLoaders,
} from '@/composables/analytics/useCodebaseDataLoaders'
import { createLogger } from '@/utils/debugUtils'
import type {
  CodeSource,
  DependencyGraph,
  ImportTreeNode,
  DuplicateCode,
  BugPredictionFile,
  BugPredictionResult,
  SecurityScoreResult,
  PerformanceScoreResult,
  ConfigDuplicatesResult,
  ApiEndpointAnalysisResult,
  SecurityFindingDetail,
  PerformanceFindingDetail,
  RedisOptimization,
  OwnershipAnalysisResult,
  OwnershipSummary,
  FileOwnership,
  DirectoryOwnership,
  ExpertiseScore,
  KnowledgeGap,
  OwnershipMetrics,
  CrossLanguageAnalysisResult,
} from '@/types/codebaseAnalytics'
// Issue #1133: Code Source Registry Components
import CodebaseOverviewPanel from '@/components/analytics/CodebaseOverviewPanel.vue'
import CodebaseDependenciesPanel from '@/components/analytics/CodebaseDependenciesPanel.vue'
import CodebaseSecurityPanel from '@/components/analytics/CodebaseSecurityPanel.vue'
import CodeSmellsSection from '@/components/analytics/CodeSmellsSection.vue'
import DuplicatesSection from '@/components/analytics/DuplicatesSection.vue'
import DeclarationsSection from '@/components/analytics/DeclarationsSection.vue'
import SourceManager from '@/components/analytics/SourceManager.vue'
import AddSourceModal from '@/components/analytics/AddSourceModal.vue'
import ShareSourceModal from '@/components/analytics/ShareSourceModal.vue'
// Issue #1469: Extracted panel sub-components
import CodebaseAnalyticsHeader from '@/components/analytics/panels/CodebaseAnalyticsHeader.vue'
import CodebaseProgressPanel from '@/components/analytics/panels/CodebaseProgressPanel.vue'
import CodebaseChartsSection from '@/components/analytics/panels/CodebaseChartsSection.vue'
import CodebaseProblemsPanel from '@/components/analytics/panels/CodebaseProblemsPanel.vue'
import CodebaseApiEndpointsPanel from '@/components/analytics/panels/CodebaseApiEndpointsPanel.vue'
import CodebaseCrossLanguagePanel from '@/components/analytics/panels/CodebaseCrossLanguagePanel.vue'
import CodebaseConfigDuplicatesPanel from '@/components/analytics/panels/CodebaseConfigDuplicatesPanel.vue'
import CodebaseBugPredictionPanel from '@/components/analytics/panels/CodebaseBugPredictionPanel.vue'
import CodebaseIntelligenceScoresPanel from '@/components/analytics/panels/CodebaseIntelligenceScoresPanel.vue'
import CodebaseEnvironmentPanel from '@/components/analytics/panels/CodebaseEnvironmentPanel.vue'
import CodebaseOwnershipPanel from '@/components/analytics/panels/CodebaseOwnershipPanel.vue'
import type {
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
} from '@/types/codeIntelligence'

const logger = createLogger('CodebaseAnalytics')

// i18n
const { t } = useI18n()
const route = useRoute()
const analyticsRouter = useRouter()

// Toast notifications
const { showToast } = useToast()
const notify = (
  message: string,
  type: 'info' | 'success' | 'warning' | 'error' = 'info',
) => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// --- Composable: Shared Reactive State (#2228/#2230) ----------------
const {
  STORAGE_KEY_PATH,
  rootPath,
  sources,
  selectedSource,
  showSourceManager,
  showAddSourceModal,
  showShareSourceModal,
  editTargetSource,
  shareTargetSource,
  showKnowledgeBaseOptIn,
  knowledgeBaseAdding,
  sourceIdParam,
  withSourceId,
  sourceIdQuery,
  analyzing,
  progressPercent,
  progressStatus,
  realTimeEnabled,
  refreshInterval,
  currentJobId,
  currentJobStatus,
  jobPollingInterval,
  jobPhases,
  jobBatches,
  jobStats,
  codebaseStats,
  problemsReport,
  duplicateAnalysis,
  declarationAnalysis,
  hardcodeAnalysis,
  refactoringSuggestions,
  codeSmellsReport,
  codeHealthScore,
  analyzingCodeSmells,
  codeSmellsAnalysisType,
  exportingReport,
  clearingCache,
  systemOverview,
  communicationPatterns,
  codeQuality,
  performanceMetrics,
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
  crossLanguageAnalysis,
  loadingCrossLanguage,
  crossLanguageError,
  expandedCrossLanguageGroups,
  environmentAnalysis,
  loadingEnvAnalysis,
  envAnalysisError,
  useAiFiltering,
  aiFilteringModel,
  aiFilteringPriority,
  llmFilteringResult,
  redisHealth,
  loadingRedisHealth,
  redisHealthError,
  loadingProgress,
  showAllProblems,
  showAllDeclarations,
  showAllDuplicates,
  expandedApiEndpointGroups,
  patternAnalysisRef,
  codeIntelFindingsLoading,
  codeIntelFindingsFetched,
  showSecurityDetails,
  showPerformanceDetails,
  showRedisDetails,
  bugRiskFilter,
  BUG_RISK_PAGE_SIZE,
  bugRiskVisibleCount,
  expandedBugRiskFiles,
  ownershipViewMode,
} = useCodebaseState()

// --- Code Intelligence (#566) ---------------------------------------
const {
  isLoading: codeIntelLoading,
  suggestions: codeIntelSuggestions,
  analyzeCode: codeIntelAnalyzeCode,
  getSuggestions: codeIntelGetSuggestions,
  batchAnalyze: codeIntelBatchAnalyze,
} = useCodeIntelligence()

const codeIntelSecurityFindings = ref<SecurityFinding[]>([])
const codeIntelPerformanceFindings = ref<PerformanceFinding[]>([])
const codeIntelRedisFindings = ref<RedisOptimizationFinding[]>([])

const codeIntelTotalFindings = computed(() =>
  codeIntelSuggestions.value.length,
)

async function runCodeIntelligenceAnalysis() {
  if (!rootPath.value) return
  logger.info('Running Code Intelligence analysis on:', rootPath.value)
  codeIntelFindingsFetched.value = { security: false, performance: false, redis: false }
  codeIntelFindingsLoading.value = true
  try {
    await codeIntelAnalyzeCode({ code: rootPath.value })
    await codeIntelGetSuggestions(rootPath.value)
    codeIntelFindingsFetched.value = { security: true, performance: true, redis: true }
    notify(
      t('analytics.codebase.notify.codeIntelComplete', { count: codeIntelTotalFindings.value }),
      'success',
    )
  } catch (e) {
    logger.error('Code Intelligence analysis failed:', e)
    notify(t('analytics.codebase.notify.codeIntelFailed'), 'error')
  } finally {
    codeIntelFindingsLoading.value = false
  }
}

async function handleFileScan(
  filePath: string,
  _types: { security: boolean; performance: boolean; redis: boolean },
) {
  codeIntelFindingsLoading.value = true
  try {
    const results = await codeIntelBatchAnalyze([{ code: filePath, filename: filePath }])
    if (results.length > 0) {
      codeIntelFindingsFetched.value = { security: true, performance: true, redis: true }
      notify(t('analytics.codebase.notify.fileScanComplete', { count: results.length }), 'info')
    } else {
      notify(t('analytics.codebase.notify.fileScanNoIssues'), 'success')
    }
  } catch (e) {
    logger.error('File scan failed:', e)
    notify(t('analytics.codebase.notify.fileScanFailed'), 'error')
  } finally {
    codeIntelFindingsLoading.value = false
  }
}

// --- Task Loaders / Background Tasks (#1304/#1321) ------------------
const {
  data: dependencyData,
  loading: dependencyLoading,
  error: dependencyError,
  load: _loadDependencyTask,
} = useTaskLoader<DependencyGraph>(
  '/api/analytics/codebase/analytics/dependencies',
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
  '/api/analytics/codebase/analytics/import-tree',
  (r) => {
    if (r.status === 'success' && r.import_tree) {
      return r.import_tree as unknown as ImportTreeNode[]
    }
    return r.status === 'no_data' ? ([] as ImportTreeNode[]) : undefined
  },
)

const dupTask = useBackgroundTask('/api/analytics/codebase/duplicates')

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
        severity_breakdown: (r.severity_breakdown as Record<string, number>) || {},
        owasp_breakdown: (r.owasp_breakdown as Record<string, number>) || {},
      }
    }
    return undefined
  },
)

const dashboardTask = useBackgroundTask('/api/analytics/dashboard/overview')
const scanRunner = useAnalyticsScanRunner()

const bugPredictionTask = useBackgroundTask('/api/analytics/bug-prediction')
const bugPredictionAnalysis = computed<BugPredictionResult | null>(() => {
  const r = bugPredictionTask.result.value
  if (!r || r.status === 'no_data') return null
  return {
    timestamp: (r.timestamp as string) || new Date().toISOString(),
    total_files: (r.total_files as number) || 0,
    analyzed_files: (r.analyzed_files as number) || 0,
    high_risk_count: (r.high_risk_count as number) || 0,
    files: (r.files as BugPredictionFile[]) || [],
  }
})
const loadingBugPrediction = bugPredictionTask.running
const bugPredictionError = bugPredictionTask.error

// #1321: API endpoints (useAnalyticsFetch)
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

// #1321: Config duplicates (useAnalyticsFetch)
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
        duplicates: (r.duplicates as ConfigDuplicatesResult['duplicates']) || [],
        report: (r.report as string) || '',
      }
    }
    return undefined
  },
)

// #1321: Performance score (useAnalyticsFetch)
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
        severity_breakdown: (r.severity_breakdown as Record<string, number>) || {},
        issue_type_breakdown: (r.issue_type_breakdown as Record<string, number>) || {},
      }
    }
    return undefined
  },
)

// #1321: Detailed findings (useAnalyticsFetch POST)
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

// #1321: Ownership (useAnalyticsFetch)
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
        analysis_time_seconds: (r.analysis_time_seconds as number) || 0,
        summary: (r.summary as OwnershipSummary) || {
          total_files: 0, total_directories: 0, total_contributors: 0,
          knowledge_gaps_count: 0, critical_gaps: 0, high_risk_gaps: 0,
        },
        file_ownership: (r.file_ownership as FileOwnership[]) || [],
        directory_ownership: (r.directory_ownership as DirectoryOwnership[]) || [],
        expertise_scores: (r.expertise_scores as ExpertiseScore[]) || [],
        knowledge_gaps: (r.knowledge_gaps as KnowledgeGap[]) || [],
        metrics: (r.metrics as OwnershipMetrics) || {
          total_lines_analyzed: 0, total_files_analyzed: 0,
          overall_bus_factor: 1, bus_factor_distribution: {},
          knowledge_risk_distribution: {}, top_contributors: [],
          ownership_concentration: 0, team_coverage: 0,
        },
      }
    }
    return undefined
  },
)

// --- Composable: Data Loaders (#2228/#2230) -------------------------
const dataLoaderOpts = { rootPath, withSourceId, sourceIdQuery }
const { loadCallGraphData: _loadCallGraph } = useCallGraphLoader(dataLoaderOpts)
const { loadChartData: _loadChart } = useChartDataLoader(dataLoaderOpts)
const { loadUnifiedReport: _loadUnified } = useUnifiedReportLoader()
const { loadEnvironmentAnalysis: _loadEnv } = useEnvironmentLoader(dataLoaderOpts)
const { loadRedisHealth: _loadRedis } = useRedisHealthLoader(dataLoaderOpts)
const { mapCrossLanguageSummary, loadCrossLanguageDetails: _loadCrossLangDetails } =
  useCrossLanguageLoader(dataLoaderOpts)
const {
  loadCachedDuplicates: _cachedDups,
  loadCachedDependencies: _cachedDeps,
  loadCachedImportTree: _cachedImports,
  loadCachedBugPrediction: _cachedBugPred,
  loadCachedSecurityScore: _cachedSecurity,
} = useCachedLoaders(dataLoaderOpts)

// Thin wrappers that pass local refs to data loader functions
const loadCallGraphData = () =>
  _loadCallGraph(callGraphData, callGraphSummary, callGraphOrphaned, callGraphLoading, callGraphError)
const loadChartData = () =>
  _loadChart(chartData as Ref<unknown>, chartDataLoading, chartDataError)
const loadUnifiedReport = () =>
  _loadUnified(unifiedReport as Ref<unknown>, unifiedReportLoading, unifiedReportError)
const loadEnvironmentAnalysis = () =>
  _loadEnv(
    environmentAnalysis, loadingEnvAnalysis, envAnalysisError,
    useAiFiltering, aiFilteringModel, aiFilteringPriority, llmFilteringResult as Ref<unknown>,
  )
const loadRedisHealth = () =>
  _loadRedis(redisHealth, loadingRedisHealth, redisHealthError)
const loadCachedDuplicates = () => _cachedDups(duplicateAnalysis as Ref<unknown[]>)
const loadCachedDependencies = () => _cachedDeps(dependencyData as Ref<unknown>)
const loadCachedImportTree = () => _cachedImports(importTreeData as Ref<unknown>)
const loadCachedBugPrediction = async () => {
  const bp = ref<Record<string, unknown> | null>(null)
  await _cachedBugPred(bp)
  if (bp.value) bugPredictionTask.result.value = bp.value
}
const loadCachedSecurityScore = () => _cachedSecurity(securityScore as Ref<unknown>)

// --- Composable: Source Registry (#2228/#2230) ----------------------
const {
  loadSources,
  handleSelectSource,
  handleClearSource,
  handleSourceSaved,
  handleShareSaved,
  handleEditSource,
  handleShareSource,
  addToKnowledgeBase,
} = useCodebaseSourceRegistry({
  rootPath, sources, selectedSource, showSourceManager,
  showAddSourceModal, showShareSourceModal, editTargetSource,
  shareTargetSource, showKnowledgeBaseOptIn, knowledgeBaseAdding,
  notify, t,
})

// --- Composable: Indexing (#2228/#2230) -----------------------------
const {
  checkCurrentIndexingJob,
  indexCodebase,
  cancelIndexingJob,
  handleStop: _handleStopIndexing,
  stopJobPolling,
} = useCodebaseIndexing({
  rootPath, selectedSource, withSourceId, analyzing, progressPercent,
  progressStatus, currentJobId, currentJobStatus, jobPollingInterval,
  jobPhases, jobBatches, jobStats, problemsReport, codebaseStats,
  showKnowledgeBaseOptIn, notify, t,
  onIndexingComplete: () => runAllAnalysisScans(),
})

const handleStop = () =>
  _handleStopIndexing(scanRunner.cancel, scanRunner.running)

// --- Computed Properties --------------------------------------------
const hasAnyResults = computed(() =>
  !!(
    codebaseStats.value ||
    problemsReport.value.length > 0 ||
    declarationAnalysis.value.length > 0 ||
    duplicateAnalysis.value.length > 0
  ),
)

const codeSmellsProgressTitle = computed(() =>
  codeSmellsAnalysisType.value === 'health'
    ? t('analytics.codebase.progress.calculatingHealth')
    : t('analytics.codebase.progress.analyzingSmells'),
)

const availableCategories = computed(() => {
  if (!unifiedReport.value?.categories) return []
  const categories = unifiedReport.value.categories
  return Object.keys(categories).map((key) => ({
    id: key,
    name: key.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    count: Array.isArray(categories[key]) ? categories[key].length : 0,
  }))
})

// Issue #609: Code smell types for filtering
const CODE_SMELL_TYPES = new Set([
  'long_function', 'debug_code', 'race_condition',
  'technical_debt_bug', 'technical_debt_todo', 'technical_debt_fixme', 'technical_debt_deprecated',
  'performance_nested_loop_complexity', 'performance_quadratic_complexity',
  'performance_n_plus_one_query', 'performance_blocking_io_in_async',
  'performance_excessive_string_concat', 'performance_list_for_lookup',
  'performance_repeated_computation', 'performance_repeated_file_open',
  'performance_sequential_awaits', 'performance_unbatched_api_calls',
])

const codeSmellsFromProblems = computed(() => {
  if (!problemsReport.value || problemsReport.value.length === 0) return []
  return problemsReport.value.filter((p) => p.type && CODE_SMELL_TYPES.has(p.type))
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

// --- Data Loaders (thin wrappers) -----------------------------------
const loadDependencyData = () => _loadDependencyTask()
const loadImportTreeData = () => _loadImportTreeTask()
const loadConfigDuplicates = () => _loadConfigDuplicates(sourceIdQuery.value)
const loadBugPrediction = () => bugPredictionTask.start()
const loadApiEndpointAnalysis = () => _loadApiEndpoints(sourceIdQuery.value)

const loadSecurityScore = async () => {
  if (!rootPath.value) return
  await _loadSecurityScoreTask(undefined, { path: rootPath.value })
}
const loadPerformanceScore = async () => {
  if (!rootPath.value) return
  await _loadPerformanceScore({ path: rootPath.value })
}
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
const loadOwnershipAnalysis = async () => {
  if (!rootPath.value) return
  await _loadOwnership({ path: rootPath.value, ...sourceIdQuery.value })
}

// --- Silent Data Loaders --------------------------------------------
const getCodebaseStats = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/stats`)
    if (!response.ok) throw new Error(`Stats endpoint returned ${response.status}`)
    const data = await response.json()
    if (data.status === 'success' && data.stats) {
      codebaseStats.value = data.stats
    } else if (data.status === 'no_data' || data.status === 'indexing') {
      codebaseStats.value = null
    }
  } catch (error: unknown) {
    logger.error('Failed to get stats:', error)
  }
}

const getProblemsReport = async () => {
  loadingProgress.problems = true
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/problems`)
    if (!response.ok) throw new Error(`Problems endpoint returned ${response.status}`)
    const data = await response.json()
    problemsReport.value = data.status === 'no_data' ? [] : (data.problems || [])
  } catch (error: unknown) {
    logger.error('Failed to get problems:', error)
  } finally {
    loadingProgress.problems = false
  }
}

const loadDeclarations = async () => {
  loadingProgress.declarations = true
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(
      withSourceId(`${backendUrl}/api/analytics/codebase/declarations`),
    )
    if (!response.ok) throw new Error(`Declarations endpoint returned ${response.status}`)
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

const loadHardcodes = async () => {
  loadingProgress.hardcodes = true
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(
      withSourceId(`${backendUrl}/api/analytics/codebase/hardcodes`),
    )
    if (!response.ok) throw new Error(`Hardcodes endpoint returned ${response.status}`)
    const data = await response.json()
    hardcodeAnalysis.value = data.hardcodes || []
  } catch (error: unknown) {
    logger.error('Failed to load hardcodes:', error)
  } finally {
    loadingProgress.hardcodes = false
  }
}

// --- Cross-Language Analysis ----------------------------------------
const getCrossLanguageAnalysis = async () => {
  loadingCrossLanguage.value = true
  crossLanguageError.value = ''
  const startTime = Date.now()
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(
      withSourceId(`${backendUrl}/api/analytics/codebase/cross-language/summary`),
    )
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    if (data.status === 'success' && data.summary) {
      crossLanguageAnalysis.value = mapCrossLanguageSummary(
        data.summary,
      ) as CrossLanguageAnalysisResult
      const issues = data.summary.issues as Record<string, number> | undefined
      notify(
        t('analytics.codebase.notify.crossLanguageResult', {
          total: issues?.total || 0, critical: issues?.critical || 0,
          high: issues?.high || 0, time: responseTime,
        }),
        'success',
      )
      await _loadCrossLangDetails(crossLanguageAnalysis as Ref<Record<string, unknown> | null>)
    } else if (data.status === 'empty') {
      crossLanguageAnalysis.value = null
    } else {
      throw new Error('Invalid response format')
    }
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Cross-language analysis failed:', error)
    crossLanguageError.value = errorMessage
    notify(
      t('analytics.codebase.notify.crossLanguageFailed', { error: errorMessage, time: responseTime }),
      'error',
    )
  } finally {
    loadingCrossLanguage.value = false
    if (!analyzing.value) progressStatus.value = t('analytics.codebase.status.ready')
  }
}

const runCrossLanguageAnalysis = async () => {
  loadingCrossLanguage.value = true
  crossLanguageError.value = ''
  progressStatus.value = t('analytics.codebase.status.runningFullCrossLanguage')
  const startTime = Date.now()
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(
      withSourceId(`${backendUrl}/api/analytics/codebase/cross-language/analyze`),
      {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_llm: true, use_cache: true }),
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
        t('analytics.codebase.notify.crossLanguageScanComplete', { time: responseTime }),
        'success',
      )
      await getCrossLanguageAnalysis()
    } else {
      throw new Error(data.message || 'Analysis failed')
    }
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Cross-language analysis scan failed:', error)
    crossLanguageError.value = errorMessage
    notify(
      t('analytics.codebase.notify.crossLanguageScanFailed', { error: errorMessage, time: responseTime }),
      'error',
    )
  } finally {
    loadingCrossLanguage.value = false
    if (!analyzing.value) progressStatus.value = t('analytics.codebase.status.ready')
  }
}

// --- Scan Orchestration ---------------------------------------------
const loadCachedAnalyticsData = async () => {
  try {
    await scanRunner.runAll([
      { id: 'stats', label: t('analytics.codebase.scans.stats'), run: () => getCodebaseStats() },
      { id: 'problems', label: t('analytics.codebase.scans.problems'), run: () => getProblemsReport() },
      { id: 'declarations', label: t('analytics.codebase.scans.declarations'), run: () => loadDeclarations() },
      { id: 'duplicates', label: t('analytics.codebase.scans.duplicates'), run: () => loadCachedDuplicates() },
      { id: 'hardcodes', label: t('analytics.codebase.scans.hardcodes'), run: () => loadHardcodes() },
      { id: 'charts', label: t('analytics.codebase.scans.charts'), run: () => loadChartData() },
      { id: 'dependencies', label: t('analytics.codebase.scans.dependencies'), run: () => loadCachedDependencies() },
      { id: 'imports', label: t('analytics.codebase.scans.imports'), run: () => loadCachedImportTree() },
      { id: 'callgraph', label: t('analytics.codebase.scans.callGraph'), run: () => loadCallGraphData() },
      { id: 'configDuplicates', label: t('analytics.codebase.scans.configDuplicates'), run: () => loadConfigDuplicates() },
      { id: 'apiEndpoints', label: t('analytics.codebase.scans.apiEndpoints'), run: () => loadApiEndpointAnalysis() },
      { id: 'bugPrediction', label: t('analytics.codebase.scans.bugPrediction'), run: () => loadCachedBugPrediction() },
      { id: 'security', label: t('analytics.codebase.scans.security'), run: () => loadCachedSecurityScore() },
      { id: 'crossLanguage', label: t('analytics.codebase.scans.crossLanguage'), run: () => getCrossLanguageAnalysis() },
    ])
    progressStatus.value = scanRunner.failedCount.value > 0
      ? t('analytics.codebase.status.loadPartialFailed', { failed: scanRunner.failedCount.value, total: scanRunner.totalCount.value })
      : t('analytics.codebase.status.loadComplete')
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to load cached analytics data:', error)
    progressStatus.value = t('analytics.codebase.status.loadFailed', { error: errorMessage })
  }
}

const runAllAnalysisScans = async () => {
  try {
    await scanRunner.runAll([
      { id: 'stats', label: t('analytics.codebase.scans.stats'), run: () => getCodebaseStats() },
      { id: 'problems', label: t('analytics.codebase.scans.problems'), run: () => getProblemsReport() },
      { id: 'declarations', label: t('analytics.codebase.scans.declarations'), run: () => loadDeclarations() },
      { id: 'duplicates', label: t('analytics.codebase.scans.duplicates'), run: () => loadDuplicates() },
      { id: 'hardcodes', label: t('analytics.codebase.scans.hardcodes'), run: () => loadHardcodes() },
      { id: 'charts', label: t('analytics.codebase.scans.charts'), run: () => loadChartData() },
      { id: 'dependencies', label: t('analytics.codebase.scans.dependencies'), run: () => loadDependencyData() },
      { id: 'imports', label: t('analytics.codebase.scans.imports'), run: () => loadImportTreeData() },
      { id: 'callgraph', label: t('analytics.codebase.scans.callGraph'), run: () => loadCallGraphData() },
      { id: 'configDuplicates', label: t('analytics.codebase.scans.configDuplicates'), run: () => loadConfigDuplicates() },
      { id: 'apiEndpoints', label: t('analytics.codebase.scans.apiEndpoints'), run: () => loadApiEndpointAnalysis() },
      { id: 'bugPrediction', label: t('analytics.codebase.scans.bugPrediction'), run: () => loadBugPrediction() },
      { id: 'security', label: t('analytics.codebase.scans.security'), run: () => loadSecurityScore() },
      { id: 'performance', label: t('analytics.codebase.scans.performance'), run: () => loadPerformanceScore() },
      { id: 'redis', label: t('analytics.codebase.scans.redis'), run: () => loadRedisHealth() },
      { id: 'environment', label: t('analytics.codebase.scans.environment'), run: () => loadEnvironmentAnalysis() },
      { id: 'ownership', label: t('analytics.codebase.scans.ownership'), run: () => loadOwnershipAnalysis() },
      { id: 'crossLanguage', label: t('analytics.codebase.scans.crossLanguage'), run: () => getCrossLanguageAnalysis() },
    ])
    progressStatus.value = scanRunner.failedCount.value > 0
      ? t('analytics.codebase.status.loadPartialFailed', { failed: scanRunner.failedCount.value, total: scanRunner.totalCount.value })
      : t('analytics.codebase.status.loadComplete')
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to load codebase analytics data:', error)
    progressStatus.value = t('analytics.codebase.status.loadFailed', { error: errorMessage })
  }
}

// --- Debug / Test Functions -----------------------------------------
const getDeclarationsData = async () => {
  const startTime = Date.now()
  loadingProgress.declarations = true
  progressStatus.value = t('analytics.codebase.status.processingDeclarations')
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(withSourceId(`${backendUrl}/api/analytics/codebase/declarations`))
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    declarationAnalysis.value = data.declarations || []
    notify(t('analytics.codebase.notify.declarationsFound', { count: declarationAnalysis.value.length, time: responseTime }), 'success')
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Declarations failed:', error)
    notify(t('analytics.codebase.notify.declarationsFailed', { error: errorMessage, time: responseTime }), 'error')
  } finally {
    loadingProgress.declarations = false
    progressStatus.value = t('analytics.codebase.status.ready')
  }
}

const getDuplicatesData = async () => {
  loadingProgress.duplicates = true
  progressStatus.value = t('analytics.codebase.status.findingDuplicates')
  const startTime = Date.now()
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(withSourceId(`${backendUrl}/api/analytics/codebase/duplicates`))
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    duplicateAnalysis.value = data.duplicates || []
    notify(t('analytics.codebase.notify.duplicatesFound', { count: duplicateAnalysis.value.length, time: responseTime }), 'success')
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Duplicates failed:', error)
    notify(t('analytics.codebase.notify.duplicatesFailed', { error: errorMessage, time: responseTime }), 'error')
  } finally {
    loadingProgress.duplicates = false
    progressStatus.value = t('analytics.codebase.status.ready')
  }
}

const getHardcodesData = async () => {
  loadingProgress.hardcodes = true
  progressStatus.value = t('analytics.codebase.status.detectingHardcodes')
  const startTime = Date.now()
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(withSourceId(`${backendUrl}/api/analytics/codebase/hardcodes`))
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    hardcodeAnalysis.value = data.hardcodes || []
    const hardcodeCount = hardcodeAnalysis.value.length
    const hardcodeTypes = hardcodeCount > 0 ? [...new Set(hardcodeAnalysis.value.map((h) => h.type))].join(', ') : 'none'
    notify(t('analytics.codebase.notify.hardcodesFound', { count: hardcodeCount, types: hardcodeTypes, time: responseTime }), 'success')
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Hardcodes failed:', error)
    notify(t('analytics.codebase.notify.hardcodesFailed', { error: errorMessage, time: responseTime }), 'error')
  } finally {
    loadingProgress.hardcodes = false
    progressStatus.value = t('analytics.codebase.status.ready')
  }
}

const getApiEndpointCoverage = async () => {
  loadingApiEndpoints.value = true
  apiEndpointsError.value = ''
  progressStatus.value = t('analytics.codebase.status.scanningApi')
  const startTime = Date.now()
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(withSourceId(`${backendUrl}/api/analytics/codebase/endpoint-analysis`))
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    if (data.status === 'success' && data.analysis) {
      apiEndpointAnalysis.value = data.analysis
      const coverage = data.analysis.coverage_percentage?.toFixed(1) || 0
      notify(t('analytics.codebase.notify.apiCoverageResult', { coverage, orphaned: data.analysis.orphaned_endpoints || 0, missing: data.analysis.missing_endpoints || 0, time: responseTime }), 'success')
    } else { throw new Error('Invalid response format') }
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('API Endpoint analysis failed:', error)
    apiEndpointsError.value = errorMessage
    notify(t('analytics.codebase.notify.apiAnalysisFailed', { error: errorMessage, time: responseTime }), 'error')
  } finally {
    loadingApiEndpoints.value = false
    progressStatus.value = t('analytics.codebase.status.ready')
  }
}

const testNpuConnection = async () => {
  const startTime = Date.now()
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/npu/status`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    const responseTime = Date.now() - startTime
    const available = data.available || data.status === 'ok' || data.workers_connected > 0
    const workerCount = data.workers_connected ?? data.total_workers ?? 0
    notify(t('analytics.codebase.notify.npuStatus', { status: available ? t('analytics.codebase.available') : t('analytics.codebase.notAvailable'), workers: workerCount, time: responseTime }), available ? 'success' : 'warning')
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('NPU connection failed:', error)
    notify(t('analytics.codebase.notify.npuFailed', { error: errorMessage, time: responseTime }), 'error')
  }
}

const _testEndpointConfigs = [
  { name: 'Declarations', path: '/api/analytics/codebase/declarations' },
  { name: 'Duplicates', path: '/api/analytics/codebase/duplicates' },
  { name: 'Hardcodes', path: '/api/analytics/codebase/hardcodes' },
  { name: 'NPU', path: '/api/npu/status' },
  { name: 'Stats', path: '/api/analytics/codebase/stats' },
]

const testAllEndpoints = async () => {
  progressStatus.value = t('analytics.codebase.status.testingApis')
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const results: string[] = []
    for (const ep of _testEndpointConfigs) {
      try { const response = await fetchWithAuth(`${backendUrl}${ep.path}`); results.push(`${ep.name}: ${response.ok ? 'OK' : 'FAIL'} (${response.status})`) }
      catch (err) { results.push(`${ep.name}: FAIL (${err instanceof Error ? err.message : String(err)})`) }
    }
    const passed = results.filter((r) => r.includes('OK')).length
    notify(t('analytics.codebase.notify.apiTestResults', { passed, total: results.length }), results.some((r) => r.includes('FAIL')) ? 'warning' : 'success')
    logger.debug('API Test Results:', results.join('\n'))
  } catch (error: unknown) {
    logger.error('API tests failed:', error)
    notify(t('analytics.codebase.notify.apiTestsFailed', { error: error instanceof Error ? error.message : String(error) }), 'error')
  } finally { progressStatus.value = t('analytics.codebase.status.ready') }
}

const testDataState = () => {
  const summary = { analyzing: analyzing.value, rootPath: rootPath.value, currentJobId: currentJobId.value, problems: problemsReport.value?.length || 0, declarations: declarationAnalysis.value?.length || 0, duplicates: duplicateAnalysis.value?.length || 0, stats: codebaseStats.value ? 'Available' : 'Not loaded' }
  logger.info('Debug State:', summary)
  notify(t('analytics.codebase.notify.debugState', { analyzing: summary.analyzing, path: summary.rootPath ? 'set' : 'empty', jobId: summary.currentJobId || 'none', problems: summary.problems }), 'info')
}

const resetState = () => {
  analyzing.value = false; currentJobId.value = null; currentJobStatus.value = null
  stopJobPolling(); progressPercent.value = 0
  progressStatus.value = t('analytics.codebase.status.stateReset')
  notify(t('analytics.codebase.notify.stateReset'), 'success')
}

// --- Code Smells / Health Score -------------------------------------
const runCodeSmellAnalysis = async () => {
  const startTime = Date.now()
  codeSmellsAnalysisType.value = 'smells'
  if (rootPath.value.includes('/data/code-sources/')) { notify(t('analytics.codebase.notify.codeIntelLocalPathRequired'), 'warning'); return }
  analyzingCodeSmells.value = true
  progressStatus.value = t('analytics.codebase.status.scanningCodeSmells')
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/code-intelligence/analyze`, { method: 'POST', headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify({ path: rootPath.value, exclude_dirs: ['node_modules', '.venv', '__pycache__', '.git', 'archives'], min_severity: 'low' }) })
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    codeSmellsReport.value = data.report
    const totalIssues = data.report?.anti_patterns?.length || 0
    notify(t('analytics.codebase.notify.codeSmellsFound', { count: totalIssues, files: data.report?.total_files || 0, time: responseTime }), totalIssues > 0 ? 'warning' : 'success')
    progressStatus.value = t('analytics.codebase.status.codeSmellsComplete', { count: totalIssues })
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Code smell analysis failed:', error)
    notify(t('analytics.codebase.notify.codeSmellsFailed', { error: errorMessage, time: Date.now() - startTime }), 'error')
    progressStatus.value = t('analytics.codebase.status.codeSmellsFailed')
  } finally { analyzingCodeSmells.value = false }
}

const getCodeHealthScore = async () => {
  const startTime = Date.now()
  codeSmellsAnalysisType.value = 'health'
  if (rootPath.value.includes('/data/code-sources/')) { notify(t('analytics.codebase.notify.healthScoreLocalPathRequired'), 'warning'); return }
  analyzingCodeSmells.value = true
  progressStatus.value = t('analytics.codebase.status.calculatingHealth')
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(rootPath.value)}`)
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    codeHealthScore.value = data
    notify(t('analytics.codebase.notify.healthScoreResult', { score: data.health_score || 0, grade: data.grade || 'N/A', issues: data.total_issues || 0, time: responseTime }), (data.health_score || 0) >= 70 ? 'success' : 'warning')
    progressStatus.value = t('analytics.codebase.status.healthScoreResult', { score: data.health_score || 0, grade: data.grade || 'N/A' })
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Health score failed:', error)
    notify(t('analytics.codebase.notify.healthScoreFailed', { error: errorMessage, time: Date.now() - startTime }), 'error')
    progressStatus.value = t('analytics.codebase.status.healthScoreFailed')
  } finally { analyzingCodeSmells.value = false }
}

// --- Export (#1588) -------------------------------------------------
const { exportReport, exportSection } = useCodebaseExport({
  sectionData: {
    'bug-prediction': bugPredictionAnalysis as Ref<unknown>,
    'code-smells': codeSmellsReport as Ref<unknown>,
    'problems': problemsReport as Ref<unknown>,
    'duplicates': duplicateAnalysis as Ref<unknown>,
    'declarations': declarationAnalysis as Ref<unknown>,
    'api-endpoints': apiEndpointAnalysis as Ref<unknown>,
    'cross-language': crossLanguageAnalysis as Ref<unknown>,
    'config-duplicates': configDuplicatesAnalysis as Ref<unknown>,
    'code-intelligence': codeHealthScore as Ref<unknown>,
    'environment': environmentAnalysis as Ref<unknown>,
    'statistics': codebaseStats as Ref<unknown>,
    'ownership': ownershipAnalysis as Ref<unknown>,
  },
  exportingReport, progressStatus, fetchWithAuth,
  getBackendUrl: () => appConfig.getServiceUrl('backend'),
  notify, t,
})

// --- Cache / Full Analysis ------------------------------------------
const clearCache = async () => {
  clearingCache.value = true
  progressStatus.value = t('analytics.codebase.status.clearingCache')
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(withSourceId(`${backendUrl}/api/analytics/codebase/cache`), { method: 'DELETE', headers: { 'Content-Type': 'application/json' } })
    if (!response.ok) { const errorText = await response.text(); throw new Error(`Status ${response.status}: ${errorText}`) }
    const result = await response.json()
    codebaseStats.value = null; problemsReport.value = []; declarationAnalysis.value = []; duplicateAnalysis.value = []; hardcodeAnalysis.value = []; chartData.value = null
    notify(t('analytics.codebase.notify.cacheCleared', { count: result.deleted_keys || 0 }), 'success')
    progressStatus.value = t('analytics.codebase.status.cacheCleared')
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Cache clear failed:', error)
    notify(t('analytics.codebase.notify.cacheClearFailed', { error: errorMessage }), 'error')
    progressStatus.value = t('analytics.codebase.status.cacheClearFailed')
  } finally { clearingCache.value = false }
}

const runFullAnalysis = async () => {
  await scanRunner.runAll([
    { id: 'indexing', label: t('analytics.codebase.scans.indexing'), run: () => indexCodebase() },
    { id: 'patterns', label: t('analytics.codebase.scans.patterns'), run: async () => { if (patternAnalysisRef.value?.runAnalysis) { await patternAnalysisRef.value.runAnalysis() } else { throw new Error('Component not ready') } } },
    { id: 'crossLanguage', label: t('analytics.codebase.scans.crossLanguage'), run: () => runCrossLanguageAnalysis() },
  ])
  progressStatus.value = t('analytics.codebase.status.analysisComplete', { succeeded: scanRunner.completedCount.value, total: scanRunner.totalCount.value })
  if (scanRunner.failedCount.value > 0) { logger.warn(`Full analysis partial failure: ${scanRunner.results.value.filter((r) => r.status === 'failed').map((r) => r.label).join(', ')}`) }
}

// --- Enhanced Analytics Dashboard Loaders ---------------------------
const loadSystemOverview = async () => {
  try {
    const ok = await dashboardTask.start()
    if (ok && dashboardTask.result.value) {
      const result = dashboardTask.result.value as Record<string, unknown>
      const commPatterns = (result.communication_patterns || {}) as Record<string, unknown>
      const perfMetrics = (result.performance_metrics || {}) as Record<string, unknown>
      const sysHealth = (result.system_health || {}) as Record<string, unknown>
      const realtimeMetrics = (result.realtime_metrics || {}) as Record<string, unknown>
      const totalCalls = (commPatterns.total_api_calls as number) || 0
      const avgResponseTime = (commPatterns.avg_response_time as number) || (perfMetrics.avg_response_time as number) || 0
      const activeConns = realtimeMetrics.active_connections as Record<string, unknown>
      const activeConnections = (sysHealth.active_connections as number) || (activeConns?.value as number) || 0
      let healthStatus = 'Unknown'
      if (sysHealth.status) healthStatus = sysHealth.status as string
      else if (sysHealth.cpu_percent !== undefined) healthStatus = (sysHealth.cpu_percent as number) < 80 ? 'Healthy' : 'Warning'
      systemOverview.value = { api_requests_per_minute: totalCalls, average_response_time: Math.round(avgResponseTime * 1000), active_connections: activeConnections, system_health: healthStatus }
    }
  } catch (error: unknown) { logger.error('loadSystemOverview failed:', error); systemOverview.value = null }
}

const loadCommunicationPatterns = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/communication/patterns`)
    if (!response.ok) throw new Error(`Status ${response.status}`)
    const result = await response.json()
    const wsActivity = result.websocket_activity || {}
    const apiPatterns = result.api_patterns || []
    const totalCalls = result.total_api_calls || 0
    const wsConnections = Object.keys(wsActivity).length || 0
    const apiFrequency = apiPatterns.length > 0 ? Math.round(apiPatterns.reduce((sum: number, p: Record<string, unknown>) => sum + ((p.frequency as number) || 0), 0) / Math.max(apiPatterns.length, 1)) : totalCalls
    const avgResponseTime = result.avg_response_time || 0
    communicationPatterns.value = { websocket_connections: wsConnections, api_call_frequency: apiFrequency, data_transfer_rate: Math.round((totalCalls * avgResponseTime * 10) / 100) / 10, unique_endpoints: result.unique_endpoints || 0 }
  } catch (error: unknown) { logger.error('loadCommunicationPatterns failed:', error); communicationPatterns.value = null }
}

const loadCodeQuality = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const healthResponse = await fetchWithAuth(`${backendUrl}/api/quality/health-score`)
    const healthData = healthResponse.ok ? await healthResponse.json() : null
    const duplicatesResponse = await fetchWithAuth(withSourceId(`${backendUrl}/api/analytics/codebase/duplicates`))
    const duplicatesData = duplicatesResponse.ok ? await duplicatesResponse.json() : null
    const debtResponse = await fetchWithAuth(`${backendUrl}/api/debt/summary`)
    const debtData = debtResponse.ok ? await debtResponse.json() : null
    if (healthData?.status === 'no_data' && debtData?.status === 'no_data') { codeQuality.value = null; return }
    codeQuality.value = { overall_score: Math.round(healthData?.overall || 0), test_coverage: Math.round(healthData?.breakdown?.testability || 0), code_duplicates: duplicatesData?.total || 0, technical_debt: debtData?.summary?.total_hours || 0 }
  } catch (error: unknown) { logger.error('loadCodeQuality failed:', error) }
}

const loadPerformanceMetrics = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const summaryResponse = await fetchWithAuth(`${backendUrl}/api/performance/summary`)
    const summaryData = summaryResponse.ok ? await summaryResponse.json() : null
    const monitoringResponse = await fetchWithAuth(`${backendUrl}/api/monitoring/status`)
    const monitoringData = monitoringResponse.ok ? await monitoringResponse.json() : null
    const qualityResponse = await fetchWithAuth(`${backendUrl}/api/quality/health-score`)
    const qualityData = qualityResponse.ok ? await qualityResponse.json() : null
    if (summaryData?.status === 'no_data' && qualityData?.status === 'no_data') { performanceMetrics.value = null; return }
    const perfScore = qualityData?.breakdown?.performance || 0
    performanceMetrics.value = { efficiency_score: Math.round(summaryData?.average_score || perfScore) || Math.round(perfScore), memory_usage: (summaryData?.patterns_enabled || 0) > 0 ? (summaryData?.patterns_enabled || 0) * 15 : 0, cpu_usage: Math.round(100 - perfScore), load_time: monitoringData?.uptime_seconds ? Math.round(monitoringData.uptime_seconds) : 0 }
  } catch (error: unknown) { logger.error('loadPerformanceMetrics failed:', error) }
}

// --- Real-Time / Refresh --------------------------------------------
const refreshAllMetrics = async () => {
  await Promise.all([loadCommunicationPatterns(), loadCodeQuality(), loadPerformanceMetrics(), getCodebaseStats(), getProblemsReport(), loadDeclarations()])
}

const toggleRealTime = () => {
  if (realTimeEnabled.value) { refreshInterval.value = setInterval(refreshAllMetrics, 30000) }
  else { if (refreshInterval.value) { clearInterval(refreshInterval.value); refreshInterval.value = null } }
}

// --- Event Handlers -------------------------------------------------
const handleFileNavigate = (filePath: string) => {
  logger.debug('Navigate to file:', filePath)
  showToast(t('analytics.codebase.notify.selected', { item: filePath }), 'info', 2000)
}

const handleFunctionSelect = (funcId: string) => {
  logger.debug('Selected function:', funcId)
  showToast(t('analytics.codebase.notify.selected', { item: funcId }), 'info', 2000)
}

const onPatternAnalysisComplete = (report: Record<string, unknown>) => {
  const summary = report?.analysis_summary as Record<string, unknown> | undefined
  logger.info('Pattern analysis complete:', summary)
  notify(t('analytics.codebase.notify.patternAnalysisComplete', { count: (summary?.total_patterns_found as number) || 0 }), 'success')
}

const onPatternAnalysisError = (message: string) => {
  logger.error('Pattern analysis error:', message)
  notify(t('analytics.codebase.notify.patternAnalysisError', { error: message }), 'error')
}

// --- Lifecycle ------------------------------------------------------
onMounted(async () => {
  const sourceId = route.params.sourceId as string | undefined
  if (!sourceId) { analyticsRouter.replace({ name: 'analytics-codebase' }); return }
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/sources/${sourceId}`)
    if (resp.ok) {
      const source = await resp.json()
      selectedSource.value = source
      rootPath.value = source.clone_path || ''
      localStorage.setItem(STORAGE_KEY_PATH, rootPath.value)
    } else { notify(t('analytics.codebase.notify.sourceNotFound'), 'error'); analyticsRouter.replace({ name: 'analytics-codebase' }); return }
  } catch (err: unknown) {
    logger.error('Failed to load source metadata:', err instanceof Error ? err.message : String(err))
    notify(t('analytics.codebase.notify.sourceNotFound'), 'error')
    analyticsRouter.replace({ name: 'analytics-codebase' }); return
  }
  await checkCurrentIndexingJob()
  loadCachedAnalyticsData()
  loadSources()
})

onUnmounted(() => {
  if (refreshInterval.value) clearInterval(refreshInterval.value)
  stopJobPolling()
})
</script>
<style scoped>
/* Issue #704: Uses CSS design tokens via getCssVar() helper */
.codebase-analytics {
  padding: 20px;
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  max-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}

/* Header and button styles moved to CodebaseAnalyticsHeader.vue */

.empty-state-container {
  padding: var(--spacing-8) var(--spacing-4);
  display: flex;
  justify-content: center;
}

.btn-lg {
  padding: var(--spacing-3) var(--spacing-6);
  font-size: var(--text-base);
}

/* Debug, progress, and phase styles moved to CodebaseProgressPanel.vue */

/* Enhanced Analytics Grid */
.enhanced-analytics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}

.card-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-header-content h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.1em;
  font-weight: 600;
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8em;
  color: var(--text-muted);
}

.refresh-indicator.active {
  color: var(--chart-green);
}

.refresh-indicator .fas {
  font-size: 0.7em;
}

.refresh-btn {
  background: var(--bg-tertiary);
  border: 1px solid var(--bg-hover);
  color: var(--text-secondary);
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: var(--bg-hover);
  color: var(--text-on-primary);
}

/* Issue #609: Section Export Buttons */
.section-export-buttons {
  display: inline-flex;
  gap: 4px;
  margin-left: 10px;
}

.export-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--bg-tertiary);
  color: var(--text-muted);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.export-btn:hover {
  background: var(--bg-tertiary);
  color: var(--color-info);
  border-color: var(--color-info);
}

.export-btn i {
  font-size: 0.7rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.metric-item {
  text-align: center;
}

.metric-label {
  font-size: 0.8em;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.metric-value {
  font-size: 1.4em;
  font-weight: 700;
  color: var(--text-on-primary);
}

.metric-value.health-good { color: var(--chart-green); }
.metric-value.health-warning { color: var(--color-warning); }
.metric-value.health-critical { color: var(--color-error); }
.metric-value.health-unknown { color: var(--text-tertiary); }

.communication-metrics, .performance-details, .quality-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pattern-item, .performance-item, .quality-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--bg-tertiary);
}

.pattern-item:last-child, .performance-item:last-child, .quality-item:last-child {
  border-bottom: none;
}

.pattern-label, .performance-label, .quality-label {
  color: var(--text-secondary);
  font-size: 0.9em;
}

.pattern-value, .performance-value, .quality-value {
  color: var(--text-on-primary);
  font-weight: 600;
}

.quality-score, .performance-gauge {
  text-align: center;
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 8px;
}

.score-value, .gauge-value {
  font-size: 2.5em;
  font-weight: 700;
  margin-bottom: 4px;
}

.score-label, .gauge-label {
  font-size: 0.9em;
  color: var(--text-muted);
}

.quality-high, .efficiency-high {
  background: rgba(34, 197, 94, 0.1);
  color: var(--chart-green);
}

.quality-medium, .efficiency-medium {
  background: rgba(251, 191, 36, 0.1);
  color: var(--color-warning-light);
}

.quality-low, .efficiency-low {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
}

.btn-link {
  background: none;
  border: none;
  color: var(--chart-blue);
  cursor: pointer;
  text-decoration: underline;
  font-size: 0.9em;
}

.btn-link:hover {
  color: var(--color-info-dark);
}

/* Traditional Analytics Section */
.analytics-section {
  background: var(--bg-secondary);
  border-radius: 12px;
  padding: 24px;
  border: 1px solid var(--bg-tertiary);
}

.real-time-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--bg-tertiary);
}

.toggle-switch {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  color: var(--text-secondary);
}

.toggle-switch input {
  display: none;
}

.toggle-slider {
  width: 40px;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  position: relative;
  transition: all 0.3s;
}

.toggle-slider:before {
  content: '';
  width: 16px;
  height: 16px;
  background: var(--text-on-primary);
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: all 0.3s;
}

.toggle-switch input:checked + .toggle-slider {
  background: var(--chart-green);
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(20px);
}

.refresh-all-btn {
  background: var(--chart-indigo);
  color: var(--text-on-primary);
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-all-btn:hover {
  background: var(--chart-indigo-dark);
}

.stats-section, .problems-section, .duplicates-section, .declarations-section {
  margin-bottom: 32px;
}

.stats-section h3, .problems-section h3, .duplicates-section h3, .declarations-section h3 {
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.stat-value {
  font-size: 2em;
  font-weight: 700;
  color: var(--chart-green);
  margin-bottom: 4px;
  text-align: center;
}

.stat-label {
  color: var(--text-muted);
  font-size: 0.9em;
  text-align: center;
}

.problems-list, .duplicates-list, .declarations-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.problem-item, .duplicate-item, .declaration-item {
  background: var(--bg-card);
  border: 1px solid var(--bg-tertiary);
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.problem-item:hover, .duplicate-item:hover, .declaration-item:hover {
  border-color: var(--bg-hover);
  transform: translateX(4px);
}

.problem-item.priority-critical {
  border-left: 4px solid var(--color-error-hover);
}

.problem-item.priority-high {
  border-left: 4px solid var(--chart-orange);
}

.problem-item.priority-medium {
  border-left: 4px solid var(--color-warning-dark);
}

.problem-item.priority-low {
  border-left: 4px solid var(--color-success-dark);
}

.problem-header, .duplicate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.problem-type, .duplicate-similarity {
  font-weight: 600;
  color: var(--text-on-primary);
}

.problem-severity, .duplicate-lines {
  font-size: 0.8em;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.3);
}

.problem-description, .problem-file, .problem-suggestion {
  margin-bottom: 4px;
  font-size: 0.9em;
}

.problem-description {
  color: var(--text-secondary);
}

.problem-file {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

.problem-suggestion {
  color: var(--color-warning-light);
  font-style: italic;
}

.duplicate-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}

.duplicate-file {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

/* Grouped Problems Section */
.problems-grouped {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.severity-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}

.severity-card {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 2px solid var(--bg-tertiary);
  transition: all 0.2s ease;
}

.severity-card:hover {
  transform: translateY(-2px);
}

.severity-card.severity-critical {
  border-color: var(--color-error-hover);
  background: rgba(220, 38, 38, 0.1);
}

.severity-card.severity-high {
  border-color: var(--chart-orange);
  background: rgba(234, 88, 12, 0.1);
}

.severity-card.severity-medium {
  border-color: var(--color-warning-dark);
  background: rgba(217, 119, 6, 0.1);
}

.severity-card.severity-low {
  border-color: var(--color-success-dark);
  background: rgba(5, 150, 105, 0.1);
}

.severity-count {
  font-size: 2em;
  font-weight: 700;
  color: var(--text-on-primary);
  line-height: 1;
}

.severity-card.severity-critical .severity-count { color: var(--color-error); }
.severity-card.severity-high .severity-count { color: var(--chart-orange); }
.severity-card.severity-medium .severity-count { color: var(--color-warning); }
.severity-card.severity-low .severity-count { color: var(--color-success); }

.severity-label {
  font-size: 0.8em;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-top: 4px;
  font-weight: 500;
}

.problems-by-type {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.problem-type-group {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--bg-tertiary);
  overflow: hidden;
}

.problem-type-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.problem-type-header:hover {
  background: var(--bg-tertiary);
}

.type-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.type-info i {
  color: var(--text-tertiary);
  font-size: 0.9em;
  transition: transform 0.2s ease;
}

.type-name {
  font-weight: 600;
  color: var(--text-secondary);
}

.type-count {
  color: var(--text-muted);
  font-size: 0.9em;
}

.type-severity-badges {
  display: flex;
  gap: 6px;
}

.badge {
  font-size: 0.7em;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.badge-critical {
  background: var(--color-error-bg);
  color: var(--color-error-light);
}

.badge-high {
  background: var(--color-warning-bg);
  color: var(--chart-orange-light);
}

.badge-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning-light);
}

.badge-low {
  background: var(--color-success-bg);
  color: var(--color-success-light);
}

.problem-type-items {
  padding: 8px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-card);
  border-top: 1px solid var(--bg-tertiary);
}

.problem-type-items .problem-item {
  margin: 0;
  padding: 12px;
  background: var(--bg-secondary);
}

.more-problems-note {
  text-align: center;
  color: var(--text-tertiary);
  font-style: italic;
  padding: 8px;
  font-size: 0.9em;
}

/* ============================================
   UNIFIED ANALYTICS SECTION STYLES
   Consistent formatting across all sections
   ============================================ */

/* Base Analytics Section */
.analytics-section {
  margin-top: 24px;
  padding: 20px;
  background: var(--bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--bg-tertiary);
}

.analytics-section h3 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 1.1em;
  flex-wrap: wrap;
}

.analytics-section .total-count {
  font-size: 0.85em;
  color: var(--text-muted);
  font-weight: normal;
}

/* Section Content Container */
.section-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Unified Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
}

.summary-card {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid var(--bg-tertiary);
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.summary-card:hover {
  transform: translateY(-2px);
}

.summary-value {
  font-size: 1.8em;
  font-weight: 700;
  color: var(--text-on-primary);
}

.summary-label {
  font-size: 0.75em;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-top: 4px;
}

/* Summary Card Variants */
.summary-card.total { border-color: var(--chart-indigo); }
.summary-card.total .summary-value { color: var(--chart-indigo-light); }
.summary-card.critical { border-color: var(--color-error); }
.summary-card.critical .summary-value { color: var(--color-error); }
.summary-card.high { border-color: var(--chart-orange); }
.summary-card.high .summary-value { color: var(--chart-orange); }
.summary-card.medium { border-color: var(--color-warning); }
.summary-card.medium .summary-value { color: var(--color-warning); }
.summary-card.low { border-color: var(--chart-green); }
.summary-card.low .summary-value { color: var(--chart-green); }
.summary-card.info { border-color: var(--chart-blue); }
.summary-card.info .summary-value { color: var(--chart-blue); }

/* Declaration Type Variants */
.summary-card.type-function { border-color: var(--chart-purple); }
.summary-card.type-function .summary-value { color: var(--chart-purple-light); }
.summary-card.type-class { border-color: var(--chart-teal); }
.summary-card.type-class .summary-value { color: var(--chart-teal-light); }
.summary-card.type-method { border-color: var(--chart-pink); }
.summary-card.type-method .summary-value { color: var(--chart-pink-light); }
.summary-card.type-variable { border-color: var(--chart-lime); }
.summary-card.type-variable .summary-value { color: var(--chart-lime-light); }
.summary-card.type-constant { border-color: var(--color-warning); }
.summary-card.type-constant .summary-value { color: var(--color-warning-light); }
.summary-card.type-import { border-color: var(--text-tertiary); }
.summary-card.type-import .summary-value { color: var(--text-muted); }
.summary-card.type-other { border-color: var(--text-tertiary); }
.summary-card.type-other .summary-value { color: var(--text-muted); }


/* Panel-specific CSS migrated to panels/ — Issue #1589 */

/* Issue #566: Code Intelligence Section Styles */
.code-intelligence-section h3 {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.code-intelligence-section .section-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.code-intelligence-section .action-btn {
  padding: 6px 12px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85em;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}

.code-intelligence-section .action-btn:hover:not(:disabled) {
  background: var(--bg-card);
  border-color: var(--color-info-dark);
}

.code-intelligence-section .action-btn.primary {
  background: var(--color-info-dark);
  border-color: var(--color-info-dark);
  color: white;
}

.code-intelligence-section .action-btn.primary:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.code-intelligence-section .action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Code Intelligence Tabs */
.code-intel-tabs {
  margin-top: 16px;
}

.code-intel-tabs .tabs-header {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-primary);
  margin-bottom: 16px;
}

.code-intel-tabs .tab-btn {
  padding: 8px 16px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9em;
  transition: all 0.15s ease;
}

.code-intel-tabs .tab-btn:hover {
  color: var(--text-primary);
}

.code-intel-tabs .tab-btn.active {
  color: var(--color-info-dark);
  border-bottom-color: var(--color-info-dark);
}

.code-intel-tabs .tab-count {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 0.8em;
}

.code-intel-tabs .tab-btn.active .tab-count {
  background: rgba(99, 102, 241, 0.2);
  color: var(--color-info-dark);
}

.code-intel-tabs .tabs-content {
  min-height: 200px;
}

/* Issue #1133: Source Registry Styles */
.source-selector-row {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  width: 100%;
}

.source-selector-wrapper {
  position: relative;
  flex: 2;
}

.source-select {
  width: 100%;
  padding: 10px 32px 10px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
  appearance: none;
  cursor: pointer;
  transition: border-color var(--duration-200);
}

.source-select:focus {
  outline: none;
  border-color: var(--color-info);
}

.select-chevron {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: var(--text-muted);
  font-size: 11px;
}

.btn-manage-sources {
  padding: 10px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  transition: all var(--duration-200);
}

.btn-manage-sources:hover {
  border-color: var(--color-info);
  color: var(--color-info);
}

.selected-source-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: var(--radius-lg);
  padding: 8px 16px;
  width: 100%;
  min-width: 0;
}

.selected-source-bar > i {
  color: var(--color-info);
  flex-shrink: 0;
}

.selected-source-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: nowrap;
}

.selected-source-path {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.selected-source-status {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  text-transform: capitalize;
  flex-shrink: 0;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.btn-clear-source {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  flex-shrink: 0;
  font-size: 11px;
  transition: color var(--duration-200);
}

.btn-clear-source:hover {
  color: var(--color-error);
}

/* Knowledge Base Opt-in Banner */
.kb-optin-banner {
  position: fixed;
  bottom: var(--spacing-6);
  right: var(--spacing-6);
  z-index: 900;
  max-width: 480px;
  width: 100%;
}

.kb-optin-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  background: var(--bg-card);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-xl);
  padding: var(--spacing-4) var(--spacing-5);
  box-shadow: var(--shadow-lg);
}

.kb-optin-content > i {
  font-size: var(--text-xl);
  color: var(--color-success);
  flex-shrink: 0;
}

.kb-optin-text {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  min-width: 0;
}

.kb-optin-text strong {
  display: block;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.kb-optin-btn {
  padding: 8px 14px;
  background: var(--color-success);
  border: none;
  border-radius: var(--radius-lg);
  color: white;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
  transition: opacity var(--duration-200);
}

.kb-optin-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.kb-optin-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.kb-optin-dismiss {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  font-size: 12px;
  flex-shrink: 0;
  transition: color var(--duration-200);
}

.kb-optin-dismiss:hover {
  color: var(--text-primary);
}

/* Scan runner styles moved to CodebaseProgressPanel.vue */
</style>
