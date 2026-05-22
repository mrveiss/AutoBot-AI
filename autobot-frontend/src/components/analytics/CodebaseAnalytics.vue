<template>
  <div class="codebase-analytics">
    <!-- Issue #1579: Header controls extracted to AnalyticsHeaderControls -->
    <AnalyticsHeaderControls
      :analyzing="analyzing"
      :root-path="rootPath"
      :selected-source="selectedSource"
      :scan-runner-running="scanRunner.running.value"
      :loading-api-endpoints="loadingApiEndpoints"
      :analyzing-code-smells="analyzingCodeSmells"
      :exporting-report="exportingReport"
      :clearing-cache="clearingCache"
      @index-codebase="indexCodebase"
      @run-full-analysis="runFullAnalysis"
      @stop="handleStop"
      @test-declarations="getDeclarationsData"
      @test-duplicates="getDuplicatesData"
      @test-hardcodes="getHardcodesData"
      @test-npu="testNpuConnection"
      @test-data-state="testDataState"
      @reset-state="resetState"
      @test-all-endpoints="testAllEndpoints"
      @api-coverage="getApiEndpointCoverage"
      @code-smells="runCodeSmellAnalysis"
      @health-score="getCodeHealthScore"
      @export-report="exportReport()"
      @clear-cache="clearCache"
    />

    <!-- Project Header Card (#1713) -->
    <div v-if="selectedSource" class="project-header-card">
      <div class="project-header-info">
        <div class="project-header-name">
          <i :class="selectedSource.source_type === 'github' ? 'github' : 'folder'"></i>
          {{ selectedSource.name }}
        </div>
        <div class="project-header-meta">
          <span v-if="selectedSource.repo" class="project-meta-item">
            <Icon name="code-branch" />
            {{ selectedSource.repo }}
          </span>
          <span v-if="selectedSource.branch" class="project-meta-item">
            <Icon name="tag" />
            {{ selectedSource.branch }}
          </span>
          <span class="project-meta-item" :class="'status-' + (selectedSource.status || 'unknown')">
            <Icon name="circle" />
            {{ selectedSource.status || 'unknown' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Issue #1579: Progress indicators extracted to AnalyticsProgressSection -->
    <AnalyticsProgressSection
      :analyzing="analyzing"
      :analyzing-code-smells="analyzingCodeSmells"
      :progress-status="progressStatus"
      :progress-percent="progressPercent"
      :current-job-id="currentJobId"
      :job-phases="jobPhases"
      :job-batches="jobBatches"
      :job-stats="jobStats"
      :scan-runner="scanRunner"
      :code-smells-progress-title="codeSmellsProgressTitle"
      @stop="handleStop"
    />

    <!-- Empty state when no cached results exist (#1458) -->
    <div v-if="!analyzing && !scanRunner.running.value && !hasAnyResults" class="empty-state-container">
      <EmptyState
        icon="database"
        :title="$t('analytics.codebase.empty.title')"
        :message="$t('analytics.codebase.empty.description')"
      >
        <template #actions>
          <button @click="indexCodebase" class="btn-primary btn-lg">
            <Icon name="database" />
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
          <Icon name="sync-alt" /> {{ $t('analytics.codebase.actions.refreshAll') }}
        </button>
      </div>

      <!-- Issue #1579: Stats + Charts section extracted to CodebaseChartsSection -->
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
        @export-section="handleExportSection"
        @load-unified-report="loadUnifiedReport"
        @load-chart-data="loadChartData"
        @update:selected-category="selectedCategory = $event"
        @index-codebase="indexCodebase"
      />

      <!-- Dependency Analysis, Import Tree, Function Call Graph (#1469) -->
      <CodebaseDependenciesPanel
        :dependency-data="dependencyData"
        :dependency-loading="dependencyLoading"
        :dependency-error="dependencyError ?? ''"
        :import-tree-data="importTreeData ?? []"
        :import-tree-loading="importTreeLoading"
        :import-tree-error="importTreeError ?? ''"
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

      <!-- Issue #1579: Problems Report extracted to ProblemsReportSection -->
      <ProblemsReportSection
        :problems="problemsReport"
        @export="(fmt: string) => exportSection('problems', fmt as 'md' | 'json')"
      />

      <!-- Code Intelligence: Anti-Pattern / Code Smells Report (#1469, #184) -->
      <CodeSmellsSection
        :smells="codeSmellsForPanel"
        :code-health-score="codeHealthScore"
        @export="(fmt: string) => exportSection('code-smells', fmt as 'md' | 'json')"
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
        :loading="loadingProgress.duplicates"
        @export="(fmt: string) => exportSection('duplicates', fmt as 'md' | 'json')"
      />

      <!-- Function Declarations (#1469, #184) -->
      <DeclarationsSection
        :declarations="declarationsForPanel"
        :loading="loadingProgress.declarations"
        @export="(fmt: string) => exportSection('declarations', fmt as 'md' | 'json')"
      />

      <!-- Hardcoded Values (#5277: wire orphan data flow) -->
      <HardcodesSection
        :hardcodes="hardcodeAnalysis"
        :loading="loadingProgress.hardcodes"
        @export="(fmt: string) => exportSection('hardcodes', fmt as 'md' | 'json')"
      />

      <!-- Issue #527: API Endpoint Checker Section (#1469: extracted to CodebaseApiEndpointsPanel) -->
      <CodebaseApiEndpointsPanel
        :analysis="apiEndpointAnalysis"
        :loading="loadingApiEndpoints"
        :error="apiEndpointsError"
        @refresh="getApiEndpointCoverage"
        @export="(fmt: string) => exportSection('api-endpoints', fmt as 'md' | 'json')"
      />

            <!-- Issue #244: Cross-Language Pattern Analysis Section (#1469: extracted to CodebaseCrossLanguagePanel) -->
      <CodebaseCrossLanguagePanel
        :analysis="crossLanguageAnalysis"
        :loading="loadingCrossLanguage"
        :error="crossLanguageError"
        @refresh="getCrossLanguageAnalysis"
        @run-full-scan="runCrossLanguageAnalysis"
        @export="(fmt: string) => exportSection('cross-language', fmt as 'md' | 'json')"
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
        @export="(fmt: string) => exportSection('config-duplicates', fmt as 'md' | 'json')"
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
        @export="(fmt: string) => exportSection('bug-prediction', fmt as 'md' | 'json')"
      />

            <!-- Issue #538: Code Intelligence Scores Section (#1469: extracted to CodebaseIntelligenceScoresPanel) -->
      <CodebaseIntelligenceScoresPanel
        :root-path="rootPath"
        :security-score="securityScore"
        :security-loading="loadingSecurityScore"
        :security-error="securityScoreError ?? ''"
        :security-findings="securityFindings"
        :security-findings-loading="loadingSecurityFindings"
        :performance-score="performanceScore"
        :performance-loading="loadingPerformanceScore"
        :performance-error="performanceScoreError ?? ''"
        :performance-findings="performanceFindings"
        :performance-findings-loading="loadingPerformanceFindings"
        :redis-health="redisHealth"
        :redis-loading="loadingRedisHealth"
        :redis-error="redisHealthError"
        :redis-optimizations="redisOptimizations"
        :redis-optimizations-loading="loadingRedisOptimizations"
        :health-score="codeIntelHealthScore"
        :quality-score="codeIntelQualityScore"
        :suggestions="codeIntelSuggestions"
        :analysis-history="codeIntelAnalysisHistory"
        @refresh-all="() => { loadSecurityScore(); loadPerformanceScore(); loadRedisHealth() }"
        @refresh-security="loadSecurityScore"
        @refresh-performance="loadPerformanceScore"
        @refresh-redis="loadRedisHealth"
        @load-security-findings="loadSecurityFindings"
        @load-performance-findings="loadPerformanceFindings"
        @load-redis-optimizations="loadRedisOptimizations"
        @load-health-score="codeIntelGetHealthScore"
        @load-quality-score="() => codeIntelGetQualityScore(rootPath, 'python')"
        @load-analysis-history="codeIntelGetAnalysisHistory"
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
        @export="(fmt: string) => exportSection('environment', fmt as 'md' | 'json')"
        @update:use-ai-filtering="useAiFiltering = $event"
        @update:ai-filtering-priority="aiFilteringPriority = $event"
      />

            <!-- Issue #248: Code Ownership and Expertise Map Section (#1469: extracted to CodebaseOwnershipPanel) -->
      <CodebaseOwnershipPanel
        :analysis="ownershipAnalysis"
        :loading="loadingOwnership"
        :error="ownershipError"
        @refresh="loadOwnershipAnalysis"
        @export="(fmt: string) => exportSection('ownership', fmt as 'md' | 'json')"
      />
    </div>

    <!-- Issue #1133: Knowledge Base Opt-in Banner -->
    <div v-if="showKnowledgeBaseOptIn" class="kb-optin-banner">
      <div class="kb-optin-content">
        <Icon name="book" />
        <div class="kb-optin-text">
          <strong>{{ $t('analytics.codebase.knowledgeBase.indexingComplete') }}</strong>
          {{ $t('analytics.codebase.knowledgeBase.addDescription') }}
        </div>
        <button
          class="kb-optin-btn"
          @click="addToKnowledgeBase"
          :disabled="knowledgeBaseAdding"
        >
          <i :class="knowledgeBaseAdding ? 'fas fa-spinner fa-spin' : 'plus'"></i>
          {{ knowledgeBaseAdding ? $t('analytics.codebase.knowledgeBase.adding') : $t('analytics.codebase.knowledgeBase.addToKnowledgeBase') }}
        </button>
        <button class="kb-optin-dismiss" @click="showKnowledgeBaseOptIn = false" :aria-label="$t('analytics.codebase.actions.dismiss')">
          <Icon name="times" />
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

    <!-- Issue #3436: Per-project sub-tab navigation and child route outlet -->
    <div v-if="route.params.sourceId" class="project-sub-tabs-container">
      <nav class="project-sub-tabs" role="tablist" aria-label="Project analytics tabs">
        <router-link
          :to="`/analytics/codebase/${route.params.sourceId}`"
          class="project-sub-tab"
          :class="{ 'project-sub-tab-active': isOverviewTabActive }"
          role="tab"
          :aria-selected="isOverviewTabActive"
        >
          <svg class="sub-tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span>{{ $t('analytics.codebase.tabs.overview', 'Overview') }}</span>
        </router-link>
        <router-link
          :to="`/analytics/codebase/${route.params.sourceId}/code-quality`"
          class="project-sub-tab"
          :class="{ 'project-sub-tab-active': isCodeQualityTabActive }"
          role="tab"
          :aria-selected="isCodeQualityTabActive"
        >
          <svg class="sub-tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{{ $t('analytics.codebase.tabs.codeQuality', 'Code Quality') }}</span>
        </router-link>
        <router-link
          :to="`/analytics/codebase/${route.params.sourceId}/code-review`"
          class="project-sub-tab"
          :class="{ 'project-sub-tab-active': isCodeReviewTabActive }"
          role="tab"
          :aria-selected="isCodeReviewTabActive"
        >
          <svg class="sub-tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          <span>{{ $t('analytics.codebase.tabs.codeReview', 'Code Review') }}</span>
        </router-link>
        <router-link
          :to="`/analytics/codebase/${route.params.sourceId}/evolution`"
          class="project-sub-tab"
          :class="{ 'project-sub-tab-active': isEvolutionTabActive }"
          role="tab"
          :aria-selected="isEvolutionTabActive"
        >
          <svg class="sub-tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
          <span>{{ $t('analytics.codebase.tabs.evolution', 'Evolution') }}</span>
        </router-link>
        <router-link
          :to="`/analytics/codebase/${route.params.sourceId}/code-generation`"
          class="project-sub-tab"
          :class="{ 'project-sub-tab-active': isCodeGenerationTabActive }"
          role="tab"
          :aria-selected="isCodeGenerationTabActive"
        >
          <svg class="sub-tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span>{{ $t('analytics.codebase.tabs.codeGeneration', 'Code Generation') }}</span>
        </router-link>
      </nav>

      <!-- Child route view renders here when a sub-tab is active -->
      <router-view v-if="!isOverviewTabActive" class="project-sub-tab-view" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CodebaseAnalytics.vue - Orchestration Layer
 *
 * Issues #2228, #2230: Script section refactored into composables.
 * This file now serves as the wiring layer connecting composables
 * to the template, child component events, and lifecycle hooks.
 *
 * Composables:
 *   useSourceRegistry     - Source selection, CRUD, knowledge base opt-in
 *   useAnalyticsDataFetchers - Stats, problems, charts, dependencies, duplicates
 *   useCodeIntelAnalysis   - Security/performance/redis scores, code smells, cross-language
 *   useAnalyticsDebug      - NPU test, endpoint tests, state inspection, display utilities
 *   useIndexingJob         - Indexing job polling, progress, cancellation (pre-existing)
 *   useDashboardLoaders    - Dashboard overview panel loaders (pre-existing)
 *   useCodebaseExport      - Report/section export (pre-existing)
 */
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'
import PatternAnalysis from '@/components/analytics/PatternAnalysis.vue'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { getCssVar } from '@/composables/useCssVars'
import { useCodebaseExport, type SectionType } from '@/composables/analytics/useCodebaseExport'
import type { ScanDefinition } from '@/composables/useAnalyticsScanRunner'
import { useIndexingJob } from '@/composables/analytics/useIndexingJob'
import { useDashboardLoaders } from '@/composables/analytics/useDashboardLoaders'
import { useSourceRegistry } from '@/composables/analytics/useSourceRegistry'
import { useAnalyticsDataFetchers } from '@/composables/analytics/useAnalyticsDataFetchers'
import { useCodeIntelAnalysis } from '@/composables/analytics/useCodeIntelAnalysis'
import { useAnalyticsDebug } from '@/composables/analytics/useAnalyticsDebug'
import { createLogger } from '@/utils/debugUtils'
// Issue #1133: Code Source Registry Components
import CodebaseOverviewPanel from '@/components/analytics/CodebaseOverviewPanel.vue'
import CodebaseDependenciesPanel from '@/components/analytics/CodebaseDependenciesPanel.vue'
import CodebaseSecurityPanel from '@/components/analytics/CodebaseSecurityPanel.vue'
import CodeSmellsSection from '@/components/analytics/CodeSmellsSection.vue'
import DuplicatesSection from '@/components/analytics/DuplicatesSection.vue'
import DeclarationsSection from '@/components/analytics/DeclarationsSection.vue'
import HardcodesSection from '@/components/analytics/HardcodesSection.vue'
import SourceManager from '@/components/analytics/SourceManager.vue'
import AddSourceModal from '@/components/analytics/AddSourceModal.vue'
import ShareSourceModal from '@/components/analytics/ShareSourceModal.vue'
import ProblemsReportSection from '@/components/analytics/ProblemsReportSection.vue'
import AnalyticsProgressSection from '@/components/analytics/AnalyticsProgressSection.vue'
import AnalyticsHeaderControls from '@/components/analytics/AnalyticsHeaderControls.vue'
// Issue #1469: Extracted panel sub-components
import CodebaseApiEndpointsPanel from '@/components/analytics/panels/CodebaseApiEndpointsPanel.vue'
import CodebaseCrossLanguagePanel from '@/components/analytics/panels/CodebaseCrossLanguagePanel.vue'
import CodebaseConfigDuplicatesPanel from '@/components/analytics/panels/CodebaseConfigDuplicatesPanel.vue'
import CodebaseBugPredictionPanel from '@/components/analytics/panels/CodebaseBugPredictionPanel.vue'
import CodebaseIntelligenceScoresPanel from '@/components/analytics/panels/CodebaseIntelligenceScoresPanel.vue'
import CodebaseEnvironmentPanel from '@/components/analytics/panels/CodebaseEnvironmentPanel.vue'
import CodebaseOwnershipPanel from '@/components/analytics/panels/CodebaseOwnershipPanel.vue'
import CodebaseChartsSection from '@/components/analytics/panels/CodebaseChartsSection.vue'

const logger = createLogger('CodebaseAnalytics')

// i18n + routing
const { t } = useI18n()
const route = useRoute()
const analyticsRouter = useRouter()

// Issue #3436: Sub-tab active-state computed properties
const isOverviewTabActive = computed(() => {
  const path = route.path
  // Active when on the exact project path (no child segment)
  return /^\/analytics\/codebase\/[^/]+\/?$/.test(path)
})
const isCodeQualityTabActive = computed(() => route.path.includes('/code-quality'))
const isCodeReviewTabActive = computed(() => route.path.includes('/code-review'))
const isEvolutionTabActive = computed(() => route.path.endsWith('/evolution'))
const isCodeGenerationTabActive = computed(() => route.path.includes('/code-generation'))

// Toast notifications
const { showToast } = useNotificationBus()

// Notification helper
const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// =============================================
// Composable 1: Source Registry (#2230)
// =============================================
const {
  rootPath,
  selectedSource,
  showSourceManager,
  showAddSourceModal,
  showShareSourceModal,
  editTargetSource,
  shareTargetSource,
  showKnowledgeBaseOptIn,
  knowledgeBaseAdding,
  sourceIdParam,
  sourceIdQuery,
  withSourceId,
  loadSources,
  loadSourceById,
  handleSelectSource,
  handleSourceSaved,
  handleShareSaved,
  handleEditSource,
  handleShareSource,
  addToKnowledgeBase,
  STORAGE_KEY_PATH,
} = useSourceRegistry({ t, showToast, notify })

const analyzing = ref(false)

// =============================================
// Composable 2: Analytics Data Fetchers (#2230)
// =============================================
const {
  scanRunner,
  codebaseStats,
  problemsReport,
  duplicateAnalysis,
  declarationAnalysis,
  hardcodeAnalysis,
  loadingProgress,
  chartData,
  chartDataLoading,
  chartDataError,
  unifiedReportLoading,
  unifiedReportError,
  selectedCategory,
  callGraphData,
  callGraphSummary,
  callGraphOrphaned,
  callGraphLoading,
  callGraphError,
  dependencyData,
  dependencyLoading,
  dependencyError,
  importTreeData,
  importTreeLoading,
  importTreeError,
  progressPercent,
  progressStatus,
  hasAnyResults,
  availableCategories,
  codeSmellsForPanel,
  declarationsForPanel,
  loadChartData,
  loadUnifiedReport,
  loadCallGraphData,
  handleFileNavigate,
  handleFunctionSelect,
  loadDeclarations,
  loadDependencyData,
  loadImportTreeData,
  getCodebaseStats,
  getProblemsReport,
  getDeclarationsData,
  getDuplicatesData,
  getHardcodesData,
  loadCachedAnalyticsData,
  runAllAnalysisScans,
} = useAnalyticsDataFetchers({
  rootPath,
  sourceIdParam,
  sourceIdQuery,
  withSourceId,
  analyzing,
  t,
  showToast,
  notify,
})

// =============================================
// Composable 3: Code Intel Analysis (#2230)
// =============================================
const {
  codeIntelLoading,
  codeIntelSecurityFindings,
  codeIntelPerformanceFindings,
  codeIntelRedisFindings,
  codeIntelFindingsLoading,
  codeIntelTotalFindings,
  codeIntelHealthScore,
  codeIntelQualityScore,
  codeIntelAnalysisHistory,
  codeIntelSuggestions,
  codeIntelGetHealthScore,
  codeIntelGetQualityScore,
  codeIntelGetAnalysisHistory,
  runCodeIntelligenceAnalysis,
  handleFileScan,
  codeSmellsReport,
  codeHealthScore,
  analyzingCodeSmells,
  codeSmellsProgressTitle,
  exportingReport,
  clearingCache,
  clearCache: clearCache_composable,
  runCodeSmellAnalysis,
  getCodeHealthScore,
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
  securityFindings,
  loadingSecurityFindings,
  performanceFindings,
  loadingPerformanceFindings,
  redisOptimizations,
  loadingRedisOptimizations,
  loadSecurityFindings,
  loadPerformanceFindings,
  loadRedisOptimizations,
  apiEndpointAnalysis,
  loadingApiEndpoints,
  apiEndpointsError,
  loadApiEndpointAnalysis,
  getApiEndpointCoverage,
  configDuplicatesAnalysis,
  loadingConfigDuplicates,
  configDuplicatesError,
  loadConfigDuplicates,
  bugPredictionTask,
  bugPredictionAnalysis,
  loadingBugPrediction,
  bugPredictionError,
  loadBugPrediction,
  loadCachedBugPrediction,
  loadCachedSecurityScore,
  environmentAnalysis,
  loadingEnvAnalysis,
  envAnalysisError,
  useAiFiltering,
  aiFilteringModel,
  aiFilteringPriority,
  llmFilteringResult,
  loadEnvironmentAnalysis,
  ownershipAnalysis,
  loadingOwnership,
  ownershipError,
  loadOwnershipAnalysis,
  crossLanguageAnalysis,
  loadingCrossLanguage,
  crossLanguageError,
  getCrossLanguageAnalysis,
  runCrossLanguageAnalysis,
} = useCodeIntelAnalysis({
  rootPath,
  sourceIdParam,
  sourceIdQuery,
  withSourceId,
  analyzing,
  t,
  showToast,
  notify,
})

// =============================================
// Composable 4: Dashboard Loaders (pre-existing)
// =============================================
const {
  systemOverview,
  communicationPatterns,
  codeQuality,
  performanceMetrics,
  realTimeEnabled,
  refreshInterval,
  loadSystemOverview,
  loadCommunicationPatterns,
  loadCodeQuality,
  loadPerformanceMetrics,
  refreshAllMetrics,
  toggleRealTime,
} = useDashboardLoaders({
  withSourceId,
  additionalRefreshCallbacks: () => [
    getCodebaseStats(),
    getProblemsReport(),
    loadDeclarations(),
  ],
})

// =============================================
// Composable 5: Indexing Job (pre-existing)
// Initialized before useAnalyticsDebug so real refs are available (#2259)
// =============================================
const {
  currentJobId,
  currentJobStatus,
  jobPhases,
  jobBatches,
  jobStats,
  checkCurrentIndexingJob,
  stopJobPolling,
  cancelIndexingJob,
  indexCodebase,
} = useIndexingJob({
  rootPath,
  analyzing,
  progressPercent,
  progressStatus,
  selectedSource,
  withSourceId,
  notify,
  t,
  problemsReport,
  codebaseStats,
  declarationAnalysis,
  duplicateAnalysis,
  hardcodeAnalysis,
  chartData,
  showKnowledgeBaseOptIn,
  onIndexComplete: () => runAllAnalysisScans(codeIntelFullScans()),
  storageKeyPath: STORAGE_KEY_PATH,
})

// =============================================
// Composable 6: Analytics Debug (#2230)
// Initialized after useIndexingJob so it receives real refs (#2259)
// =============================================
const {
  testNpuConnection,
  testAllEndpoints,
  testDataState,
  resetState,
} = useAnalyticsDebug({
  rootPath,
  analyzing,
  progressStatus,
  currentJobId,
  currentJobStatus,
  progressPercent,
  codebaseStats,
  problemsReport,
  declarationAnalysis,
  duplicateAnalysis,
  stopJobPolling,
  t,
  notify,
})

// =============================================
// Composable 7: Export (pre-existing)
// =============================================
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
    'hardcodes': hardcodeAnalysis as Ref<unknown>,
  },
  exportingReport,
  progressStatus,
  withSourceId,
  notify,
  t,
})

// Typed wrapper for @export-section event handler (section is string from emit but SectionType at runtime)
const handleExportSection = (section: string, fmt: 'md' | 'json') =>
  exportSection(section as SectionType, fmt)

// =============================================
// Orchestration: Event Handlers + Lifecycle
// =============================================

// #2258: Bridge code-intel scans into the data-fetcher scan orchestrator.
// loadCachedAnalyticsData uses lighter cached loaders; runAllAnalysisScans
// uses full re-fetch triggers after indexing completes.
// #2390: Include all code-intel scans so every panel populates on page visit
const codeIntelExtraScans = (): ScanDefinition[] => [
  { id: 'configDuplicates', label: t('analytics.codebase.scans.configDuplicates'), run: async () => { await loadConfigDuplicates() } },
  { id: 'apiEndpoints', label: t('analytics.codebase.scans.apiEndpoints'), run: async () => { await loadApiEndpointAnalysis() } },
  { id: 'bugPrediction', label: t('analytics.codebase.scans.bugPrediction'), run: async () => { await loadCachedBugPrediction() } },
  { id: 'security', label: t('analytics.codebase.scans.security'), run: async () => { await loadCachedSecurityScore() } },
  { id: 'performance', label: t('analytics.codebase.scans.performance'), run: async () => { await loadPerformanceScore() } },
  { id: 'redis', label: t('analytics.codebase.scans.redis'), run: async () => { await loadRedisHealth() } },
  { id: 'environment', label: t('analytics.codebase.scans.environment'), run: async () => { await loadEnvironmentAnalysis() } },
  { id: 'ownership', label: t('analytics.codebase.scans.ownership'), run: async () => { await loadOwnershipAnalysis() } },
  { id: 'crossLanguage', label: t('analytics.codebase.scans.crossLanguage'), run: async () => { await getCrossLanguageAnalysis() } },
  { id: 'codeIntelligence', label: t('analytics.codebase.scans.codeIntelligence'), run: async () => { await runCodeIntelligenceAnalysis() } },
]

const codeIntelFullScans = (): ScanDefinition[] => [
  { id: 'configDuplicates', label: t('analytics.codebase.scans.configDuplicates'), run: async () => { await loadConfigDuplicates() } },
  { id: 'apiEndpoints', label: t('analytics.codebase.scans.apiEndpoints'), run: async () => { await loadApiEndpointAnalysis() } },
  { id: 'bugPrediction', label: t('analytics.codebase.scans.bugPrediction'), run: async () => { await loadBugPrediction() } },
  { id: 'security', label: t('analytics.codebase.scans.security'), run: async () => { await loadSecurityScore() } },
  { id: 'performance', label: t('analytics.codebase.scans.performance'), run: async () => { await loadPerformanceScore() } },
  { id: 'redis', label: t('analytics.codebase.scans.redis'), run: async () => { await loadRedisHealth() } },
  { id: 'environment', label: t('analytics.codebase.scans.environment'), run: async () => { await loadEnvironmentAnalysis() } },
  { id: 'ownership', label: t('analytics.codebase.scans.ownership'), run: async () => { await loadOwnershipAnalysis() } },
  { id: 'crossLanguage', label: t('analytics.codebase.scans.crossLanguage'), run: async () => { await getCrossLanguageAnalysis() } },
  { id: 'codeIntelligence', label: t('analytics.codebase.scans.codeIntelligence'), run: async () => { await runCodeIntelligenceAnalysis() } },
]

// Issue #208: Pattern Analysis component ref
interface PatternAnalysisComponent {
  runAnalysis: () => Promise<void>
  error?: string
}
const patternAnalysisRef = ref<PatternAnalysisComponent | null>(null)

// Stop all running operations
const handleStop = () => {
  if (analyzing.value && currentJobId.value) {
    cancelIndexingJob()
  }
  if (scanRunner.running.value) {
    scanRunner.cancel()
  }
}

// Clear analysis cache — delegates to useCodeIntelAnalysis.clearCache (#6068)
const clearCache = () =>
  clearCache_composable(withSourceId, () => {
    codebaseStats.value = null
    problemsReport.value = []
    declarationAnalysis.value = []
    duplicateAnalysis.value = []
    hardcodeAnalysis.value = []
    chartData.value = null
    progressStatus.value = t('analytics.codebase.status.cacheCleared')
  })

// Run full analysis with scan runner
const runFullAnalysis = async () => {
  await scanRunner.runAll([
    { id: 'indexing', label: t('analytics.codebase.scans.indexing'), run: () => indexCodebase() },
    {
      id: 'patterns',
      label: t('analytics.codebase.scans.patterns'),
      run: async () => {
        if (patternAnalysisRef.value?.runAnalysis) {
          await patternAnalysisRef.value.runAnalysis()
          if (patternAnalysisRef.value?.error) {
            throw new Error(patternAnalysisRef.value.error)
          }
        } else {
          throw new Error('Component not ready')
        }
      },
    },
    {
      id: 'crossLanguage',
      label: t('analytics.codebase.scans.crossLanguage'),
      run: () => runCrossLanguageAnalysis(),
    },
  ])
  const succeeded = scanRunner.completedCount.value
  const total = scanRunner.totalCount.value
  progressStatus.value = t('analytics.codebase.status.analysisComplete', { succeeded, total })
  if (scanRunner.failedCount.value > 0) {
    const failedNames = scanRunner.results.value
      .filter(r => r.status === 'failed')
      .map(r => r.label)
      .join(', ')
    logger.warn(`Full analysis partial failure: ${failedNames}`)
  }
}

// Pattern analysis event handlers
const onPatternAnalysisComplete = (report: any) => {
  logger.info('Pattern analysis complete:', report?.analysis_summary)
  notify(t('analytics.codebase.notify.patternAnalysisComplete', { count: report?.analysis_summary?.total_patterns_found || 0 }), 'success')
}

const onPatternAnalysisError = (message: string) => {
  logger.error('Pattern analysis error:', message)
  notify(t('analytics.codebase.notify.patternAnalysisError', { error: message }), 'error')
}

// =============================================
// Lifecycle Hooks
// =============================================
onMounted(async () => {
  const sourceId = route.params.sourceId as string | undefined
  if (!sourceId) {
    analyticsRouter.replace({ name: 'analytics-codebase' })
    return
  }

  // Load source metadata from backend (#6068: extracted to useSourceRegistry)
  const loaded = await loadSourceById(sourceId)
  if (!loaded) {
    analyticsRouter.replace({ name: 'analytics-codebase' })
    return
  }

  await checkCurrentIndexingJob()
  loadCachedAnalyticsData(codeIntelExtraScans())
  // #2390: Auto-load overview dashboard cards on page visit
  loadSystemOverview()
  loadCommunicationPatterns()
  loadCodeQuality()
  loadPerformanceMetrics()
  loadSources()
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
  stopJobPolling()
})
</script>
<style scoped>
/* Issue #704: Uses CSS design tokens via getCssVar() helper */
.codebase-analytics {
  padding: var(--spacing-5);
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}

/* Project Header Card (#1713) */
.project-header-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4) var(--spacing-5);
  margin-bottom: var(--spacing-4);
  border-left: 4px solid var(--accent-primary, #3b82f6);
  box-shadow: var(--shadow-sm);
}

.project-header-name {
  font-size: 1.15em;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.project-header-meta {
  display: flex;
  gap: var(--spacing-4);
  margin-top: var(--spacing-2);
  flex-wrap: wrap;
}

.project-meta-item {
  font-size: var(--text-sm);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.project-meta-item.status-ready { color: var(--color-success, #22c55e); }
.project-meta-item.status-syncing { color: var(--color-warning, #f59e0b); }
.project-meta-item.status-error { color: var(--color-error, #ef4444); }

.btn-primary {
  padding: var(--spacing-2-5) var(--spacing-5);
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  background: var(--chart-green);
  color: var(--text-on-success);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-success-dark);
  transform: translateY(-1px);
}

.btn-primary:disabled {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: not-allowed;
  transform: none;
}

.empty-state-container {
  padding: var(--spacing-8) var(--spacing-4);
  display: flex;
  justify-content: center;
}

.btn-lg {
  padding: var(--spacing-3) var(--spacing-6);
  font-size: var(--text-base);
}

/* Traditional Analytics Section */
.analytics-section {
  margin-top: var(--spacing-6);
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--bg-tertiary);
}

.real-time-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--bg-tertiary);
}

.toggle-switch {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
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
  border-radius: var(--radius-xl);
  position: relative;
  transition: all var(--duration-300);
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
  transition: all var(--duration-300);
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
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.refresh-all-btn:hover {
  background: var(--chart-indigo-dark);
}

/* Knowledge Base Opt-in Banner */
.kb-optin-banner {
  position: fixed;
  bottom: var(--spacing-6);
  right: var(--spacing-6);
  z-index: var(--z-modal-backdrop);
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
  margin-bottom: var(--spacing-0-5);
}

.kb-optin-btn {
  padding: var(--spacing-2) var(--spacing-3-5);
  background: var(--color-success);
  border: none;
  border-radius: var(--radius-lg);
  color: white;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
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
  padding: var(--spacing-1);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  font-size: var(--text-xs);
  flex-shrink: 0;
  transition: color var(--duration-200);
}

.kb-optin-dismiss:hover {
  color: var(--text-primary);
}

/* Issue #3436: Per-project sub-tab bar */
.project-sub-tabs-container {
  margin-top: var(--spacing-6);
  border-top: 1px solid var(--border-default);
}

.project-sub-tabs {
  display: flex;
  gap: var(--spacing-0-5);
  padding: var(--spacing-0) var(--spacing-0) var(--spacing-0) var(--spacing-0);
  overflow-x: auto;
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-secondary);
}

.project-sub-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2-5) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: all var(--duration-150) var(--ease-in-out);
  position: relative;
  top: 1px;
  white-space: nowrap;
}

.project-sub-tab:hover {
  color: var(--text-primary);
  background-color: var(--bg-tertiary);
}

.project-sub-tab-active {
  color: var(--color-info);
  border-bottom-color: var(--color-info);
  background-color: transparent;
}

.project-sub-tab-active:hover {
  color: var(--color-info);
  background-color: var(--color-info-bg);
}

.sub-tab-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.project-sub-tab-view {
  margin-top: var(--spacing-4);
}
</style>
