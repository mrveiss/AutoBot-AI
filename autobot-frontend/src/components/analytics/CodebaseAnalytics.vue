<template>
  <div class="codebase-analytics">
    <!-- Header Controls -->
    <div class="analytics-header">
      <div class="header-content">
        <h2><i class="fas fa-code"></i> {{ $t('analytics.codebase.title') }}</h2>
        <div class="header-controls">
          <router-link :to="{ name: 'analytics-codebase' }" class="btn-back">
            <i class="fas fa-arrow-left"></i>
            {{ $t('analytics.codebase.buttons.backToProjects') }}
          </router-link>

          <button @click="indexCodebase" :disabled="analyzing" class="btn-primary">
            <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-database'"></i>
            {{ analyzing ? $t('analytics.codebase.buttons.indexing') : $t('analytics.codebase.buttons.indexCodebase') }}
          </button>
          <button
            v-if="analyzing || scanRunner.running.value"
            @click="handleStop"
            class="btn-cancel"
          >
            <i class="fas fa-stop-circle"></i>
            {{ $t('analytics.codebase.actions.stop') }}
          </button>
          <button @click="runFullAnalysis" :disabled="analyzing || (!rootPath && !selectedSource)" class="btn-secondary">
            <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-chart-bar'"></i>
            {{ analyzing ? $t('analytics.codebase.buttons.analyzing') : $t('analytics.codebase.buttons.analyzeAll') }}
          </button>

          <!-- Enhanced Debug Controls -->
          <div class="debug-controls" style="margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
            <button @click="getDeclarationsData" class="btn-debug btn-debug-success">{{ $t('analytics.codebase.buttons.testDeclarations') }}</button>
            <button @click="getDuplicatesData" class="btn-debug btn-debug-warning">{{ $t('analytics.codebase.buttons.testDuplicates') }}</button>
            <button @click="getHardcodesData" class="btn-debug btn-debug-error">{{ $t('analytics.codebase.buttons.testHardcodes') }}</button>
            <button @click="testNpuConnection" class="btn-debug btn-debug-purple">{{ $t('analytics.codebase.buttons.testNpu') }}</button>
            <button @click="testDataState" class="btn-debug btn-debug-info">{{ $t('analytics.codebase.buttons.debugState') }}</button>
            <button @click="resetState" class="btn-debug btn-debug-orange">{{ $t('analytics.codebase.buttons.resetState') }}</button>
            <button @click="testAllEndpoints" class="btn-debug btn-debug-cyan">{{ $t('analytics.codebase.buttons.testAllApis') }}</button>
            <!-- Issue #527: API Endpoint Checker -->
            <button @click="getApiEndpointCoverage" :disabled="loadingApiEndpoints" class="btn-debug btn-debug-indigo">
              <i :class="loadingApiEndpoints ? 'fas fa-spinner fa-spin' : 'fas fa-plug'"></i>
              {{ loadingApiEndpoints ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.buttons.apiCoverage') }}
            </button>
            <!-- Code Intelligence / Anti-Pattern Detection -->
            <button @click="runCodeSmellAnalysis" :disabled="analyzingCodeSmells" class="btn-debug btn-debug-pink">
              <i :class="analyzingCodeSmells ? 'fas fa-spinner fa-spin' : 'fas fa-bug'"></i>
              {{ analyzingCodeSmells ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.buttons.codeSmells') }}
            </button>
            <button @click="getCodeHealthScore" :disabled="analyzingCodeSmells" class="btn-debug btn-debug-violet">
              <i class="fas fa-heartbeat"></i> {{ $t('analytics.codebase.buttons.healthScore') }}
            </button>
            <button @click="exportReport()" :disabled="exportingReport" class="btn-debug btn-debug-secondary">
              <i :class="exportingReport ? 'fas fa-spinner fa-spin' : 'fas fa-file-export'"></i>
              {{ exportingReport ? $t('analytics.codebase.buttons.exporting') : $t('analytics.codebase.buttons.exportReport') }}
            </button>
            <button @click="clearCache" :disabled="clearingCache" class="btn-debug btn-debug-brown">
              <i :class="clearingCache ? 'fas fa-spinner fa-spin' : 'fas fa-trash-alt'"></i>
              {{ clearingCache ? $t('analytics.codebase.buttons.clearing') : $t('analytics.codebase.buttons.clearCache') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Unified Operation Progress — Issues #1190, #1365, #1366 -->
    <!-- Single status bar covering indexing and code-smell operations; shows all available detail -->
    <div
      v-if="analyzing || analyzingCodeSmells || (progressStatus && progressStatus !== 'Ready' && progressStatus !== 'Ready (state reset)')"
      class="progress-container"
      :class="{
        'progress-container--idle': !analyzing && !analyzingCodeSmells,
        'code-smells-progress': analyzingCodeSmells && !analyzing
      }"
    >
      <div class="progress-header">
        <div class="progress-title">
          <i :class="
            (analyzing || analyzingCodeSmells)
              ? 'fas fa-spinner fa-spin'
              : progressStatus.includes('completed') || progressStatus.includes('complete')
                ? 'fas fa-check-circle'
                : progressStatus.includes('failed') || progressStatus.includes('cancelled')
                  ? 'fas fa-times-circle'
                  : 'fas fa-info-circle'
          "></i>
          {{ analyzing ? $t('analytics.codebase.progress.indexingInProgress') : analyzingCodeSmells ? codeSmellsProgressTitle : $t('analytics.codebase.progress.indexingStatus') }}
        </div>
        <div v-if="currentJobId && analyzing" class="job-id">{{ $t('analytics.codebase.progress.job') }}: {{ currentJobId.substring(0, 8) }}...</div>
      </div>

      <!-- Phase Progress (active indexing only) -->
      <div v-if="analyzing && jobPhases" class="phase-progress">
        <div
          v-for="phase in jobPhases.phase_list"
          :key="phase.id"
          class="phase-item"
          :class="{
            'phase-completed': phase.status === 'completed',
            'phase-running': phase.status === 'running',
            'phase-pending': phase.status === 'pending'
          }"
        >
          <i :class="getPhaseIcon(phase.status)"></i>
          <span>{{ phase.name }}</span>
        </div>
      </div>

      <!-- Progress Bar: determinate for indexing/idle, indeterminate for code-smells-only -->
      <div class="progress-bar">
        <div
          class="progress-fill"
          :class="{ indeterminate: analyzingCodeSmells && !analyzing }"
          :style="analyzingCodeSmells && !analyzing ? {} : { width: progressPercent + '%' }"
        ></div>
      </div>
      <div class="progress-status">{{ progressStatus }}</div>

      <!-- Batch Progress (active indexing only) -->
      <div v-if="analyzing && jobBatches && jobBatches.total_batches > 0" class="batch-progress">
        <div class="batch-header">
          <span class="batch-label">{{ $t('analytics.codebase.progress.batchProgress') }}:</span>
          <span class="batch-count">{{ jobBatches.completed_batches }} / {{ jobBatches.total_batches }}</span>
        </div>
        <div class="batch-bar">
          <div
            class="batch-fill"
            :style="{ width: (jobBatches.completed_batches / jobBatches.total_batches * 100) + '%' }"
          ></div>
        </div>
      </div>

      <!-- Live Stats (active indexing only) -->
      <div v-if="analyzing && jobStats" class="live-stats">
        <div class="stat-item">
          <i class="fas fa-file-code"></i>
          <span>{{ jobStats.files_scanned }} {{ $t('analytics.codebase.progress.files') }}</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ jobStats.problems_found }} {{ $t('analytics.codebase.progress.problems') }}</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-code"></i>
          <span>{{ jobStats.functions_found }} {{ $t('analytics.codebase.progress.functions') }}</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-cubes"></i>
          <span>{{ jobStats.classes_found }} {{ $t('analytics.codebase.progress.classes') }}</span>
        </div>
        <div class="stat-item" v-if="jobStats.items_stored > 0">
          <i class="fas fa-database"></i>
          <span>{{ jobStats.items_stored }} {{ $t('analytics.codebase.progress.stored') }}</span>
        </div>
      </div>
    </div>

    <!-- Scan Runner Progress (#1418) -->
    <div v-if="scanRunner.running.value || scanRunner.results.value.length > 0" class="scan-runner-progress">
      <div class="scan-runner-header">
        <span class="scan-runner-title">
          <i :class="scanRunner.running.value ? 'fas fa-spinner fa-spin' : 'fas fa-check-circle'"></i>
          {{ $t('analytics.codebase.scanRunner.title') }}
        </span>
        <span class="scan-runner-count">
          {{ scanRunner.completedCount.value }} / {{ scanRunner.totalCount.value }}
        </span>
      </div>
      <div class="mini-progress">
        <div class="mini-progress-bar" :style="{ width: scanRunner.progress.value + '%' }"></div>
      </div>
      <div class="scan-runner-items">
        <div
          v-for="result in scanRunner.results.value"
          :key="result.id"
          class="scan-runner-item"
          :class="'scan-' + result.status"
        >
          <i :class="{
            'fas fa-spinner fa-spin': result.status === 'running',
            'fas fa-check': result.status === 'completed',
            'fas fa-times': result.status === 'failed',
            'fas fa-forward': result.status === 'skipped',
            'fas fa-clock': result.status === 'pending',
          }"></i>
          <span class="scan-label">{{ result.label }}</span>
          <span v-if="result.durationMs != null" class="scan-duration">{{ result.durationMs }}ms</span>
          <span v-if="result.error" class="scan-error">{{ result.error }}</span>
        </div>
      </div>
    </div>

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

      <!-- Codebase Statistics -->
      <div class="stats-section">
        <h3>
          <i class="fas fa-chart-pie"></i> {{ $t('analytics.codebase.stats.title') }}
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons">
            <button @click="exportSection('statistics', 'md')" class="export-btn" :disabled="!codebaseStats" :title="$t('analytics.codebase.actions.exportMarkdown')">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('statistics', 'json')" class="export-btn" :disabled="!codebaseStats" :title="$t('analytics.codebase.actions.exportJson')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>
        <div v-if="codebaseStats" class="stats-grid">
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
            <div class="stat-label">{{ $t('analytics.codebase.stats.totalFiles') }}</div>
          </BasePanel>
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_lines || 0 }}</div>
            <div class="stat-label">{{ $t('analytics.codebase.stats.linesOfCode') }}</div>
          </BasePanel>
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_functions || 0 }}</div>
            <div class="stat-label">{{ $t('analytics.codebase.stats.functions') }}</div>
          </BasePanel>
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_classes || 0 }}</div>
            <div class="stat-label">{{ $t('analytics.codebase.stats.classes') }}</div>
          </BasePanel>
        </div>
        <EmptyState
          v-else
          icon="fas fa-chart-bar"
          :message="$t('analytics.codebase.stats.noData')"
        />
      </div>

      <!-- Analytics Charts Section -->
      <div class="charts-section">
        <div class="section-header">
          <h3><i class="fas fa-chart-bar"></i> {{ $t('analytics.codebase.problems.title') }}</h3>
          <div class="section-header-actions">
            <button @click="loadUnifiedReport" class="refresh-btn" :disabled="unifiedReportLoading" :title="$t('analytics.codebase.problems.loadReport')">
              <i :class="unifiedReportLoading ? 'fas fa-spinner fa-spin' : 'fas fa-layer-group'"></i>
            </button>
            <button @click="loadChartData" class="refresh-btn" :disabled="chartDataLoading" :title="$t('analytics.codebase.actions.refreshCharts')">
              <i :class="chartDataLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
            </button>
          </div>
        </div>

        <!-- Category Filter Tabs -->
        <div class="category-tabs" v-if="availableCategories.length > 0 || chartData">
          <button
            @click="selectedCategory = 'all'"
            class="category-tab"
            :class="{ active: selectedCategory === 'all' }"
          >
            <i class="fas fa-th-large"></i>
            {{ $t('analytics.codebase.problems.allIssues') }}
            <span class="tab-count" v-if="chartData?.summary?.total_problems">
              {{ chartData.summary.total_problems.toLocaleString() }}
            </span>
          </button>
          <button
            v-for="cat in availableCategories"
            :key="cat.id"
            @click="selectedCategory = cat.id"
            class="category-tab"
            :class="{ active: selectedCategory === cat.id }"
          >
            <i :class="getCategoryIcon(cat.id)"></i>
            {{ cat.name }}
            <span class="tab-count">{{ cat.count }}</span>
          </button>
        </div>

        <!-- Unified Report Error -->
        <div v-if="unifiedReportError" class="charts-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ unifiedReportError }}</span>
          <button @click="loadUnifiedReport" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <div v-if="chartDataLoading" class="charts-loading">
          <i class="fas fa-spinner fa-spin"></i>
          <span>{{ $t('analytics.codebase.problems.loadingChartData') }}</span>
        </div>

        <div v-else-if="chartDataError" class="charts-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ chartDataError }}</span>
          <button @click="loadChartData" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <div v-else-if="chartData" class="charts-grid">
          <!-- Summary Stats -->
          <div v-if="chartData.summary" class="chart-summary">
            <div class="summary-stat">
              <span class="summary-value">{{ chartData.summary.total_problems?.toLocaleString() || 0 }}</span>
              <span class="summary-label">{{ $t('analytics.codebase.problems.totalProblems') }}</span>
            </div>
            <div class="summary-stat">
              <span class="summary-value">{{ chartData.summary.unique_problem_types || 0 }}</span>
              <span class="summary-label">{{ $t('analytics.codebase.problems.problemTypes') }}</span>
            </div>
            <div class="summary-stat">
              <span class="summary-value">{{ chartData.summary.files_with_problems || 0 }}</span>
              <span class="summary-label">{{ $t('analytics.codebase.problems.filesAffected') }}</span>
            </div>
            <div class="summary-stat race-highlight">
              <span class="summary-value">{{ chartData.summary.race_condition_count || 0 }}</span>
              <span class="summary-label">{{ $t('analytics.codebase.problems.raceConditions') }}</span>
            </div>
          </div>

          <!-- Charts Row 1: Problem Types + Severity -->
          <div class="charts-row">
            <ProblemTypesChart
              v-if="filteredChartData?.problem_types && filteredChartData.problem_types.length > 0"
              :data="filteredChartData.problem_types"
              :title="selectedCategory === 'all' ? 'Problem Types Distribution' : `${selectedCategory.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())} Issues`"
              :height="320"
              class="chart-item"
            />
            <div v-else class="chart-empty-slot">
              <EmptyState icon="fas fa-chart-pie" :message="selectedCategory === 'all' ? 'No problem type data' : `No issues in ${selectedCategory.replace(/_/g, ' ')} category`" />
            </div>
            <SeverityBarChart
              v-if="chartData.severity_counts && chartData.severity_counts.length > 0"
              :data="chartData.severity_counts"
              :title="$t('analytics.codebase.charts.problemsBySeverity')"
              :height="320"
              class="chart-item"
            />
            <div v-else class="chart-empty-slot">
              <EmptyState icon="fas fa-signal" message="No severity data" />
            </div>
          </div>

          <!-- Charts Row 2: Race Conditions + Top Files -->
          <div class="charts-row">
            <RaceConditionsDonut
              v-if="chartData.race_conditions && chartData.race_conditions.length > 0"
              :data="chartData.race_conditions"
              :title="$t('analytics.codebase.charts.raceConditionsByCategory')"
              :height="320"
              class="chart-item"
            />
            <div v-else class="chart-empty-slot">
              <EmptyState icon="fas fa-exclamation-circle" message="No race condition data" />
            </div>
            <TopFilesChart
              v-if="chartData.top_files && chartData.top_files.length > 0"
              :data="chartData.top_files"
              :title="$t('analytics.codebase.charts.topFilesWithProblems')"
              :height="400"
              :maxFiles="10"
              class="chart-item"
            />
            <div v-else class="chart-empty-slot">
              <EmptyState icon="fas fa-file-code" message="No file data" />
            </div>
          </div>
        </div>

        <EmptyState
          v-else
          icon="fas fa-chart-area"
          :message="$t('analytics.codebase.problems.noChartData')"
        >
          <template #actions>
            <button @click="indexCodebase" class="btn-primary" :disabled="analyzing">
              <i class="fas fa-database"></i> {{ $t('analytics.codebase.buttons.indexCodebase') }}
            </button>
          </template>
        </EmptyState>
      </div>

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

      <!-- Problems Report - Grouped by Type and Severity -->
      <div class="problems-section analytics-section">
        <h3>
          <i class="fas fa-exclamation-triangle"></i> {{ $t('analytics.codebase.problems.codeProblems') }}
          <span v-if="problemsReport && problemsReport.length > 0" class="total-count">
            ({{ problemsReport.length.toLocaleString() }} total)
          </span>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons">
            <button @click="exportSection('problems', 'md')" class="export-btn" :disabled="!problemsReport || problemsReport.length === 0" :title="$t('analytics.codebase.actions.exportMarkdown')">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('problems', 'json')" class="export-btn" :disabled="!problemsReport || problemsReport.length === 0" :title="$t('analytics.codebase.actions.exportJson')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>
        <div v-if="problemsReport && problemsReport.length > 0" class="section-content">
          <!-- Severity Summary Cards -->
          <div class="summary-cards">
            <div class="summary-card total">
              <div class="summary-value">{{ problemsReport.length.toLocaleString() }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.stats.total') }}</div>
            </div>
            <div
              v-for="(problems, severity) in problemsBySeverity"
              :key="severity"
              class="summary-card"
              :class="severity"
            >
              <div class="summary-value">{{ problems.length.toLocaleString() }}</div>
              <div class="summary-label">{{ severity.charAt(0).toUpperCase() + severity.slice(1) }}</div>
            </div>
          </div>

          <!-- Grouped by Type (Accordion) -->
          <div class="accordion-groups">
            <div
              v-for="(typeData, type) in problemsByType"
              :key="type"
              class="accordion-group"
            >
              <div
                class="accordion-header"
                @click="toggleProblemType(type)"
              >
                <div class="header-info">
                  <i :class="expandedProblemTypes[type] ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ formatProblemType(type) }}</span>
                  <span class="header-count">({{ typeData.problems.length.toLocaleString() }})</span>
                </div>
                <div class="header-badges">
                  <span v-if="typeData.severityCounts.critical" class="severity-badge critical">
                    {{ typeData.severityCounts.critical }} {{ $t('analytics.codebase.severity.critical') }}
                  </span>
                  <span v-if="typeData.severityCounts.high" class="severity-badge high">
                    {{ typeData.severityCounts.high }} {{ $t('analytics.codebase.severity.high') }}
                  </span>
                  <span v-if="typeData.severityCounts.medium" class="severity-badge medium">
                    {{ typeData.severityCounts.medium }} {{ $t('analytics.codebase.severity.medium') }}
                  </span>
                  <span v-if="typeData.severityCounts.low" class="severity-badge low">
                    {{ typeData.severityCounts.low }} {{ $t('analytics.codebase.severity.low') }}
                  </span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedProblemTypes[type]" class="accordion-items">
                  <div
                    v-for="(problem, index) in typeData.problems.slice(0, 20)"
                    :key="index"
                    class="list-item"
                    :class="getItemSeverityClass(problem.severity)"
                  >
                    <div class="item-header">
                      <span class="item-severity" :class="problem.severity?.toLowerCase()">
                        {{ problem.severity || 'unknown' }}
                      </span>
                    </div>
                    <div class="item-description">{{ problem.description }}</div>
                    <div class="item-location">📁 {{ problem.file_path }}{{ problem.line_number ? ':' + problem.line_number : '' }}</div>
                    <div v-if="problem.suggestion" class="item-suggestion">💡 {{ problem.suggestion }}</div>
                  </div>
                  <div v-if="typeData.problems.length > 20" class="show-more">
                    <span class="muted">Showing 20 of {{ typeData.problems.length.toLocaleString() }} {{ formatProblemType(type) }} issues</span>
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-check-circle"
          :message="$t('analytics.codebase.problems.noProblems')"
          variant="success"
        />
      </div>

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

      <!-- Issue #527: API Endpoint Checker Section -->
      <div class="api-endpoints-section analytics-section">
        <h3>
          <i class="fas fa-plug"></i> {{ $t('analytics.codebase.apiCoverage.title') }}
          <span v-if="apiEndpointAnalysis" class="total-count">
            ({{ apiEndpointAnalysis.coverage_percentage?.toFixed(1) || 0 }}% coverage)
          </span>
          <button @click="getApiEndpointCoverage" :disabled="loadingApiEndpoints" class="refresh-btn" style="margin-left: 10px;">
            <i :class="loadingApiEndpoints ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons">
            <button @click="exportSection('api-endpoints', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')" :disabled="!apiEndpointAnalysis">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('api-endpoints', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')" :disabled="!apiEndpointAnalysis">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>

        <!-- Loading State -->
        <div v-if="loadingApiEndpoints" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.apiCoverage.scanning') }}
        </div>

        <!-- Error State -->
        <div v-else-if="apiEndpointsError" class="error-state">
          <i class="fas fa-exclamation-triangle"></i> {{ apiEndpointsError }}
          <button @click="getApiEndpointCoverage" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <!-- Analysis Results -->
        <div v-else-if="apiEndpointAnalysis" class="section-content">
          <!-- Summary Cards -->
          <div class="summary-cards">
            <div class="summary-card total">
              <div class="summary-value">{{ apiEndpointAnalysis.backend_endpoints || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.backendEndpoints') }}</div>
            </div>
            <div class="summary-card info">
              <div class="summary-value">{{ apiEndpointAnalysis.frontend_calls || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.frontendCalls') }}</div>
            </div>
            <div class="summary-card success">
              <div class="summary-value">{{ apiEndpointAnalysis.used_endpoints || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.usedEndpoints') }}</div>
            </div>
            <div class="summary-card warning">
              <div class="summary-value">{{ apiEndpointAnalysis.orphaned_endpoints || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.orphaned') }}</div>
            </div>
            <div class="summary-card critical">
              <div class="summary-value">{{ apiEndpointAnalysis.missing_endpoints || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.apiCoverage.missing') }}</div>
            </div>
          </div>

          <!-- Coverage Progress Bar -->
          <div class="coverage-bar-container">
            <div class="coverage-label">
              <span>{{ $t('analytics.codebase.apiCoverage.coverageLabel') }}</span>
              <span class="coverage-value" :class="getCoverageClass(apiEndpointAnalysis.coverage_percentage)">
                {{ apiEndpointAnalysis.coverage_percentage?.toFixed(1) || 0 }}%
              </span>
            </div>
            <div class="coverage-bar">
              <div
                class="coverage-fill"
                :style="{ width: (apiEndpointAnalysis.coverage_percentage || 0) + '%' }"
                :class="getCoverageClass(apiEndpointAnalysis.coverage_percentage)"
              ></div>
            </div>
          </div>

          <!-- Accordion Groups -->
          <div class="accordion-groups">
            <!-- Orphaned Endpoints (defined but not called) -->
            <div v-if="apiEndpointAnalysis.orphaned?.length > 0" class="accordion-group">
              <div class="accordion-header warning" @click="expandedApiEndpointGroups.orphaned = !expandedApiEndpointGroups.orphaned">
                <div class="header-info">
                  <i :class="expandedApiEndpointGroups.orphaned ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.apiCoverage.orphanedEndpoints') }}</span>
                  <span class="header-count">({{ apiEndpointAnalysis.orphaned.length }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge warning">{{ $t('analytics.codebase.apiCoverage.unusedCode') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedApiEndpointGroups.orphaned" class="accordion-items">
                  <div v-for="(ep, index) in apiEndpointAnalysis.orphaned.slice(0, 30)" :key="'orphan-' + index" class="list-item item-warning">
                    <div class="item-header">
                      <span class="method-badge" :class="ep.method?.toLowerCase()">{{ ep.method }}</span>
                      <span class="item-path">{{ ep.path }}</span>
                    </div>
                    <div class="item-location">📁 {{ ep.file_path }}:{{ ep.line_number }}</div>
                  </div>
                  <div v-if="apiEndpointAnalysis.orphaned.length > 30" class="show-more">
                    <span class="muted">Showing 30 of {{ apiEndpointAnalysis.orphaned.length }} orphaned endpoints</span>
                  </div>
                </div>
              </transition>
            </div>

            <!-- Missing Endpoints (called but not defined) -->
            <div v-if="apiEndpointAnalysis.missing?.length > 0" class="accordion-group">
              <div class="accordion-header critical" @click="expandedApiEndpointGroups.missing = !expandedApiEndpointGroups.missing">
                <div class="header-info">
                  <i :class="expandedApiEndpointGroups.missing ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.apiCoverage.missingEndpoints') }}</span>
                  <span class="header-count">({{ apiEndpointAnalysis.missing.length }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge critical">{{ $t('analytics.codebase.apiCoverage.potentialBugs') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedApiEndpointGroups.missing" class="accordion-items">
                  <div v-for="(ep, index) in apiEndpointAnalysis.missing.slice(0, 30)" :key="'missing-' + index" class="list-item item-critical">
                    <div class="item-header">
                      <span class="method-badge" :class="ep.method?.toLowerCase()">{{ ep.method }}</span>
                      <span class="item-path">{{ ep.path }}</span>
                    </div>
                    <div class="item-location">📁 {{ ep.file_path }}:{{ ep.line_number }}</div>
                    <div v-if="ep.details" class="item-details">{{ ep.details }}</div>
                  </div>
                  <div v-if="apiEndpointAnalysis.missing.length > 30" class="show-more">
                    <span class="muted">Showing 30 of {{ apiEndpointAnalysis.missing.length }} missing endpoints</span>
                  </div>
                </div>
              </transition>
            </div>

            <!-- Used Endpoints (matched and working) -->
            <div v-if="(apiEndpointAnalysis.used?.length ?? 0) > 0" class="accordion-group">
              <div class="accordion-header success" @click="expandedApiEndpointGroups.used = !expandedApiEndpointGroups.used">
                <div class="header-info">
                  <i :class="expandedApiEndpointGroups.used ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.apiCoverage.usedEndpointsHeader') }}</span>
                  <span class="header-count">({{ apiEndpointAnalysis.used?.length ?? 0 }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge success">{{ $t('analytics.codebase.apiCoverage.active') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedApiEndpointGroups.used" class="accordion-items">
                  <div v-for="(usage, index) in apiEndpointAnalysis.used?.slice(0, 30)" :key="'used-' + index" class="list-item item-success">
                    <div class="item-header">
                      <span class="method-badge" :class="usage.endpoint?.method?.toLowerCase()">{{ usage.endpoint?.method }}</span>
                      <span class="item-path">{{ usage.endpoint?.path }}</span>
                      <span class="call-count-badge">{{ usage.call_count }} calls</span>
                    </div>
                    <div class="item-location">📁 {{ usage.endpoint?.file_path }}:{{ usage.endpoint?.line_number }}</div>
                  </div>
                  <div v-if="(apiEndpointAnalysis.used?.length ?? 0) > 30" class="show-more">
                    <span class="muted">Showing 30 of {{ apiEndpointAnalysis.used?.length ?? 0 }} used endpoints</span>
                  </div>
                </div>
              </transition>
            </div>
          </div>

          <!-- Last Scan Timestamp -->
          <div v-if="apiEndpointAnalysis.scan_timestamp" class="scan-timestamp">
            <i class="fas fa-clock"></i> {{ $t('analytics.codebase.actions.lastScan') }}: {{ formatTimestamp(apiEndpointAnalysis.scan_timestamp) }}
          </div>
        </div>

        <!-- Empty State -->
        <EmptyState
          v-else
          icon="fas fa-plug"
          :message="$t('analytics.codebase.apiCoverage.noData')"
        />
      </div>

      <!-- Issue #244: Cross-Language Pattern Analysis Section -->
      <div class="cross-language-section analytics-section">
        <h3>
          <i class="fas fa-language"></i> {{ $t('analytics.codebase.crossLanguage.title') }}
          <span v-if="crossLanguageAnalysis" class="total-count">
            ({{ crossLanguageAnalysis.total_patterns }} patterns)
          </span>
          <button @click="getCrossLanguageAnalysis" :disabled="loadingCrossLanguage" class="refresh-btn" style="margin-left: 10px;">
            <i :class="loadingCrossLanguage ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <button @click="runCrossLanguageAnalysis" :disabled="loadingCrossLanguage" class="btn-scan" style="margin-left: 5px;">
            <i :class="loadingCrossLanguage ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
            {{ loadingCrossLanguage ? $t('analytics.codebase.buttons.scanning') : $t('analytics.codebase.crossLanguage.fullScan') }}
          </button>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons">
            <button @click="exportSection('cross-language', 'md')" class="export-btn" :disabled="!crossLanguageAnalysis" :title="$t('analytics.codebase.actions.exportMarkdown')">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('cross-language', 'json')" class="export-btn" :disabled="!crossLanguageAnalysis" :title="$t('analytics.codebase.actions.exportJson')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>

        <!-- Loading State -->
        <div v-if="loadingCrossLanguage" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.crossLanguage.analyzing') }}
        </div>

        <!-- Error State -->
        <div v-else-if="crossLanguageError" class="error-state">
          <i class="fas fa-exclamation-triangle"></i> {{ crossLanguageError }}
          <button @click="getCrossLanguageAnalysis" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <!-- Analysis Results -->
        <div v-else-if="crossLanguageAnalysis" class="section-content">
          <!-- Summary Cards -->
          <div class="summary-cards">
            <div class="summary-card total">
              <div class="summary-value">{{ crossLanguageAnalysis.python_files_analyzed + crossLanguageAnalysis.typescript_files_analyzed + crossLanguageAnalysis.vue_files_analyzed }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.crossLanguage.filesAnalyzed') }}</div>
            </div>
            <div class="summary-card critical">
              <div class="summary-value">{{ crossLanguageAnalysis.critical_issues }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.severity.critical') }}</div>
            </div>
            <div class="summary-card warning">
              <div class="summary-value">{{ crossLanguageAnalysis.high_issues }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.severity.high') }}</div>
            </div>
            <div class="summary-card info">
              <div class="summary-value">{{ crossLanguageAnalysis.dto_mismatches?.length || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.crossLanguage.dtoMismatches') }}</div>
            </div>
            <div class="summary-card success">
              <div class="summary-value">{{ crossLanguageAnalysis.pattern_matches?.length || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.crossLanguage.semanticMatches') }}</div>
            </div>
          </div>

          <!-- Language Breakdown -->
          <div class="language-breakdown">
            <span class="language-badge python">
              <i class="fab fa-python"></i> {{ crossLanguageAnalysis.python_files_analyzed }} Python
            </span>
            <span class="language-badge typescript">
              <i class="fab fa-js-square"></i> {{ crossLanguageAnalysis.typescript_files_analyzed }} TypeScript
            </span>
            <span class="language-badge vue">
              <i class="fab fa-vuejs"></i> {{ crossLanguageAnalysis.vue_files_analyzed }} Vue
            </span>
          </div>

          <!-- Accordion Groups -->
          <div class="accordion-groups">
            <!-- DTO Mismatches -->
            <div v-if="crossLanguageAnalysis.dto_mismatches?.length > 0" class="accordion-group">
              <div class="accordion-header critical" @click="expandedCrossLanguageGroups.dtoMismatches = !expandedCrossLanguageGroups.dtoMismatches">
                <div class="header-info">
                  <i :class="expandedCrossLanguageGroups.dtoMismatches ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.crossLanguage.dtoTypeMismatches') }}</span>
                  <span class="header-count">({{ crossLanguageAnalysis.dto_mismatches.length }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge critical">{{ $t('analytics.codebase.crossLanguage.typeSafety') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedCrossLanguageGroups.dtoMismatches" class="accordion-items">
                  <div v-for="(m, index) in crossLanguageAnalysis.dto_mismatches.slice(0, 20)" :key="'dto-' + index" class="list-item item-critical">
                    <div class="item-header">
                      <span class="type-badge">{{ m.mismatch_type }}</span>
                      <span class="item-name">{{ m.backend_type }} → {{ m.frontend_type || 'Unknown' }}</span>
                    </div>
                    <div class="item-field">Field: <code>{{ m.field_name }}</code></div>
                    <div v-if="m.recommendation" class="item-recommendation">💡 {{ m.recommendation }}</div>
                  </div>
                  <div v-if="crossLanguageAnalysis.dto_mismatches.length > 20" class="show-more">
                    <span class="muted">Showing 20 of {{ crossLanguageAnalysis.dto_mismatches.length }} DTO mismatches</span>
                  </div>
                </div>
              </transition>
            </div>

            <!-- API Contract Mismatches -->
            <div v-if="crossLanguageAnalysis.api_contract_mismatches?.length > 0" class="accordion-group">
              <div class="accordion-header warning" @click="expandedCrossLanguageGroups.apiMismatches = !expandedCrossLanguageGroups.apiMismatches">
                <div class="header-info">
                  <i :class="expandedCrossLanguageGroups.apiMismatches ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.crossLanguage.apiContractIssues') }}</span>
                  <span class="header-count">({{ crossLanguageAnalysis.api_contract_mismatches.length }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge warning">{{ $t('analytics.codebase.crossLanguage.contract') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedCrossLanguageGroups.apiMismatches" class="accordion-items">
                  <div v-for="(m, index) in crossLanguageAnalysis.api_contract_mismatches.slice(0, 20)" :key="'api-' + index"
                       :class="['list-item', m.mismatch_type === 'missing_endpoint' ? 'item-critical' : 'item-warning']">
                    <div class="item-header">
                      <span class="method-badge" :class="m.http_method?.toLowerCase()">{{ m.http_method }}</span>
                      <span class="item-path">{{ m.endpoint_path }}</span>
                      <span :class="['type-badge', m.mismatch_type === 'missing_endpoint' ? 'missing' : 'orphaned']">
                        {{ m.mismatch_type === 'missing_endpoint' ? 'Missing' : 'Orphaned' }}
                      </span>
                    </div>
                    <div v-if="m.details" class="item-details">{{ m.details }}</div>
                  </div>
                  <div v-if="crossLanguageAnalysis.api_contract_mismatches.length > 20" class="show-more">
                    <span class="muted">Showing 20 of {{ crossLanguageAnalysis.api_contract_mismatches.length }} API issues</span>
                  </div>
                </div>
              </transition>
            </div>

            <!-- Validation Duplications -->
            <div v-if="crossLanguageAnalysis.validation_duplications?.length > 0" class="accordion-group">
              <div class="accordion-header info" @click="expandedCrossLanguageGroups.validationDups = !expandedCrossLanguageGroups.validationDups">
                <div class="header-info">
                  <i :class="expandedCrossLanguageGroups.validationDups ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.crossLanguage.validationDuplications') }}</span>
                  <span class="header-count">({{ crossLanguageAnalysis.validation_duplications.length }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge info">{{ $t('analytics.codebase.crossLanguage.dryViolation') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedCrossLanguageGroups.validationDups" class="accordion-items">
                  <div v-for="(v, index) in crossLanguageAnalysis.validation_duplications.slice(0, 15)" :key="'val-' + index" class="list-item item-info">
                    <div class="item-header">
                      <span class="validation-type-badge">{{ v.validation_type }}</span>
                      <span class="similarity-score">{{ (v.similarity_score * 100).toFixed(0) }}% similar</span>
                    </div>
                    <div class="item-locations">
                      <span v-if="v.python_location" class="location python">
                        🐍 {{ v.python_location.file_path }}:{{ v.python_location.line_start }}
                      </span>
                      <span v-if="v.typescript_location" class="location typescript">
                        📜 {{ v.typescript_location.file_path }}:{{ v.typescript_location.line_start }}
                      </span>
                    </div>
                    <div v-if="v.recommendation" class="item-recommendation">💡 {{ v.recommendation }}</div>
                  </div>
                  <div v-if="crossLanguageAnalysis.validation_duplications.length > 15" class="show-more">
                    <span class="muted">Showing 15 of {{ crossLanguageAnalysis.validation_duplications.length }} duplications</span>
                  </div>
                </div>
              </transition>
            </div>

            <!-- Semantic Pattern Matches -->
            <div v-if="crossLanguageAnalysis.pattern_matches?.length > 0" class="accordion-group">
              <div class="accordion-header success" @click="expandedCrossLanguageGroups.semanticMatches = !expandedCrossLanguageGroups.semanticMatches">
                <div class="header-info">
                  <i :class="expandedCrossLanguageGroups.semanticMatches ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
                  <span class="header-name">{{ $t('analytics.codebase.crossLanguage.semanticPatternMatches') }}</span>
                  <span class="header-count">({{ crossLanguageAnalysis.pattern_matches.length }})</span>
                </div>
                <div class="header-badges">
                  <span class="severity-badge success">{{ $t('analytics.codebase.crossLanguage.aiDetected') }}</span>
                </div>
              </div>
              <transition name="accordion">
                <div v-if="expandedCrossLanguageGroups.semanticMatches" class="accordion-items">
                  <div v-for="(m, index) in crossLanguageAnalysis.pattern_matches.slice(0, 15)" :key="'match-' + index" class="list-item item-success">
                    <div class="item-header">
                      <span class="similarity-score highlight">{{ (m.similarity_score * 100).toFixed(0) }}% match</span>
                      <span class="match-type">{{ m.match_type }}</span>
                    </div>
                    <div class="item-locations">
                      <span v-if="m.source_location" class="location">
                        📁 {{ m.source_location.file_path }}:{{ m.source_location.line_start }}
                      </span>
                      <span class="arrow">↔</span>
                      <span v-if="m.target_location" class="location">
                        📁 {{ m.target_location.file_path }}:{{ m.target_location.line_start }}
                      </span>
                    </div>
                  </div>
                  <div v-if="crossLanguageAnalysis.pattern_matches.length > 15" class="show-more">
                    <span class="muted">Showing 15 of {{ crossLanguageAnalysis.pattern_matches.length }} matches</span>
                  </div>
                </div>
              </transition>
            </div>
          </div>

          <!-- Analysis Timestamp -->
          <div v-if="crossLanguageAnalysis.scan_timestamp" class="scan-timestamp">
            <i class="fas fa-clock"></i> {{ $t('analytics.codebase.actions.lastScan') }}: {{ formatTimestamp(crossLanguageAnalysis.scan_timestamp) }}
            <span v-if="crossLanguageAnalysis.analysis_time_ms" class="analysis-time">
              ({{ (crossLanguageAnalysis.analysis_time_ms / 1000).toFixed(1) }}s)
            </span>
          </div>
        </div>

        <!-- Empty State -->
        <EmptyState
          v-else
          icon="fas fa-language"
          :message="$t('analytics.codebase.crossLanguage.noData')"
        />
      </div>

      <!-- Issue #208: Code Pattern Analysis Section -->
      <PatternAnalysis
        ref="patternAnalysisRef"
        :root-path="rootPath"
        :auto-load="true"
        @analysis-complete="onPatternAnalysisComplete"
        @error="onPatternAnalysisError"
      />

      <!-- Issue #538: Config Duplicates Detection Section -->
      <div class="config-duplicates-section analytics-section">
        <h3>
          <i class="fas fa-clone"></i> {{ $t('analytics.codebase.duplicates.configTitle') }}
          <span v-if="configDuplicatesAnalysis" class="total-count">
            ({{ configDuplicatesAnalysis.duplicates_found }} duplicates)
          </span>
          <button @click="loadConfigDuplicates" :disabled="loadingConfigDuplicates" class="refresh-btn" style="margin-left: 10px;">
            <i :class="loadingConfigDuplicates ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons">
            <button @click="exportSection('config-duplicates', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')" :disabled="!configDuplicatesAnalysis">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('config-duplicates', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')" :disabled="!configDuplicatesAnalysis">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>

        <!-- Loading State -->
        <div v-if="loadingConfigDuplicates" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.duplicates.scanningConfig') }}
        </div>

        <!-- Error State -->
        <div v-else-if="configDuplicatesError" class="error-state">
          <i class="fas fa-exclamation-triangle"></i> {{ configDuplicatesError }}
          <button @click="loadConfigDuplicates" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <!-- Analysis Results -->
        <div v-else-if="configDuplicatesAnalysis && configDuplicatesAnalysis.duplicates_found > 0" class="section-content">
          <!-- Summary Cards -->
          <div class="summary-cards">
            <div class="summary-card warning">
              <div class="summary-value">{{ configDuplicatesAnalysis.duplicates_found }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.duplicates.duplicateValues') }}</div>
            </div>
            <div class="summary-card info">
              <div class="summary-value">{{ configDuplicatesAnalysis.duplicates?.length || 0 }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.duplicates.uniquePatterns') }}</div>
            </div>
          </div>

          <!-- Duplicates List -->
          <div class="duplicates-list">
            <div
              v-for="(dup, index) in configDuplicatesAnalysis.duplicates?.slice(0, 20)"
              :key="'config-dup-' + index"
              class="list-item item-warning"
            >
              <div class="item-header">
                <span class="config-value-badge">{{ truncateValue(dup.value) }}</span>
                <span class="location-count">{{ dup.locations?.length || 0 }} locations</span>
              </div>
              <div class="item-locations">
                <div v-for="(loc, locIdx) in dup.locations?.slice(0, 5)" :key="'loc-' + locIdx" class="location-item">
                  📁 {{ loc.file }}:{{ loc.line }}
                </div>
                <div v-if="dup.locations?.length > 5" class="more-locations">
                  ... and {{ dup.locations.length - 5 }} more locations
                </div>
              </div>
            </div>
            <div v-if="configDuplicatesAnalysis.duplicates?.length > 20" class="show-more">
              <span class="muted">Showing 20 of {{ configDuplicatesAnalysis.duplicates.length }} duplicate patterns</span>
            </div>
          </div>

          <!-- Recommendation -->
          <div class="recommendation-box">
            <i class="fas fa-lightbulb"></i>
            <span>{{ $t('analytics.codebase.duplicates.recommendation') }}</span>
          </div>
        </div>

        <!-- No Duplicates Found -->
        <div v-else-if="configDuplicatesAnalysis && configDuplicatesAnalysis.duplicates_found === 0" class="success-state">
          <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.duplicates.noDuplicatesFound') }}
        </div>

        <!-- Empty State -->
        <EmptyState
          v-else
          icon="fas fa-clone"
          :message="$t('analytics.codebase.duplicates.noConfigData')"
        />
      </div>

      <!-- Issue #538: Bug Prediction Section - Enhanced with detailed findings -->
      <div class="bug-prediction-section analytics-section">
        <h3>
          <i class="fas fa-bug"></i> {{ $t('analytics.codebase.bugPrediction.title') }}
          <span v-if="bugPredictionAnalysis" class="total-count">
            ({{ getAtRiskFilesCount() }} files need attention)
          </span>
          <button @click="loadBugPrediction" :disabled="loadingBugPrediction" class="refresh-btn" style="margin-left: 10px;">
            <i :class="loadingBugPrediction ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons" v-if="bugPredictionAnalysis">
            <button @click="exportSection('bug-prediction', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('bug-prediction', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>

        <!-- Loading State (#1418: progress bar matching PatternAnalysis.vue) -->
        <div v-if="loadingBugPrediction" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          <span v-if="bugPredictionTask.taskStatus.value">
            {{ bugPredictionTask.taskStatus.value.current_step || $t('analytics.codebase.bugPrediction.analyzing') }}
          </span>
          <span v-else>{{ $t('analytics.codebase.bugPrediction.analyzing') }}</span>
          <div v-if="bugPredictionTask.taskStatus.value?.progress" class="mini-progress">
            <div class="mini-progress-bar" :style="{ width: bugPredictionTask.taskStatus.value.progress + '%' }"></div>
          </div>
        </div>

        <!-- Interrupted State (#1418) -->
        <div v-if="!loadingBugPrediction && bugPredictionTask.wasInterrupted.value" class="interrupted-state">
          <i class="fas fa-info-circle"></i>
          {{ $t('analytics.codebase.bugPrediction.interrupted') }}
          <button @click="loadBugPrediction" class="rerun-btn">
            <i class="fas fa-redo"></i> {{ $t('analytics.codebase.actions.retry') }}
          </button>
        </div>

        <!-- Error State -->
        <div v-else-if="!loadingBugPrediction && bugPredictionError" class="error-state">
          <i class="fas fa-exclamation-triangle"></i> {{ bugPredictionError }}
          <button @click="loadBugPrediction" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <!-- Analysis Results -->
        <div v-else-if="bugPredictionAnalysis && bugPredictionAnalysis.files.length > 0" class="section-content">
          <!-- Summary Cards -->
          <div class="summary-cards">
            <div class="summary-card total">
              <div class="summary-value">{{ bugPredictionAnalysis.analyzed_files }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.filesAnalyzed') }}</div>
            </div>
            <div class="summary-card critical" :class="{ clickable: bugPredictionAnalysis.high_risk_count > 0 }" @click="bugPredictionAnalysis.high_risk_count > 0 && toggleBugRiskFilter('high')">
              <div class="summary-value">{{ bugPredictionAnalysis.high_risk_count }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.highRisk') }}</div>
            </div>
            <div class="summary-card warning clickable" @click="toggleBugRiskFilter('medium')">
              <div class="summary-value">{{ bugPredictionAnalysis.files.filter(f => f.risk_score >= 40 && f.risk_score < 60).length }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.mediumRisk') }}</div>
            </div>
            <div class="summary-card success clickable" @click="toggleBugRiskFilter('low')">
              <div class="summary-value">{{ bugPredictionAnalysis.files.filter(f => f.risk_score < 40).length }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.bugPrediction.lowRisk') }}</div>
            </div>
          </div>

          <!-- Top Risk Factors Summary -->
          <div v-if="getTopRiskFactors().length > 0" class="top-risk-factors-summary">
            <h4><i class="fas fa-exclamation-circle"></i> {{ $t('analytics.codebase.bugPrediction.topIssues') }}</h4>
            <div class="risk-factors-grid">
              <div v-for="factor in getTopRiskFactors()" :key="factor.name" class="risk-factor-card" :class="factor.severity">
                <div class="factor-icon">
                  <i :class="getRiskFactorIcon(factor.name)"></i>
                </div>
                <div class="factor-details">
                  <div class="factor-name">{{ formatFactorName(factor.name) }}</div>
                  <div class="factor-count">{{ factor.count }} files affected</div>
                  <div class="factor-description">{{ getRiskFactorDescription(factor.name) }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Risk Filter Tabs -->
          <div class="risk-filter-tabs">
            <button
              :class="{ active: bugRiskFilter === 'all' }"
              @click="bugRiskFilter = 'all'; bugRiskVisibleCount = BUG_RISK_PAGE_SIZE"
            >
              All ({{ bugPredictionAnalysis.files.length }})
            </button>
            <button
              :class="{ active: bugRiskFilter === 'high' }"
              @click="bugRiskFilter = 'high'; bugRiskVisibleCount = BUG_RISK_PAGE_SIZE"
              :disabled="bugPredictionAnalysis.high_risk_count === 0"
            >
              High ({{ bugPredictionAnalysis.high_risk_count }})
            </button>
            <button
              :class="{ active: bugRiskFilter === 'medium' }"
              @click="bugRiskFilter = 'medium'; bugRiskVisibleCount = BUG_RISK_PAGE_SIZE"
            >
              Medium ({{ bugPredictionAnalysis.files.filter(f => f.risk_score >= 40 && f.risk_score < 60).length }})
            </button>
            <button
              :class="{ active: bugRiskFilter === 'low' }"
              @click="bugRiskFilter = 'low'; bugRiskVisibleCount = BUG_RISK_PAGE_SIZE"
            >
              Low ({{ bugPredictionAnalysis.files.filter(f => f.risk_score < 40).length }})
            </button>
          </div>

          <!-- Files List with Detailed Info -->
          <div class="risk-files-list detailed">
            <h4>
              <i class="fas fa-file-code"></i>
              {{ bugRiskFilter === 'all' ? 'Analyzed Files' : `${bugRiskFilter.charAt(0).toUpperCase() + bugRiskFilter.slice(1)} Risk Files` }}
              <span class="file-count">({{ getFilteredBugRiskFiles().length }} files)</span>
            </h4>

            <div v-if="getFilteredBugRiskFiles().length === 0" class="no-files-message">
              <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.bugPrediction.noFilesInCategory') }}
            </div>

            <div
              v-for="(file, index) in getFilteredBugRiskFiles().slice(0, bugRiskVisibleCount)"
              :key="'risk-file-' + index"
              class="risk-file-item"
              :class="[getRiskClass(file.risk_score), { expanded: expandedBugRiskFiles.has(file.file_path) }]"
            >
              <!-- File Header (Always Visible) -->
              <div class="file-header" @click="toggleBugRiskFileExpand(file.file_path)">
                <div class="file-info">
                  <span class="risk-score-badge" :class="getRiskClass(file.risk_score)">
                    {{ file.risk_score.toFixed(0) }}
                  </span>
                  <span class="file-path">{{ file.file_path }}</span>
                  <span class="risk-level-tag" :class="file.risk_level">{{ file.risk_level }}</span>
                </div>
                <div class="expand-icon">
                  <i :class="expandedBugRiskFiles.has(file.file_path) ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
                </div>
              </div>

              <!-- Quick Risk Indicators (Always Visible) -->
              <div class="quick-risk-indicators">
                <span v-if="file.factors?.complexity >= 80" class="indicator high" :title="$t('analytics.codebase.risk.highComplexity')">
                  <i class="fas fa-project-diagram"></i> {{ $t('analytics.codebase.risk.complex') }}
                </span>
                <span v-if="file.factors?.change_frequency >= 80" class="indicator warning" :title="$t('analytics.codebase.risk.frequentlyChanged')">
                  <i class="fas fa-history"></i> {{ $t('analytics.codebase.risk.unstable') }}
                </span>
                <span v-if="file.factors?.file_size >= 70" class="indicator info" :title="$t('analytics.codebase.risk.largeFile')">
                  <i class="fas fa-file-alt"></i> {{ $t('analytics.codebase.risk.large') }}
                </span>
                <span v-if="file.factors?.bug_history > 0" class="indicator critical" :title="$t('analytics.codebase.risk.hasBugHistory')">
                  <i class="fas fa-bug"></i> {{ $t('analytics.codebase.risk.bugHistory') }}
                </span>
                <span v-if="file.factors?.test_coverage === 50" class="indicator muted" :title="$t('analytics.codebase.risk.noTestsDetected')">
                  <i class="fas fa-vial"></i> {{ $t('analytics.codebase.risk.noTests') }}
                </span>
              </div>

              <!-- Expanded Details -->
              <div v-if="expandedBugRiskFiles.has(file.file_path)" class="file-details">
                <!-- Risk Factors Breakdown -->
                <div class="detail-section">
                  <h5><i class="fas fa-chart-bar"></i> {{ $t('analytics.codebase.bugPrediction.riskFactorBreakdown') }}</h5>
                  <div class="factors-breakdown">
                    <div
                      v-for="(value, factor) in file.factors"
                      :key="factor"
                      class="factor-row"
                      :class="{ 'high-value': value >= 80, 'medium-value': value >= 50 && value < 80 }"
                    >
                      <div class="factor-label">
                        <i :class="getRiskFactorIcon(String(factor))"></i>
                        {{ formatFactorName(String(factor)) }}
                      </div>
                      <div class="factor-bar-container">
                        <div class="factor-bar" :style="{ width: value + '%' }" :class="getFactorBarClass(value)"></div>
                      </div>
                      <div class="factor-value">{{ typeof value === 'number' ? value.toFixed(0) : value }}</div>
                    </div>
                  </div>
                </div>

                <!-- Prevention Tips -->
                <div v-if="file.prevention_tips && file.prevention_tips.length > 0" class="detail-section">
                  <h5><i class="fas fa-lightbulb"></i> {{ $t('analytics.codebase.bugPrediction.recommendedFixes') }}</h5>
                  <ul class="tips-list">
                    <li v-for="(tip, tipIndex) in file.prevention_tips" :key="tipIndex">
                      <i class="fas fa-wrench"></i> {{ tip }}
                    </li>
                  </ul>
                </div>

                <!-- Suggested Tests -->
                <div v-if="file.suggested_tests && file.suggested_tests.length > 0" class="detail-section">
                  <h5><i class="fas fa-vial"></i> {{ $t('analytics.codebase.bugPrediction.suggestedTests') }}</h5>
                  <ul class="tests-list">
                    <li v-for="(test, testIndex) in file.suggested_tests" :key="testIndex">
                      <i class="fas fa-flask"></i> {{ test }}
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            <!-- Load More Button (#1430) -->
            <div v-if="getFilteredBugRiskFiles().length > bugRiskVisibleCount" class="show-more-container">
              <button @click="bugRiskVisibleCount += BUG_RISK_PAGE_SIZE" class="show-more-btn">
                <i class="fas fa-chevron-down"></i>
                Show More ({{ Math.min(BUG_RISK_PAGE_SIZE, getFilteredBugRiskFiles().length - bugRiskVisibleCount) }} of {{ getFilteredBugRiskFiles().length - bugRiskVisibleCount }} remaining)
              </button>
            </div>
          </div>

          <!-- Timestamp -->
          <div v-if="bugPredictionAnalysis.timestamp" class="scan-timestamp">
            <i class="fas fa-clock"></i> {{ $t('analytics.codebase.bugPrediction.lastAnalysis') }}: {{ formatTimestamp(bugPredictionAnalysis.timestamp) }}
          </div>
        </div>

        <!-- No Files to Analyze -->
        <div v-else-if="bugPredictionAnalysis && bugPredictionAnalysis.files.length === 0" class="success-state">
          <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.bugPrediction.noFilesAnalyzed') }}
        </div>

        <!-- Empty State -->
        <EmptyState
          v-else
          icon="fas fa-bug"
          :message="$t('analytics.codebase.bugPrediction.noData')"
        />
      </div>

      <!-- Issue #538: Code Intelligence Scores Section -->
      <div class="code-intelligence-scores-section analytics-section">
        <h3>
          <i class="fas fa-shield-alt"></i> {{ $t('analytics.codebase.intelligence.scoresTitle') }}
          <button
            @click="loadSecurityScore(); loadPerformanceScore(); loadRedisHealth()"
            :disabled="loadingSecurityScore || loadingPerformanceScore || loadingRedisHealth"
            class="refresh-btn"
            style="margin-left: 10px;"
          >
            <i :class="(loadingSecurityScore || loadingPerformanceScore || loadingRedisHealth) ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </h3>

        <!-- Score Cards Grid -->
        <div class="scores-grid">
          <!-- Security Score Card -->
          <div class="score-card security-card">
            <div class="score-header">
              <i class="fas fa-shield-alt"></i>
              <span>{{ $t('analytics.codebase.intelligence.security') }}</span>
              <button
                @click="loadSecurityScore"
                :disabled="loadingSecurityScore"
                class="card-refresh-btn"
                :title="$t('analytics.codebase.intelligence.refreshSecurity')"
              >
                <i :class="loadingSecurityScore ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
              </button>
            </div>
            <div v-if="loadingSecurityScore" class="score-loading">
              <i class="fas fa-spinner fa-spin"></i>
            </div>
            <div v-else-if="securityScoreError" class="score-error">
              <i class="fas fa-exclamation-triangle"></i>
              <span>{{ securityScoreError }}</span>
            </div>
            <div v-else-if="securityScore" class="score-content">
              <div class="score-value" :class="getScoreClass(securityScore.security_score)">
                {{ securityScore.security_score }}
              </div>
              <div class="score-grade" :class="getGradeClass(securityScore.grade)">
                {{ securityScore.grade }}
              </div>
              <div class="score-status">{{ securityScore.status_message }}</div>
              <div class="score-details">
                <span class="detail-item critical" v-if="securityScore.critical_issues > 0">
                  <i class="fas fa-times-circle"></i> {{ securityScore.critical_issues }} critical
                </span>
                <span class="detail-item warning" v-if="securityScore.high_issues > 0">
                  <i class="fas fa-exclamation-circle"></i> {{ securityScore.high_issues }} high
                </span>
                <span class="detail-item info">
                  <i class="fas fa-file-code"></i> {{ securityScore.files_analyzed }} files
                </span>
              </div>
              <button
                class="view-details-btn"
                @click="toggleSecurityDetails"
                :disabled="loadingSecurityFindings"
              >
                <i :class="loadingSecurityFindings ? 'fas fa-spinner fa-spin' : (showSecurityDetails ? 'fas fa-chevron-up' : 'fas fa-chevron-down')"></i>
                {{ showSecurityDetails ? $t('analytics.codebase.intelligence.hideDetails') : $t('analytics.codebase.intelligence.viewDetails') }}
              </button>
            </div>
            <div v-else class="score-empty">
              <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
            </div>
          </div>

          <!-- Performance Score Card -->
          <div class="score-card performance-card">
            <div class="score-header">
              <i class="fas fa-tachometer-alt"></i>
              <span>{{ $t('analytics.codebase.intelligence.performanceLabel') }}</span>
              <button
                @click="loadPerformanceScore"
                :disabled="loadingPerformanceScore"
                class="card-refresh-btn"
                :title="$t('analytics.codebase.intelligence.refreshPerformance')"
              >
                <i :class="loadingPerformanceScore ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
              </button>
            </div>
            <div v-if="loadingPerformanceScore" class="score-loading">
              <i class="fas fa-spinner fa-spin"></i>
            </div>
            <div v-else-if="performanceScoreError" class="score-error">
              <i class="fas fa-exclamation-triangle"></i>
              <span>{{ performanceScoreError }}</span>
            </div>
            <div v-else-if="performanceScore" class="score-content">
              <div class="score-value" :class="getScoreClass(performanceScore.performance_score)">
                {{ performanceScore.performance_score }}
              </div>
              <div class="score-grade" :class="getGradeClass(performanceScore.grade)">
                {{ performanceScore.grade }}
              </div>
              <div class="score-status">{{ performanceScore.status_message }}</div>
              <div class="score-details">
                <span class="detail-item warning" v-if="performanceScore.total_issues > 0">
                  <i class="fas fa-exclamation-triangle"></i> {{ performanceScore.total_issues }} issues
                </span>
                <span class="detail-item info">
                  <i class="fas fa-file-code"></i> {{ performanceScore.files_analyzed }} files
                </span>
              </div>
              <button
                class="view-details-btn"
                @click="togglePerformanceDetails"
                :disabled="loadingPerformanceFindings"
              >
                <i :class="loadingPerformanceFindings ? 'fas fa-spinner fa-spin' : (showPerformanceDetails ? 'fas fa-chevron-up' : 'fas fa-chevron-down')"></i>
                {{ showPerformanceDetails ? $t('analytics.codebase.intelligence.hideDetails') : $t('analytics.codebase.intelligence.viewDetails') }}
              </button>
            </div>
            <div v-else class="score-empty">
              <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
            </div>
          </div>

          <!-- Redis Health Score Card -->
          <div class="score-card redis-card">
            <div class="score-header">
              <i class="fas fa-database"></i>
              <span>{{ $t('analytics.codebase.intelligence.redisUsage') }}</span>
              <button
                @click="loadRedisHealth"
                :disabled="loadingRedisHealth"
                class="card-refresh-btn"
                :title="$t('analytics.codebase.intelligence.refreshRedis')"
              >
                <i :class="loadingRedisHealth ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
              </button>
            </div>
            <div v-if="loadingRedisHealth" class="score-loading">
              <i class="fas fa-spinner fa-spin"></i>
            </div>
            <div v-else-if="redisHealthError" class="score-error">
              <i class="fas fa-exclamation-triangle"></i>
              <span>{{ redisHealthError }}</span>
            </div>
            <div v-else-if="redisHealth" class="score-content">
              <div class="score-value" :class="getScoreClass(redisHealth.redis_health_score)">
                {{ redisHealth.redis_health_score }}
              </div>
              <div class="score-grade" :class="getGradeClass(redisHealth.grade)">
                {{ redisHealth.grade }}
              </div>
              <div class="score-status">{{ redisHealth.status_message }}</div>
              <div class="score-details">
                <span class="detail-item warning" v-if="redisHealth.total_issues > 0">
                  <i class="fas fa-exclamation-triangle"></i> {{ redisHealth.total_issues }} issues
                </span>
                <span class="detail-item info">
                  <i class="fas fa-file-code"></i> {{ redisHealth.total_files }} files
                </span>
              </div>
              <button
                class="view-details-btn"
                @click="toggleRedisDetails"
                :disabled="loadingRedisOptimizations"
              >
                <i :class="loadingRedisOptimizations ? 'fas fa-spinner fa-spin' : (showRedisDetails ? 'fas fa-chevron-up' : 'fas fa-chevron-down')"></i>
                {{ showRedisDetails ? $t('analytics.codebase.intelligence.hideDetails') : $t('analytics.codebase.intelligence.viewDetails') }}
              </button>
            </div>
            <div v-else class="score-empty">
              <span>{{ $t('analytics.codebase.intelligence.noScoreData') }}</span>
            </div>
          </div>
        </div>

        <!-- Issue #566: Expandable Security Findings Panel -->
        <div v-if="showSecurityDetails" class="findings-panel security-findings-panel">
          <div class="findings-header">
            <h4><i class="fas fa-shield-alt"></i> {{ $t('analytics.codebase.intelligence.securityFindings') }}</h4>
            <span class="findings-count">{{ securityFindings?.length ?? 0 }} findings</span>
          </div>
          <div v-if="loadingSecurityFindings" class="findings-loading">
            <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.intelligence.loadingSecurityFindings') }}
          </div>
          <div v-else-if="!securityFindings?.length" class="findings-empty">
            <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.intelligence.noSecurityVulnerabilities') }}
          </div>
          <div v-else class="findings-list">
            <div
              v-for="(finding, index) in securityFindings"
              :key="'sec-' + index"
              class="finding-item"
              :class="getSeverityClass(finding.severity)"
            >
              <div class="finding-header">
                <span class="finding-severity" :class="getSeverityClass(finding.severity)">
                  {{ finding.severity }}
                </span>
                <span class="finding-type">{{ finding.vulnerability_type }}</span>
              </div>
              <div class="finding-description">{{ finding.description }}</div>
              <div class="finding-location">
                <i class="fas fa-file-code"></i>
                {{ finding.file_path }}
                <span v-if="finding.line">:{{ finding.line }}</span>
              </div>
              <div v-if="finding.recommendation" class="finding-recommendation">
                <i class="fas fa-lightbulb"></i> {{ finding.recommendation }}
              </div>
              <div v-if="finding.owasp_category" class="finding-owasp">
                <i class="fas fa-tag"></i> OWASP: {{ finding.owasp_category }}
              </div>
            </div>
          </div>
        </div>

        <!-- Issue #566: Expandable Performance Findings Panel -->
        <div v-if="showPerformanceDetails" class="findings-panel performance-findings-panel">
          <div class="findings-header">
            <h4><i class="fas fa-tachometer-alt"></i> {{ $t('analytics.codebase.intelligence.performanceIssues') }}</h4>
            <span class="findings-count">{{ performanceFindings?.length ?? 0 }} issues</span>
          </div>
          <div v-if="loadingPerformanceFindings" class="findings-loading">
            <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.intelligence.loadingPerformanceIssues') }}
          </div>
          <div v-else-if="!performanceFindings?.length" class="findings-empty">
            <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.intelligence.noPerformanceIssues') }}
          </div>
          <div v-else class="findings-list">
            <div
              v-for="(finding, index) in performanceFindings"
              :key="'perf-' + index"
              class="finding-item"
              :class="getSeverityClass(finding.severity)"
            >
              <div class="finding-header">
                <span class="finding-severity" :class="getSeverityClass(finding.severity)">
                  {{ finding.severity }}
                </span>
                <span class="finding-type">{{ finding.issue_type }}</span>
              </div>
              <div class="finding-description">{{ finding.description }}</div>
              <div class="finding-location">
                <i class="fas fa-file-code"></i>
                {{ finding.file_path }}
                <span v-if="finding.line">:{{ finding.line }}</span>
                <span v-if="finding.function_name" class="function-name">
                  in {{ finding.function_name }}()
                </span>
              </div>
              <div v-if="finding.recommendation" class="finding-recommendation">
                <i class="fas fa-lightbulb"></i> {{ finding.recommendation }}
              </div>
            </div>
          </div>
        </div>

        <!-- Issue #566: Expandable Redis Optimizations Panel -->
        <div v-if="showRedisDetails" class="findings-panel redis-findings-panel">
          <div class="findings-header">
            <h4><i class="fas fa-database"></i> {{ $t('analytics.codebase.intelligence.redisOptimizations') }}</h4>
            <span class="findings-count">{{ redisOptimizations?.length ?? 0 }} suggestions</span>
          </div>
          <div v-if="loadingRedisOptimizations" class="findings-loading">
            <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.intelligence.loadingRedisOptimizations') }}
          </div>
          <div v-else-if="!redisOptimizations?.length" class="findings-empty">
            <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.intelligence.noRedisOptimizations') }}
          </div>
          <div v-else class="findings-list">
            <div
              v-for="(opt, index) in redisOptimizations"
              :key="'redis-' + index"
              class="finding-item"
              :class="getSeverityClass(opt.severity)"
            >
              <div class="finding-header">
                <span class="finding-severity" :class="getSeverityClass(opt.severity)">
                  {{ opt.severity }}
                </span>
                <span class="finding-type">{{ opt.optimization_type }}</span>
                <span v-if="opt.category" class="finding-category">{{ opt.category }}</span>
              </div>
              <div class="finding-description">{{ opt.description }}</div>
              <div class="finding-location">
                <i class="fas fa-file-code"></i>
                {{ opt.file_path }}
                <span v-if="opt.line">:{{ opt.line }}</span>
              </div>
              <div v-if="opt.recommendation" class="finding-recommendation">
                <i class="fas fa-lightbulb"></i> {{ opt.recommendation }}
              </div>
            </div>
          </div>
        </div>

        <!-- Empty State when no path -->
        <EmptyState
          v-if="!rootPath && !securityScore && !performanceScore && !redisHealth"
          icon="fas fa-shield-alt"
          :message="$t('analytics.codebase.intelligence.noScoresData')"
        />
      </div>

      <!-- Issue #538: Environment Analysis Section -->
      <div class="environment-analysis-section analytics-section">
        <h3>
          <i class="fas fa-leaf"></i> {{ $t('analytics.codebase.environment.title') }}
          <span v-if="environmentAnalysis" class="total-count">
            ({{ environmentAnalysis.total_hardcoded_values }} hardcoded values)
          </span>
          <button @click="loadEnvironmentAnalysis" :disabled="loadingEnvAnalysis" class="refresh-btn" style="margin-left: 10px;">
            <i :class="loadingEnvAnalysis ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons" v-if="environmentAnalysis">
            <button @click="exportSection('environment', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('environment', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>

        <!-- Issue #633: AI Filtering Toggle -->
        <div class="ai-filter-controls" style="margin-bottom: 15px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 6px; display: flex; align-items: center; gap: 15px; flex-wrap: wrap;">
          <label class="toggle-label" style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
            <input
              type="checkbox"
              v-model="useAiFiltering"
              style="width: 18px; height: 18px; cursor: pointer;"
            />
            <span style="font-weight: 500;">
              <i class="fas fa-robot"></i> {{ $t('analytics.codebase.environment.useAiFiltering') }}
            </span>
          </label>
          <span v-if="useAiFiltering" class="ai-filter-options" style="display: flex; align-items: center; gap: 10px;">
            <select v-model="aiFilteringPriority" class="ai-filter-select">
              <option value="high">{{ $t('analytics.codebase.environment.highPriorityOnly') }}</option>
              <option value="medium">{{ $t('analytics.codebase.environment.mediumPriority') }}</option>
              <option value="low">{{ $t('analytics.codebase.environment.lowPriority') }}</option>
              <option value="all">{{ $t('analytics.codebase.environment.allPriorities') }}</option>
            </select>
            <span class="ai-filter-model-hint">
              Model: {{ aiFilteringModel }}
            </span>
          </span>
          <span v-if="llmFilteringResult" class="llm-result-badge">
            <i class="fas fa-check-circle"></i>
            {{ llmFilteringResult.original_count }} → {{ llmFilteringResult.filtered_count }}
            ({{ llmFilteringResult.reduction_percent }}% reduced)
          </span>
        </div>

        <!-- Loading State -->
        <div v-if="loadingEnvAnalysis" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i>
          {{ useAiFiltering ? 'Scanning with AI filtering...' : 'Scanning for hardcoded values...' }}
        </div>

        <!-- Error State -->
        <div v-else-if="envAnalysisError" class="error-state">
          <i class="fas fa-exclamation-triangle"></i> {{ envAnalysisError }}
          <button @click="loadEnvironmentAnalysis" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <!-- Analysis Results -->
        <div v-else-if="environmentAnalysis && environmentAnalysis.total_hardcoded_values > 0" class="section-content">
          <!-- Summary Cards -->
          <div class="summary-cards">
            <div class="summary-card total">
              <div class="summary-value">{{ environmentAnalysis.total_hardcoded_values }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.environment.hardcodedValues') }}</div>
            </div>
            <div class="summary-card critical">
              <div class="summary-value">{{ environmentAnalysis.high_priority_count }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.environment.highPriority') }}</div>
            </div>
            <div class="summary-card warning">
              <div class="summary-value">{{ environmentAnalysis.recommendations_count }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.environment.recommendations') }}</div>
            </div>
            <div class="summary-card info">
              <div class="summary-value">{{ Object.keys(environmentAnalysis.categories).length }}</div>
              <div class="summary-label">{{ $t('analytics.codebase.environment.categories') }}</div>
            </div>
          </div>

          <!-- Categories Breakdown -->
          <div v-if="Object.keys(environmentAnalysis.categories).length > 0" class="categories-breakdown">
            <h4>{{ $t('analytics.codebase.environment.categories') }}</h4>
            <div class="category-badges">
              <span
                v-for="(count, category) in environmentAnalysis.categories"
                :key="category"
                class="category-badge"
              >
                {{ formatFactorName(String(category)) }}: {{ count }}
              </span>
            </div>
          </div>

          <!-- Recommendations List -->
          <div v-if="environmentAnalysis.recommendations.length > 0" class="recommendations-list">
            <h4>{{ $t('analytics.codebase.environment.envVarRecommendations') }}</h4>
            <div
              v-for="(rec, index) in environmentAnalysis.recommendations.slice(0, 10)"
              :key="'rec-' + index"
              class="recommendation-item"
              :class="'priority-' + rec.priority"
            >
              <div class="rec-header">
                <code class="env-var-name">{{ rec.env_var_name }}</code>
                <span class="priority-badge" :class="rec.priority">{{ rec.priority }}</span>
              </div>
              <div class="rec-description">{{ rec.description }}</div>
              <div class="rec-default">Default: <code>{{ truncateValue(rec.default_value, 50) }}</code></div>
            </div>
            <div v-if="environmentAnalysis.recommendations.length > 10" class="show-more">
              <span class="muted">Showing 10 of {{ environmentAnalysis.recommendations.length }} recommendations</span>
            </div>
          </div>

          <!-- Hardcoded Values Preview -->
          <div v-if="environmentAnalysis.hardcoded_values.length > 0" class="hardcoded-preview">
            <h4>
              {{ $t('analytics.codebase.environment.sampleHardcodedValues') }}
              <!-- Issue #631: Show truncation warning when results are limited -->
              <span v-if="environmentAnalysis.is_truncated || environmentAnalysis.hardcoded_values.length < environmentAnalysis.total_hardcoded_values" class="truncation-warning">
                (showing {{ environmentAnalysis.hardcoded_values.length }} of {{ environmentAnalysis.total_hardcoded_values.toLocaleString() }} - use Export for full data)
              </span>
            </h4>
            <!-- Issue #706: Fixed field names to match backend API (file/line/type/suggested_env_var) -->
            <div
              v-for="(hv, index) in environmentAnalysis.hardcoded_values.slice(0, 8)"
              :key="'hv-' + index"
              class="hardcoded-item"
              :class="'severity-' + hv.severity"
            >
              <div class="hv-location">
                <span class="file-path">{{ hv.file }}</span>
                <span class="line-number">:{{ hv.line }}</span>
              </div>
              <div class="hv-value">
                <code>{{ truncateValue(hv.value, 60) }}</code>
                <span class="value-type">{{ hv.type }}</span>
              </div>
              <div v-if="hv.suggested_env_var" class="hv-suggestion">
                <i class="fas fa-lightbulb"></i> Use: <code>{{ hv.suggested_env_var }}</code>
              </div>
            </div>
          </div>

          <!-- Analysis Time -->
          <div class="scan-timestamp">
            <i class="fas fa-clock"></i> Analysis completed in {{ environmentAnalysis.analysis_time_seconds.toFixed(2) }}s
          </div>
        </div>

        <!-- No Hardcoded Values -->
        <div v-else-if="environmentAnalysis && environmentAnalysis.total_hardcoded_values === 0" class="success-state">
          <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.environment.noHardcodedValues') }}
        </div>

        <!-- Empty State -->
        <EmptyState
          v-else
          icon="fas fa-leaf"
          :message="$t('analytics.codebase.environment.noData')"
        />
      </div>

      <!-- Issue #248: Code Ownership and Expertise Map Section -->
      <div class="ownership-section analytics-section">
        <h3>
          <i class="fas fa-users-cog"></i> {{ $t('analytics.codebase.ownership.title') }}
          <span v-if="ownershipAnalysis" class="total-count">
            ({{ ownershipAnalysis.summary.total_contributors }} contributors)
          </span>
          <button @click="loadOwnershipAnalysis" :disabled="loadingOwnership" class="refresh-btn" style="margin-left: 10px;">
            <i :class="loadingOwnership ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
          <!-- Issue #609: Section Export Buttons -->
          <div class="section-export-buttons" v-if="ownershipAnalysis">
            <button @click="exportSection('ownership', 'md')" class="export-btn" :title="$t('analytics.codebase.actions.exportMarkdown')">
              <i class="fas fa-file-alt"></i> MD
            </button>
            <button @click="exportSection('ownership', 'json')" class="export-btn" :title="$t('analytics.codebase.actions.exportJson')">
              <i class="fas fa-file-code"></i> JSON
            </button>
          </div>
        </h3>

        <!-- Loading State -->
        <div v-if="loadingOwnership" class="loading-state">
          <i class="fas fa-spinner fa-spin"></i> {{ $t('analytics.codebase.ownership.analyzing') }}
        </div>

        <!-- Error State -->
        <div v-else-if="ownershipError" class="error-state">
          <i class="fas fa-exclamation-triangle"></i> {{ ownershipError }}
          <button @click="loadOwnershipAnalysis" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
        </div>

        <!-- Analysis Results -->
        <div v-else-if="ownershipAnalysis && ownershipAnalysis.status === 'success'" class="section-content">
          <!-- View Mode Tabs -->
          <div class="ownership-tabs">
            <button
              :class="['tab-btn', { active: ownershipViewMode === 'overview' }]"
              @click="ownershipViewMode = 'overview'"
            >
              <i class="fas fa-chart-pie"></i> {{ $t('analytics.codebase.ownership.overview') }}
            </button>
            <button
              :class="['tab-btn', { active: ownershipViewMode === 'contributors' }]"
              @click="ownershipViewMode = 'contributors'"
            >
              <i class="fas fa-users"></i> {{ $t('analytics.codebase.ownership.contributors') }}
            </button>
            <button
              :class="['tab-btn', { active: ownershipViewMode === 'files' }]"
              @click="ownershipViewMode = 'files'"
            >
              <i class="fas fa-folder-tree"></i> {{ $t('analytics.codebase.ownership.filesTab') }}
            </button>
            <button
              :class="['tab-btn', { active: ownershipViewMode === 'gaps' }]"
              @click="ownershipViewMode = 'gaps'"
            >
              <i class="fas fa-exclamation-triangle"></i> {{ $t('analytics.codebase.ownership.knowledgeGaps') }}
              <span v-if="ownershipAnalysis.summary.critical_gaps > 0" class="gap-badge critical">
                {{ ownershipAnalysis.summary.critical_gaps }}
              </span>
            </button>
          </div>

          <!-- Overview Tab -->
          <div v-if="ownershipViewMode === 'overview'" class="ownership-overview">
            <!-- Summary Cards -->
            <div class="summary-cards">
              <div class="summary-card total">
                <div class="summary-value">{{ ownershipAnalysis.summary.total_files }}</div>
                <div class="summary-label">{{ $t('analytics.codebase.ownership.filesAnalyzed') }}</div>
              </div>
              <div class="summary-card info">
                <div class="summary-value">{{ ownershipAnalysis.summary.total_contributors }}</div>
                <div class="summary-label">{{ $t('analytics.codebase.ownership.contributors') }}</div>
              </div>
              <div class="summary-card" :class="ownershipAnalysis.metrics.overall_bus_factor <= 1 ? 'critical' : 'warning'">
                <div class="summary-value">{{ ownershipAnalysis.metrics.overall_bus_factor }}</div>
                <div class="summary-label">{{ $t('analytics.codebase.ownership.busFactor') }}</div>
              </div>
              <div class="summary-card" :class="ownershipAnalysis.summary.critical_gaps > 0 ? 'critical' : 'success'">
                <div class="summary-value">{{ ownershipAnalysis.summary.knowledge_gaps_count }}</div>
                <div class="summary-label">{{ $t('analytics.codebase.ownership.knowledgeGaps') }}</div>
              </div>
            </div>

            <!-- Metrics -->
            <div class="ownership-metrics">
              <div class="metric-item">
                <span class="metric-label">{{ $t('analytics.codebase.ownership.ownershipConcentration') }}:</span>
                <span class="metric-value" :class="ownershipAnalysis.metrics.ownership_concentration > 70 ? 'high-concentration' : ''">
                  {{ ownershipAnalysis.metrics.ownership_concentration }}%
                </span>
                <div class="metric-bar">
                  <div class="metric-bar-fill" :style="{ width: ownershipAnalysis.metrics.ownership_concentration + '%' }"
                       :class="ownershipAnalysis.metrics.ownership_concentration > 70 ? 'critical' : ownershipAnalysis.metrics.ownership_concentration > 50 ? 'warning' : 'ok'"></div>
                </div>
              </div>
              <div class="metric-item">
                <span class="metric-label">{{ $t('analytics.codebase.ownership.teamCoverage') }}:</span>
                <span class="metric-value">{{ ownershipAnalysis.metrics.team_coverage }}%</span>
                <div class="metric-bar">
                  <div class="metric-bar-fill" :style="{ width: ownershipAnalysis.metrics.team_coverage + '%' }"
                       :class="ownershipAnalysis.metrics.team_coverage < 30 ? 'critical' : ownershipAnalysis.metrics.team_coverage < 60 ? 'warning' : 'ok'"></div>
                </div>
              </div>
            </div>

            <!-- Top Contributors Preview -->
            <div v-if="ownershipAnalysis.metrics.top_contributors.length > 0" class="top-contributors-preview">
              <h4><i class="fas fa-trophy"></i> {{ $t('analytics.codebase.ownership.topContributors') }}</h4>
              <div class="contributor-list">
                <div
                  v-for="(contrib, index) in ownershipAnalysis.metrics.top_contributors.slice(0, 5)"
                  :key="'top-' + index"
                  class="contributor-item"
                >
                  <span class="rank">#{{ index + 1 }}</span>
                  <span class="name">{{ contrib.name }}</span>
                  <span class="lines">{{ contrib.lines.toLocaleString() }} lines</span>
                  <span class="score">{{ contrib.score.toFixed(0) }} pts</span>
                </div>
              </div>
            </div>

            <!-- Knowledge Risk Distribution -->
            <div v-if="Object.keys(ownershipAnalysis.metrics.knowledge_risk_distribution).length > 0" class="risk-distribution">
              <h4><i class="fas fa-chart-bar"></i> {{ $t('analytics.codebase.ownership.knowledgeRiskDistribution') }}</h4>
              <div class="risk-badges">
                <span
                  v-for="(count, risk) in ownershipAnalysis.metrics.knowledge_risk_distribution"
                  :key="risk"
                  class="risk-badge"
                  :class="'risk-' + risk"
                >
                  {{ formatFactorName(String(risk)) }}: {{ count }} files
                </span>
              </div>
            </div>
          </div>

          <!-- Contributors Tab -->
          <div v-if="ownershipViewMode === 'contributors'" class="ownership-contributors">
            <div
              v-for="(expert, index) in ownershipAnalysis.expertise_scores"
              :key="'expert-' + index"
              class="expert-card"
            >
              <div class="expert-header">
                <span class="expert-rank">#{{ index + 1 }}</span>
                <span class="expert-name">{{ expert.author_name }}</span>
                <span class="expert-score">{{ expert.overall_score.toFixed(0) }}</span>
              </div>
              <div class="expert-stats">
                <div class="stat">
                  <i class="fas fa-code"></i>
                  <span>{{ expert.total_lines.toLocaleString() }} lines</span>
                </div>
                <div class="stat">
                  <i class="fas fa-code-commit"></i>
                  <span>{{ expert.total_commits }} commits</span>
                </div>
                <div class="stat">
                  <i class="fas fa-crown"></i>
                  <span>{{ expert.files_owned }} files owned</span>
                </div>
              </div>
              <div class="expert-scores">
                <div class="score-bar">
                  <span class="score-label">Impact</span>
                  <div class="score-track">
                    <div class="score-fill impact" :style="{ width: expert.impact_score + '%' }"></div>
                  </div>
                  <span class="score-value">{{ expert.impact_score.toFixed(0) }}</span>
                </div>
                <div class="score-bar">
                  <span class="score-label">Recency</span>
                  <div class="score-track">
                    <div class="score-fill recency" :style="{ width: expert.recency_score + '%' }"></div>
                  </div>
                  <span class="score-value">{{ expert.recency_score.toFixed(0) }}</span>
                </div>
              </div>
              <div v-if="expert.expertise_areas.length > 0" class="expertise-areas">
                <span class="area-tag" v-for="area in expert.expertise_areas.slice(0, 3)" :key="area">
                  {{ area }}
                </span>
              </div>
            </div>
          </div>

          <!-- Files Tab -->
          <div v-if="ownershipViewMode === 'files'" class="ownership-files">
            <!-- Directory Overview -->
            <div v-if="ownershipAnalysis.directory_ownership.length > 0" class="directories-section">
              <h4><i class="fas fa-folder"></i> {{ $t('analytics.codebase.ownership.directoryOwnership') }}</h4>
              <div class="directory-list">
                <div
                  v-for="(dir, index) in ownershipAnalysis.directory_ownership.slice(0, 15)"
                  :key="'dir-' + index"
                  class="directory-item"
                  :class="'risk-' + dir.knowledge_risk"
                >
                  <div class="dir-path">{{ dir.directory_path }}</div>
                  <div class="dir-meta">
                    <span class="dir-owner">{{ dir.primary_owner || 'Unknown' }}</span>
                    <span class="dir-pct">{{ dir.ownership_percentage }}%</span>
                    <span class="dir-bus-factor" :class="dir.bus_factor <= 1 ? 'low' : ''">
                      <i class="fas fa-users"></i> {{ dir.bus_factor }}
                    </span>
                    <span class="dir-lines">{{ dir.total_lines.toLocaleString() }} lines</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- File Details -->
            <div v-if="ownershipAnalysis.file_ownership.length > 0" class="files-section">
              <h4><i class="fas fa-file-code"></i> {{ $t('analytics.codebase.ownership.fileOwnership') }}</h4>
              <div class="file-list">
                <div
                  v-for="(file, index) in ownershipAnalysis.file_ownership.slice(0, 30)"
                  :key="'file-' + index"
                  class="file-item"
                  :class="'risk-' + file.knowledge_risk"
                >
                  <div class="file-path">{{ file.file_path }}</div>
                  <div class="file-meta">
                    <span class="file-owner">{{ file.primary_owner || 'Unknown' }}</span>
                    <span class="file-pct">{{ file.ownership_percentage }}%</span>
                    <span class="file-bus-factor" :class="file.bus_factor <= 1 ? 'low' : ''">
                      <i class="fas fa-users"></i> {{ file.bus_factor }}
                    </span>
                    <span class="file-lines">{{ file.total_lines }} lines</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Knowledge Gaps Tab -->
          <div v-if="ownershipViewMode === 'gaps'" class="ownership-gaps">
            <div v-if="ownershipAnalysis.knowledge_gaps.length === 0" class="success-state">
              <i class="fas fa-check-circle"></i> {{ $t('analytics.codebase.ownership.noKnowledgeGaps') }}
            </div>
            <div v-else class="gaps-list">
              <div
                v-for="(gap, index) in ownershipAnalysis.knowledge_gaps"
                :key="'gap-' + index"
                class="gap-item"
                :class="'risk-' + gap.risk_level"
              >
                <div class="gap-header">
                  <span class="gap-risk-badge" :class="gap.risk_level">{{ gap.risk_level.toUpperCase() }}</span>
                  <span class="gap-type">{{ formatFactorName(gap.gap_type) }}</span>
                  <span class="gap-lines">{{ gap.affected_lines.toLocaleString() }} lines</span>
                </div>
                <div class="gap-area">
                  <i class="fas fa-folder"></i> {{ gap.area }}
                </div>
                <div class="gap-description">{{ gap.description }}</div>
                <div class="gap-recommendation">
                  <i class="fas fa-lightbulb"></i> {{ gap.recommendation }}
                </div>
              </div>
            </div>
          </div>

          <!-- Analysis Time -->
          <div class="scan-timestamp">
            <i class="fas fa-clock"></i> Analysis completed in {{ ownershipAnalysis.analysis_time_seconds.toFixed(2) }}s
          </div>
        </div>

        <!-- Empty State -->
        <EmptyState
          v-else
          icon="fas fa-users-cog"
          :message="$t('analytics.codebase.ownership.noData')"
        />
      </div>
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
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { NetworkConstants } from '@/constants/network.ts'
import EmptyState from '@/components/ui/EmptyState.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import PatternAnalysis from '@/components/analytics/PatternAnalysis.vue'
import { useToast } from '@/composables/useToast'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { useTaskLoader } from '@/composables/useTaskLoader'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
import { useAnalyticsScanRunner } from '@/composables/useAnalyticsScanRunner'
import { createLogger } from '@/utils/debugUtils'
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
import type {
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
} from '@/types/codeIntelligence'

const logger = createLogger('CodebaseAnalytics')

// ApexCharts components (still used in Analytics Charts section)
import {
  ProblemTypesChart,
  SeverityBarChart,
  RaceConditionsDonut,
  TopFilesChart,
} from '@/components/charts'

// i18n
const { t } = useI18n()
const route = useRoute()
const analyticsRouter = useRouter()

// Toast notifications
const { showToast } = useToast()

// Issue #566: Code Intelligence composable (renamed to avoid conflicts with existing refs)
// NOTE: securityFindings/performanceFindings/redisFindings and their fetch/scan methods do not
// exist in useCodeIntelligence. Those endpoints are tracked in issue #920.
const {
  isLoading: codeIntelLoading,
  suggestions: codeIntelSuggestions,
  analyzeCode: codeIntelAnalyzeCode,
  getSuggestions: codeIntelGetSuggestions,
  batchAnalyze: codeIntelBatchAnalyze,
} = useCodeIntelligence()

// TODO: implement security/performance/redis findings endpoints in backend (#920)
const codeIntelSecurityFindings = ref<SecurityFinding[]>([])
const codeIntelPerformanceFindings = ref<PerformanceFinding[]>([])
const codeIntelRedisFindings = ref<RedisOptimizationFinding[]>([])

// Issue #566: Code Intelligence UI state — tab/modal state moved to CodebaseSecurityPanel (#1469)
const codeIntelFindingsLoading = ref(false)
const codeIntelFindingsFetched = ref({ security: false, performance: false, redis: false })

// Issue #566: Code Intelligence computed properties
// Suggestions from analyzeCode serve as findings until dedicated endpoints exist (#920)
const codeIntelTotalFindings = computed(() =>
  codeIntelSuggestions.value.length
)

async function runCodeIntelligenceAnalysis() {
  if (!rootPath.value) return
  logger.info('Running Code Intelligence analysis on:', rootPath.value)

  // Reset findings cache
  codeIntelFindingsFetched.value = { security: false, performance: false, redis: false }

  // Use analyzeCode + getSuggestions; dedicated security/performance/redis endpoints
  // are tracked in issue #920
  codeIntelFindingsLoading.value = true
  try {
    await codeIntelAnalyzeCode({ code: rootPath.value })
    await codeIntelGetSuggestions(rootPath.value)
    codeIntelFindingsFetched.value = { security: true, performance: true, redis: true }
    notify(t('analytics.codebase.notify.codeIntelComplete', { count: codeIntelTotalFindings.value }), 'success')
  } catch (e) {
    logger.error('Code Intelligence analysis failed:', e)
    notify(t('analytics.codebase.notify.codeIntelFailed'), 'error')
  } finally {
    codeIntelFindingsLoading.value = false
  }
}

// Scan a single file by submitting it for batch analysis.
// Per-type scan endpoints (scanFileSecurity, scanFilePerformance, scanFileRedis)
// are not yet implemented in the composable and are tracked in issue #920.
async function handleFileScan(
  filePath: string,
  _types: { security: boolean; performance: boolean; redis: boolean }
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

// Notification helper for error handling
const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// Issue #1304/#1321: Background task composables for long-running analytics
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
    return r.status === 'no_data' ? [] as ImportTreeNode[] : undefined
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

// Issue #1133: CodeSource type
interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  credential_id: string | null
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  owner_id: string | null
  access: 'private' | 'shared' | 'public'
  shared_with: string[]
  created_at: string
}

// Reactive data
// Load path from localStorage if available, otherwise use default
const STORAGE_KEY_PATH = 'codebase-analytics-path'
const savedPath = localStorage.getItem(STORAGE_KEY_PATH)
const rootPath = ref(savedPath || '/opt/autobot')

// Issue #1133: Source registry state
const sources = ref<CodeSource[]>([])
const selectedSource = ref<CodeSource | null>(null)
const showSourceManager = ref(false)
const showAddSourceModal = ref(false)
const showShareSourceModal = ref(false)
const editTargetSource = ref<CodeSource | null>(null)
const shareTargetSource = ref<CodeSource | null>(null)
const showKnowledgeBaseOptIn = ref(false)
const knowledgeBaseAdding = ref(false)

const analyzing = ref(false)
const progressPercent = ref(0)
const progressStatus = ref('Ready')
const realTimeEnabled = ref(false)
const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)

// Issue #208: Pattern Analysis component ref
interface PatternAnalysisComponent {
  runAnalysis: () => Promise<void>
}
const patternAnalysisRef = ref<PatternAnalysisComponent | null>(null)

// Indexing job state tracking
const currentJobId = ref<string | null>(null)
const currentJobStatus = ref<string | null>(null)
const jobPollingInterval = ref<ReturnType<typeof setInterval> | null>(null)

// Interfaces for job tracking
interface JobPhase {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed'
}

interface JobPhasesData {
  phase_list: JobPhase[]
}

interface JobBatchesData {
  total_batches: number
  completed_batches: number
}

interface JobStatsData {
  files_scanned: number
  problems_found: number
  functions_found: number
  classes_found: number
  items_stored: number
}

// Enhanced progress tracking with phases and batches
const jobPhases = ref<JobPhasesData | null>(null)
const jobBatches = ref<JobBatchesData | null>(null)
const jobStats = ref<JobStatsData | null>(null)

// Helper to get phase icon based on status
const getPhaseIcon = (status: string): string => {
  switch (status) {
    case 'completed':
      return 'fas fa-check-circle'
    case 'running':
      return 'fas fa-spinner fa-spin'
    case 'pending':
    default:
      return 'fas fa-circle'
  }
}

// Get icon for problem category
const getCategoryIcon = (categoryId: string): string => {
  const iconMap: Record<string, string> = {
    race_conditions: 'fas fa-random',
    debug_code: 'fas fa-bug',
    complexity: 'fas fa-project-diagram',
    code_smells: 'fas fa-exclamation-circle',
    performance: 'fas fa-tachometer-alt',
    security: 'fas fa-shield-alt',
    long_functions: 'fas fa-scroll',
    duplicate_code: 'fas fa-clone',
    hardcoded_values: 'fas fa-lock',
    missing_types: 'fas fa-question-circle',
    unused_imports: 'fas fa-unlink',
    // Default icon
    default: 'fas fa-tag'
  }
  return iconMap[categoryId] || iconMap.default
}

// Analytics data interfaces
interface Problem {
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

interface DuplicateCode {
  similarity: number
  lines: number
  file1: string
  file2: string
  start1?: number
  start2?: number
}

interface Declaration {
  type: string
  name: string
  file_path: string
  line?: number
  line_number?: number
  is_exported?: boolean
}

// Issue #706: Fixed field names to match backend API response
// Backend returns 'file' and 'line', not 'file_path' and 'line_number'
interface HardcodedValue {
  file: string              // Backend returns 'file', not 'file_path'
  line: number              // Backend returns 'line', not 'line_number'
  variable_name?: string
  value: string
  type: string              // Backend returns 'type', aliased to value_type in display
  severity: string
  suggested_env_var: string // Backend returns 'suggested_env_var', not 'suggestion'
  context?: string
  current_usage?: string
}

interface RefactoringSuggestion {
  type: string
  severity: string
  description: string
  file_path: string
  line?: number
  suggestion: string
}

// Analytics data
const codebaseStats = ref<Record<string, unknown> | null>(null)
const problemsReport = ref<Problem[]>([])
const duplicateAnalysis = ref<DuplicateCode[]>([])
const declarationAnalysis = ref<Declaration[]>([])
const hardcodeAnalysis = ref<HardcodedValue[]>([])
const refactoringSuggestions = ref<RefactoringSuggestion[]>([])

// Code Intelligence / Anti-Pattern Detection data
interface CodeSmellsReportData {
  smells: Array<{
    type: string
    severity: string
    message: string
    file_path: string
    line?: number
  }>
  summary?: Record<string, unknown>
}

interface CodeHealthScoreData {
  grade: string
  health_score: number
  breakdown?: Record<string, unknown>
  [key: string]: unknown
}

const codeSmellsReport = ref<CodeSmellsReportData | null>(null)
const codeHealthScore = ref<CodeHealthScoreData | null>(null)
const analyzingCodeSmells = ref(false)
const codeSmellsAnalysisType = ref('') // 'smells' or 'health'
const exportingReport = ref(false)
const clearingCache = ref(false)

// Computed property for code smells progress title
const codeSmellsProgressTitle = computed(() => {
  return codeSmellsAnalysisType.value === 'health'
    ? t('analytics.codebase.progress.calculatingHealth')
    : t('analytics.codebase.progress.analyzingSmells')
})

// Enhanced analytics data interfaces
interface SystemOverviewData {
  api_requests_per_minute: number
  average_response_time: number
  active_connections: number
  system_health: string
}

interface CommunicationPatternsData {
  websocket_connections: number
  api_call_frequency: number
  data_transfer_rate: number
}

interface CodeQualityData {
  overall_score: number
  test_coverage: number
  code_duplicates: number
  technical_debt: number
}

interface PerformanceMetricsData {
  efficiency_score: number
  memory_usage: number
  cpu_usage: number
  load_time: number
}

interface ChartDataItem {
  name: string
  value: number
  type?: string
  [key: string]: unknown
}

interface ChartDataSummary {
  total_problems?: number
  unique_problem_types?: number
  files_with_problems?: number
  race_condition_count?: number
}

interface ChartData {
  summary?: ChartDataSummary
  problem_types?: ChartDataItem[]
  severity_counts?: ChartDataItem[]
  race_conditions?: ChartDataItem[]
  top_files?: ChartDataItem[]
  [key: string]: unknown
}

interface DependencyNode {
  id: string
  name: string
  type?: string
}

interface DependencyEdge {
  source: string
  target: string
  type?: string
}

interface ModuleData {
  name: string
  path?: string
  import_count: number
  [key: string]: unknown
}

interface ExternalDependency {
  name: string
  usage_count?: number
  [key: string]: unknown
}

// CircularDependency can be either an array of module names (string[])
// or an object with cycle/modules, length, and severity (#1197)
type CircularDependency =
  | string[]
  | { modules: string[]; cycle?: string[]; length?: number; severity?: string }

interface DependencySummary {
  total_modules?: number
  total_import_relationships?: number
  external_dependency_count?: number
  circular_dependency_count?: number
}

interface DependencyGraph {
  nodes: DependencyNode[]
  edges: DependencyEdge[]
  summary?: DependencySummary
  modules?: ModuleData[]
  external_dependencies?: ExternalDependency[]
  circular_dependencies?: CircularDependency[]
  import_relationships?: DependencyEdge[]
}

interface ImportTreeNode {
  name: string
  path: string
  children?: ImportTreeNode[]
  imports?: string[]
}

interface UnifiedReportData {
  categories: Record<string, Problem[]>
  summary: {
    total: number
    by_severity: Record<string, number>
    by_category: Record<string, number>
  }
  timestamp: string
}

// Enhanced analytics data
const systemOverview = ref<SystemOverviewData | null>(null)
const communicationPatterns = ref<CommunicationPatternsData | null>(null)
const codeQuality = ref<CodeQualityData | null>(null)
const performanceMetrics = ref<PerformanceMetricsData | null>(null)

// Chart data for visualizations
const chartData = ref<ChartData | null>(null)
const chartDataLoading = ref(false)
const chartDataError = ref('')

// Unified analytics report data
const unifiedReport = ref<UnifiedReportData | null>(null)
const unifiedReportLoading = ref(false)
const unifiedReportError = ref('')
const selectedCategory = ref('all') // Filter: all, race_conditions, debug_code, complexity, etc.

// Dependency analysis data — refs provided by useTaskLoader (#1321)
// Import tree data — refs provided by useTaskLoader (#1321)

// Function call graph data
const callGraphData = ref<DependencyGraph>({ nodes: [], edges: [] })
const callGraphSummary = ref<Record<string, unknown> | null>(null)
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
const callGraphOrphaned = ref<OrphanedFunction[]>([])
const callGraphLoading = ref(false)
const callGraphError = ref('')

// Issue #527: API Endpoint Checker data
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

// #1321: apiEndpointAnalysis — useAnalyticsFetch
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
  used: false
})

// Issue #538: Config Duplicates Detection data
interface ConfigDuplicatesResult {
  duplicates_found: number
  duplicates: Array<{ value: string; locations: Array<{ file: string; line: number }> }>
  report: string
}
// #1321: configDuplicatesAnalysis — useAnalyticsFetch
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

// Issue #538: Bug Prediction data
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
// #1418: bugPrediction — useBackgroundTask with batched analysis
const bugPredictionTask = useBackgroundTask(
  '/api/analytics/bug-prediction',
)
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

// Enhanced Bug Prediction UI state
const bugRiskFilter = ref<'all' | 'high' | 'medium' | 'low'>('all')
const BUG_RISK_PAGE_SIZE = 50
const bugRiskVisibleCount = ref(BUG_RISK_PAGE_SIZE)
const expandedBugRiskFiles = ref<Set<string>>(new Set())

// Bug Risk helper functions
function getAtRiskFilesCount(): number {
  if (!bugPredictionAnalysis.value) return 0
  // Count files with risk score >= 40 (medium and high risk)
  return bugPredictionAnalysis.value.files.filter(f => f.risk_score >= 40).length
}

function toggleBugRiskFilter(filter: 'high' | 'medium' | 'low'): void {
  bugRiskFilter.value = bugRiskFilter.value === filter ? 'all' : filter
  bugRiskVisibleCount.value = BUG_RISK_PAGE_SIZE
}

function toggleBugRiskFileExpand(filePath: string): void {
  if (expandedBugRiskFiles.value.has(filePath)) {
    expandedBugRiskFiles.value.delete(filePath)
  } else {
    expandedBugRiskFiles.value.add(filePath)
  }
  // Force reactivity update
  expandedBugRiskFiles.value = new Set(expandedBugRiskFiles.value)
}

function getFilteredBugRiskFiles(): BugPredictionFile[] {
  if (!bugPredictionAnalysis.value) return []
  const files = bugPredictionAnalysis.value.files
  let filtered: BugPredictionFile[]

  switch (bugRiskFilter.value) {
    case 'high':
      filtered = files.filter(f => f.risk_score >= 60)
      break
    case 'medium':
      filtered = files.filter(f => f.risk_score >= 40 && f.risk_score < 60)
      break
    case 'low':
      filtered = files.filter(f => f.risk_score < 40)
      break
    case 'all':
    default:
      filtered = [...files]
      break
  }

  // Sort by risk score descending
  return filtered.sort((a, b) => b.risk_score - a.risk_score)
}

interface TopRiskFactor {
  name: string
  count: number
  severity: 'critical' | 'high' | 'medium' | 'low'
}

function getTopRiskFactors(): TopRiskFactor[] {
  if (!bugPredictionAnalysis.value) return []

  const factorCounts: Record<string, number> = {
    complexity: 0,
    change_frequency: 0,
    file_size: 0,
    bug_history: 0,
    test_coverage: 0
  }

  // Count files with high values for each factor
  for (const file of bugPredictionAnalysis.value.files) {
    if (!file.factors) continue
    if (file.factors.complexity >= 80) factorCounts.complexity++
    if (file.factors.change_frequency >= 80) factorCounts.change_frequency++
    if (file.factors.file_size >= 70) factorCounts.file_size++
    if (file.factors.bug_history > 0) factorCounts.bug_history++
    if (file.factors.test_coverage === 50) factorCounts.test_coverage++
  }

  // Convert to array and sort by count
  const factors: TopRiskFactor[] = Object.entries(factorCounts)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => ({
      name,
      count,
      severity: getSeverityForFactor(name, count)
    }))
    .sort((a, b) => b.count - a.count)

  return factors.slice(0, 4) // Top 4 factors
}

function getSeverityForFactor(factor: string, count: number): 'critical' | 'high' | 'medium' | 'low' {
  if (factor === 'bug_history' && count > 0) return 'critical'
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
    dependency_count: 'fas fa-sitemap'
  }
  return icons[factor] || 'fas fa-exclamation-circle'
}

function getRiskFactorDescription(factor: string): string {
  const descriptions: Record<string, string> = {
    complexity: t('analytics.codebase.bugPrediction.factors.complexity'),
    change_frequency: t('analytics.codebase.bugPrediction.factors.changeFrequency'),
    file_size: t('analytics.codebase.bugPrediction.factors.fileSize'),
    bug_history: t('analytics.codebase.bugPrediction.factors.bugHistory'),
    test_coverage: t('analytics.codebase.bugPrediction.factors.testCoverage'),
    dependency_count: t('analytics.codebase.bugPrediction.factors.dependencyCount')
  }
  return descriptions[factor] || t('analytics.codebase.bugPrediction.factors.default')
}

function getFactorBarClass(value: number): string {
  if (value >= 80) return 'bar-critical'
  if (value >= 50) return 'bar-warning'
  return 'bar-ok'
}

// Issue #538: Code Intelligence Scores (Security, Performance, Redis)
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
// securityScore, loadingSecurityScore, securityScoreError — provided by useTaskLoader (#1321)
// #1321: performanceScore — useAnalyticsFetch
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
    if (r.status === 'no_data') return undefined
    return undefined
  },
)
const redisHealth = ref<RedisHealthResult | null>(null)
const loadingRedisHealth = ref(false)
const redisHealthError = ref('')

// Issue #566: Detailed findings interfaces for expandable panels (field names from API)
// Distinct from code-intelligence SecurityFinding/PerformanceFinding types (#920)
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

// Issue #566/#1321: Detailed findings — useAnalyticsFetch (POST)
const {
  data: securityFindings,
  loading: loadingSecurityFindings,
  load: _loadSecurityFindings,
} = useAnalyticsFetch<SecurityFindingDetail[]>(
  '/api/code-intelligence/security/analyze',
  (r) => (r.status === 'success' && r.findings)
    ? r.findings as unknown as SecurityFindingDetail[]
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
  (r) => (r.status === 'success' && r.findings)
    ? r.findings as unknown as PerformanceFindingDetail[]
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
  (r) => (r.status === 'success' && r.findings)
    ? r.findings as unknown as RedisOptimization[]
    : [],
  { method: 'POST' },
)
const showRedisDetails = ref(false)

// Issue #538: Environment Analysis data
// Issue #706: Fixed field names to match backend API response
interface HardcodedValue {
  file: string              // Backend returns 'file', not 'file_path'
  line: number              // Backend returns 'line', not 'line_number'
  variable_name?: string
  value: string
  type: string              // Backend returns 'type', not 'value_type'
  severity: string
  suggested_env_var: string // Backend returns 'suggested_env_var', not 'suggestion'
  context?: string
  current_usage?: string
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
  hardcoded_values: HardcodedValue[]
  recommendations: EnvRecommendation[]
  // Issue #631: Indicates if display results are truncated
  is_truncated?: boolean
}
const environmentAnalysis = ref<EnvironmentAnalysisResult | null>(null)
const loadingEnvAnalysis = ref(false)
const envAnalysisError = ref('')

// Issue #633: AI filtering toggle state
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

// Issue #248: Code Ownership and Expertise Map data
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
  top_contributors: Array<{ name: string; lines: number; score: number }>
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
// #1321: ownershipAnalysis — useAnalyticsFetch
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
    if (r.status === 'error') return undefined
    return undefined
  },
)
const ownershipViewMode = ref<'overview' | 'files' | 'contributors' | 'gaps'>('overview')

// Issue #244: Cross-Language Pattern Analysis data
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
const crossLanguageAnalysis = ref<CrossLanguageAnalysisResult | null>(null)
const loadingCrossLanguage = ref(false)
const crossLanguageError = ref('')
const expandedCrossLanguageGroups = reactive({
  dtoMismatches: false,
  apiMismatches: false,
  validationDups: false,
  semanticMatches: false
})

// Loading states for individual data types
const loadingProgress = reactive({
  declarations: false,
  duplicates: false,
  hardcodes: false,
  problems: false
})

// UI state for "show all" functionality
const showAllProblems = ref(false)
const showAllDeclarations = ref(false)
const showAllDuplicates = ref(false)

onMounted(async () => {
  const sourceId = route.params.sourceId as string | undefined
  if (!sourceId) {
    analyticsRouter.replace({ name: 'analytics-codebase' })
    return
  }

  // Load the source metadata from backend
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const resp = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/${sourceId}`,
    )
    if (resp.ok) {
      const source = await resp.json()
      selectedSource.value = source
      rootPath.value = source.clone_path || ''
      localStorage.setItem(STORAGE_KEY_PATH, rootPath.value)
    } else {
      notify(t('analytics.codebase.notify.sourceNotFound'), 'error')
      analyticsRouter.replace({ name: 'analytics-codebase' })
      return
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to load source metadata:', msg)
    notify(t('analytics.codebase.notify.sourceNotFound'), 'error')
    analyticsRouter.replace({ name: 'analytics-codebase' })
    return
  }

  // Check if there's already an indexing job running
  await checkCurrentIndexingJob()

  // Issue #1469: Load only cached results on mount (no analysis triggers)
  loadCachedAnalyticsData()

  // Load sources list for any modals
  loadSources()
})

// Issue #1133: Source registry functions

async function loadSources() {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/sources`)
    if (!response.ok) return
    const data = await response.json()
    sources.value = data.sources ?? []
  } catch (err: unknown) {
    logger.warn('Failed to load sources:', err instanceof Error ? err.message : String(err))
  }
}

function handleSelectSource(source: CodeSource) {
  selectedSource.value = source
  if (source.clone_path) {
    rootPath.value = source.clone_path
    localStorage.setItem(STORAGE_KEY_PATH, source.clone_path)
  }
  showSourceManager.value = false
  notify(t('analytics.codebase.notify.selectedSource', { name: source.name }), 'info')
}

function handleClearSource() {
  selectedSource.value = null
}

async function handleSourceSaved(source: CodeSource) {
  showAddSourceModal.value = false
  editTargetSource.value = null
  await loadSources()
  notify(t('analytics.codebase.notify.sourceSaved', { name: source.name }), 'success')
}

async function handleShareSaved(source: CodeSource) {
  showShareSourceModal.value = false
  shareTargetSource.value = null
  await loadSources()
  notify(t('analytics.codebase.notify.accessUpdated', { name: source.name }), 'success')
}

function handleEditSource(source: CodeSource) {
  editTargetSource.value = source
  showAddSourceModal.value = true
  showSourceManager.value = false
}

function handleShareSource(source: CodeSource) {
  shareTargetSource.value = source
  showShareSourceModal.value = true
}

async function addToKnowledgeBase() {
  if (!rootPath.value) return
  knowledgeBaseAdding.value = true
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_path: rootPath.value })
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }
    showKnowledgeBaseOptIn.value = false
    notify(t('analytics.codebase.notify.knowledgeBaseAdded'), 'success')
  } catch (err: unknown) {
    logger.error('Failed to add to knowledge base:', err instanceof Error ? err.message : String(err))
    notify(t('analytics.codebase.notify.knowledgeBaseFailed'), 'error')
  } finally {
    knowledgeBaseAdding.value = false
  }
}

// Check if there's a running indexing job
const checkCurrentIndexingJob = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/current`)
    if (response.ok) {
      const data = await response.json()
      if (data.has_active_job) {
        // Job is running - update UI and start polling
        currentJobId.value = data.task_id
        currentJobStatus.value = data.status
        analyzing.value = true
        progressStatus.value = data.progress?.step || t('analytics.codebase.status.indexingInProgress')
        progressPercent.value = data.progress?.percent || 20

        // Start polling for updates
        startJobPolling()
        notify(t('analytics.codebase.notify.indexingAlreadyRunning'), 'info')
      } else if (data.task_id && data.status !== 'idle') {
        // Job recently completed
        progressStatus.value = t('analytics.codebase.status.lastJob', { status: data.status })
      }
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.warn('Could not check for running job:', errorMessage)
  }
}

// Poll for job status updates
const startJobPolling = () => {
  if (jobPollingInterval.value) {
    clearInterval(jobPollingInterval.value)
  }

  jobPollingInterval.value = setInterval(async () => {
    await pollJobStatus()
  }, 2000) // Poll every 2 seconds
}

// Stop polling
const stopJobPolling = () => {
  if (jobPollingInterval.value) {
    clearInterval(jobPollingInterval.value)
    jobPollingInterval.value = null
  }
}

// Poll for current job status
const pollJobStatus = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/current`)
    if (response.ok) {
      const data = await response.json()
      currentJobStatus.value = data.status

      if (data.has_active_job) {
        // Keep analyzing true while job is active
        analyzing.value = true

        // Update phase tracking first (used in status building)
        if (data.phases) {
          jobPhases.value = data.phases
        }

        // Update batch tracking
        if (data.batches) {
          jobBatches.value = data.batches
        }

        // Update job stats
        if (data.stats) {
          jobStats.value = data.stats
        }

        // Update progress - build informative status message
        if (data.progress) {
          progressPercent.value = data.progress.percent || 0

          // Build detailed status from operation, current_file, and progress counts
          const operation = data.progress.operation || 'Processing'
          const currentFile = data.progress.current_file || ''
          const current = data.progress.current || 0
          const total = data.progress.total || 0

          // Build status with progress counts when available
          let statusParts: string[] = []
          if (currentFile && currentFile !== 'Initializing...') {
            statusParts.push(currentFile)
          }
          if (total > 0) {
            statusParts.push(`(${current}/${total})`)
          }

          progressStatus.value = statusParts.length > 0
            ? `${operation}: ${statusParts.join(' ')}`
            : operation
        }

        // Also poll for intermediate results (but don't overwrite detailed status)
        await pollIntermediateResults()
      } else {
        // Job finished
        analyzing.value = false
        stopJobPolling()

        // Reset enhanced tracking
        jobPhases.value = null
        jobBatches.value = null
        jobStats.value = null

        if (data.status === 'completed') {
          progressStatus.value = t('analytics.codebase.status.indexingCompleted')
          progressPercent.value = 100
          notify(t('analytics.codebase.notify.indexingCompleted'), 'success')

          // Issue #1133: Show knowledge base opt-in after indexing
          showKnowledgeBaseOptIn.value = true

          // Refresh data — full analysis after manual indexing
          await runAllAnalysisScans()
        } else if (data.status === 'cancelled') {
          progressStatus.value = t('analytics.codebase.status.indexingCancelled')
          notify(t('analytics.codebase.notify.indexingCancelled'), 'warning')
        } else if (data.status === 'failed' || data.error) {
          progressStatus.value = t('analytics.codebase.status.indexingFailed', { error: data.error || t('analytics.codebase.errors.unknown') })
          notify(t('analytics.codebase.notify.indexingFailed', { error: data.error || t('analytics.codebase.errors.unknown') }), 'error')
        }

        currentJobId.value = null
      }
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.warn('Job polling error:', errorMessage)
  }
}

// Poll for intermediate results during indexing
// Note: Does NOT update progressStatus - that's handled by pollJobStatus with detailed info
const pollIntermediateResults = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')

    // Poll for problems found so far
    const problemsResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/problems`)
    if (problemsResponse.ok) {
      const problemsData = await problemsResponse.json()
      // Always update problems (even if empty) to reflect current state
      problemsReport.value = problemsData.problems || []
    }

    // Poll for stats - update codebaseStats but don't overwrite progressStatus
    const statsResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/stats`)
    if (statsResponse.ok) {
      const statsData = await statsResponse.json()
      if (statsData.stats) {
        codebaseStats.value = statsData.stats
        // Note: progressStatus is now set by pollJobStatus with detailed operation info
        // The jobStats ref already shows files_scanned, problems_found in the UI
      }
    }
  } catch (error: unknown) {
    // Silent - don't interrupt polling
  }
}

// Cancel the running indexing job
const cancelIndexingJob = async () => {
  if (!currentJobId.value) {
    notify(t('analytics.codebase.notify.noActiveJob'), 'warning')
    return
  }

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index/cancel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })

    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        analyzing.value = false
        stopJobPolling()
        currentJobId.value = null
        progressStatus.value = t('analytics.codebase.status.indexingCancelledByUser')
        notify(t('analytics.codebase.notify.indexingJobCancelled'), 'success')
      } else {
        notify(data.message || t('analytics.codebase.notify.couldNotCancel'), 'warning')
      }
    } else {
      notify(t('analytics.codebase.notify.cancelFailed'), 'error')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    notify(t('analytics.codebase.notify.cancelError', { error: errorMessage }), 'error')
  }
}

const handleStop = () => {
  if (analyzing.value && currentJobId.value) {
    cancelIndexingJob()
  }
  if (scanRunner.running.value) {
    scanRunner.cancel()
  }
}

const hasAnyResults = computed(() => {
  return !!(
    codebaseStats.value ||
    problemsReport.value.length > 0 ||
    declarationAnalysis.value.length > 0 ||
    duplicateAnalysis.value.length > 0
  )
})

// Fetch project root from backend configuration (only if no localStorage path)
// Issue #677: Uses centralized appConfig to avoid duplicate API calls
const loadProjectRoot = async () => {
  // Skip if we already have a saved path from localStorage
  const savedPath = localStorage.getItem(STORAGE_KEY_PATH)
  if (savedPath) {
    logger.debug('Using saved path from localStorage:', savedPath)
    return
  }

  try {
    // Issue #677: Use appConfig.getProjectRoot() instead of direct fetch
    // This leverages the centralized config with deduplication
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

// Load all codebase analytics data (silent mode - no alerts)
// Issue #711: Phased loading for better perceived performance
// Phase 1: Critical data (stats, problems) - show immediately
// Phase 2: Important data (declarations, duplicates, charts) - load next
// Phase 3: Secondary data (call graph, analysis) - load in background
// Issue #1469: Load only cached/stored results on mount (no POST-based analysis triggers).
// Scans that trigger new computation (POST /analyze, real-time scans) are excluded here
// and only run via runAllAnalysisScans() after manual indexing or explicit user action.
const loadCachedAnalyticsData = async () => {
  try {
    await scanRunner.runAll([
      { id: 'stats', label: t('analytics.codebase.scans.stats'), run: () => getCodebaseStats() },
      { id: 'problems', label: t('analytics.codebase.scans.problems'), run: () => getProblemsReport() },
      { id: 'declarations', label: t('analytics.codebase.scans.declarations'), run: () => loadDeclarations() },
      { id: 'hardcodes', label: t('analytics.codebase.scans.hardcodes'), run: () => loadHardcodes() },
      { id: 'charts', label: t('analytics.codebase.scans.charts'), run: () => loadChartData() },
      { id: 'callgraph', label: t('analytics.codebase.scans.callGraph'), run: () => loadCallGraphData() },
      { id: 'configDuplicates', label: t('analytics.codebase.scans.configDuplicates'), run: () => loadConfigDuplicates() },
      { id: 'apiEndpoints', label: t('analytics.codebase.scans.apiEndpoints'), run: () => loadApiEndpointAnalysis() },
      { id: 'crossLanguage', label: t('analytics.codebase.scans.crossLanguage'), run: () => getCrossLanguageAnalysis() },
    ])

    if (scanRunner.failedCount.value > 0) {
      progressStatus.value = t('analytics.codebase.status.loadPartialFailed', {
        failed: scanRunner.failedCount.value,
        total: scanRunner.totalCount.value,
      })
    } else {
      progressStatus.value = t('analytics.codebase.status.loadComplete')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to load cached analytics data:', error)
    progressStatus.value = t('analytics.codebase.status.loadFailed', { error: errorMessage })
  }
}

// Issue #1469: Full analysis scan list — only runs after manual indexing or explicit user action.
// Includes POST-based analysis triggers and real-time computation scans.
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

    if (scanRunner.failedCount.value > 0) {
      progressStatus.value = t('analytics.codebase.status.loadPartialFailed', {
        failed: scanRunner.failedCount.value,
        total: scanRunner.totalCount.value,
      })
    } else {
      progressStatus.value = t('analytics.codebase.status.loadComplete')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to load codebase analytics data:', error)
    progressStatus.value = t('analytics.codebase.status.loadFailed', { error: errorMessage })
  }
}

// Load chart data for visualizations
const loadChartData = async () => {
  chartDataLoading.value = true
  chartDataError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/analytics/charts`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`Chart data endpoint returned ${response.status}`)
    }

    const data = await response.json()

    if (data.status === 'success' && data.chart_data) {
      chartData.value = data.chart_data
      logger.debug('Chart data loaded:', {
        problemTypes: data.chart_data.problem_types?.length || 0,
        severities: data.chart_data.severity_counts?.length || 0,
        raceConditions: data.chart_data.race_conditions?.length || 0,
        topFiles: data.chart_data.top_files?.length || 0
      })
    } else if (data.status === 'no_data') {
      chartData.value = null
      logger.debug('No chart data available - run indexing first')
    }

  } catch (error: unknown) {
    logger.error('Failed to load chart data:', error)
    chartDataError.value = error instanceof Error ? error.message : String(error)
  } finally {
    chartDataLoading.value = false
  }
}

// Load unified analytics report
const loadUnifiedReport = async () => {
  unifiedReportLoading.value = true
  unifiedReportError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/unified/report`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`Unified report endpoint returned ${response.status}`)
    }

    const data = await response.json()

    if (data.status === 'success') {
      unifiedReport.value = data
      logger.debug('Unified report loaded:', {
        healthScore: data.summary?.health_score,
        grade: data.summary?.grade,
        totalIssues: data.summary?.total_issues,
        categories: Object.keys(data.categories || {}).length
      })
    } else if (data.status === 'no_data') {
      // Issue #543: Handle no_data status from backend
      unifiedReport.value = null
      logger.debug('No unified report data - run indexing first')
    }
  } catch (error: unknown) {
    logger.error('Failed to load unified report:', error)
    unifiedReportError.value = error instanceof Error ? error.message : String(error)
  } finally {
    unifiedReportLoading.value = false
  }
}

// Get available categories from unified report
const availableCategories = computed(() => {
  if (!unifiedReport.value?.categories) return []
  const categories = unifiedReport.value.categories
  return Object.keys(categories).map(key => ({
    id: key,
    name: key.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    count: Array.isArray(categories[key]) ? categories[key].length : 0
  }))
})

// Get filtered chart data based on selected category
const filteredChartData = computed((): ChartData | null => {
  if (!chartData.value) return null
  if (selectedCategory.value === 'all') return chartData.value

  const filtered: ChartData = { ...chartData.value }

  // Filter problem types by selected category
  if (filtered.problem_types) {
    filtered.problem_types = filtered.problem_types.filter((pt: ChartDataItem) => {
      const type = pt.type?.toLowerCase() || ''
      const category = selectedCategory.value.toLowerCase()
      return type.includes(category) || category.includes(type)
    })
  }

  return filtered
})

// Load dependency analysis data (#1304/#1321: useTaskLoader)
const loadDependencyData = () => _loadDependencyTask()

// Load import tree data (#1304/#1321: useTaskLoader)
const loadImportTreeData = () => _loadImportTreeTask()

// Handle file navigation from import tree
const handleFileNavigate = (filePath: string) => {
  logger.debug('Navigate to file:', filePath)
  // Could scroll to file in problems list or open in editor
  // For now, just log it - can be extended later
  showToast(t('analytics.codebase.notify.selected', { item: filePath }), 'info', 2000)
}

// Load function call graph data
const loadCallGraphData = async () => {
  callGraphLoading.value = true
  callGraphError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/analytics/call-graph`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`Call graph endpoint returned ${response.status}`)
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
        summary: data.summary
      })
    } else if (data.status === 'no_data') {
      // Issue #543: Handle no_data status from backend
      callGraphData.value = { nodes: [], edges: [] }
      callGraphSummary.value = null
      callGraphOrphaned.value = []
      logger.debug('No call graph data - run indexing first')
    }

  } catch (error: unknown) {
    logger.error('Failed to load call graph:', error)
    callGraphError.value = error instanceof Error ? error.message : String(error)
  } finally {
    callGraphLoading.value = false
  }
}

// Handle function selection from call graph
const handleFunctionSelect = (funcId: string) => {
  logger.debug('Selected function:', funcId)
  showToast(t('analytics.codebase.notify.selected', { item: funcId }), 'info', 2000)
}

// Silent version of declarations loading (no alerts)
const loadDeclarations = async () => {
  loadingProgress.declarations = true
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`
    const response = await fetchWithAuth(declarationsEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      throw new Error(`Declarations endpoint returned ${response.status}`)
    }
    const data = await response.json()
    declarationAnalysis.value = data.declarations || []
  } catch (error: unknown) {
    logger.error('Failed to load declarations:', error)
  } finally {
    loadingProgress.declarations = false
  }
}

// Silent version of duplicates loading (#1304: background task)
const loadDuplicates = async () => {
  loadingProgress.duplicates = true
  try {
    const ok = await dupTask.start()
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

// Silent version of hardcodes loading (no alerts)
const loadHardcodes = async () => {
  loadingProgress.hardcodes = true
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const hardcodesEndpoint = `${backendUrl}/api/analytics/codebase/hardcodes`
    const response = await fetchWithAuth(hardcodesEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      throw new Error(`Hardcodes endpoint returned ${response.status}`)
    }
    const data = await response.json()
    hardcodeAnalysis.value = data.hardcodes || []
  } catch (error: unknown) {
    logger.error('Failed to load hardcodes:', error)
  } finally {
    loadingProgress.hardcodes = false
  }
}

// Issue #538/#1321: Config duplicates (useAnalyticsFetch)
const loadConfigDuplicates = () => _loadConfigDuplicates()

// Issue #538/#1321: Bug prediction (useAnalyticsFetch)
// Issue #1430: removed hardcoded limit=1000 — backend default handles it
const loadBugPrediction = () => bugPredictionTask.start()

// Issue #538/#1321: API endpoint analysis (useAnalyticsFetch)
const loadApiEndpointAnalysis = () => _loadApiEndpoints()

// Issue #538/#1321: Load security score (useTaskLoader)
const loadSecurityScore = async () => {
  if (!rootPath.value) return
  await _loadSecurityScoreTask(undefined, { path: rootPath.value })
}

// Issue #538/#1321: Performance score (useAnalyticsFetch)
const loadPerformanceScore = async () => {
  if (!rootPath.value) return
  await _loadPerformanceScore({ path: rootPath.value })
}

// Issue #538: Load Redis health score from code intelligence
const loadRedisHealth = async () => {
  if (!rootPath.value) return
  // Issue #1190: /opt/autobot is too large for real-time scan (504 timeout). Skip it.
  if (rootPath.value === '/opt/autobot' || rootPath.value.includes('/data/code-sources/')) {
    logger.debug('Skipping Redis health scan for large/remote path:', rootPath.value)
    return
  }
  loadingRedisHealth.value = true
  redisHealthError.value = ''
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/code-intelligence/redis/health-score?path=${encodeURIComponent(rootPath.value)}`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      if (response.status === 504) {
        throw new Error('Analysis timed out — codebase too large for real-time scan')
      }
      const detail = await response.json().catch(() => null)
      throw new Error(detail?.detail || `Redis health endpoint returned ${response.status}`)
    }
    const data = await response.json()
    if (data.status === 'success') {
      redisHealth.value = {
        redis_health_score: data.health_score ?? data.redis_health_score ?? 0,
        grade: data.grade || 'N/A',
        status_message: data.status_message || '',
        total_files: data.total_files || 0,
        total_issues: data.total_optimizations || data.total_issues || 0,
        files_with_issues: data.files_with_issues || 0
      }
    } else if (data.status === 'no_data') {
      // Issue #543: Handle no_data status from backend
      redisHealth.value = null
      logger.debug('No Redis health data - run indexing first')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to load Redis health:', error)
    redisHealthError.value = errorMessage
  } finally {
    loadingRedisHealth.value = false
  }
}

// Issue #566/#1321: Detailed findings loaders (useAnalyticsFetch POST)
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

// Issue #566: Toggle functions for detail panels
const toggleSecurityDetails = async () => {
  showSecurityDetails.value = !showSecurityDetails.value
  if (showSecurityDetails.value && !securityFindings.value?.length) {
    await loadSecurityFindings()
  }
}

const togglePerformanceDetails = async () => {
  showPerformanceDetails.value = !showPerformanceDetails.value
  if (showPerformanceDetails.value && !performanceFindings.value?.length) {
    await loadPerformanceFindings()
  }
}

const toggleRedisDetails = async () => {
  showRedisDetails.value = !showRedisDetails.value
  if (showRedisDetails.value && !redisOptimizations.value?.length) {
    await loadRedisOptimizations()
  }
}

// Issue #566: Get severity color class
const getSeverityClass = (severity: string): string => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'severity-critical'
    case 'high': return 'severity-high'
    case 'medium': return 'severity-medium'
    case 'low': return 'severity-low'
    default: return 'severity-info'
  }
}

// Issue #538: Load environment analysis from codebase analytics
// Issue #633: Added AI filtering support with LLM-based false positive reduction
const loadEnvironmentAnalysis = async () => {
  if (!rootPath.value) return
  loadingEnvAnalysis.value = true
  envAnalysisError.value = ''
  llmFilteringResult.value = null
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    // Issue #633: Build URL with optional AI filtering parameters
    let url = `${backendUrl}/api/analytics/codebase/env-analysis?path=${encodeURIComponent(rootPath.value)}`
    if (useAiFiltering.value) {
      url += `&use_llm_filter=true`
      url += `&llm_model=${encodeURIComponent(aiFilteringModel.value)}`
      url += `&filter_priority=${encodeURIComponent(aiFilteringPriority.value)}`
    }
    const response = await fetchWithAuth(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      throw new Error(`Environment analysis endpoint returned ${response.status}`)
    }
    const data = await response.json()
    if (data.status === 'success') {
      environmentAnalysis.value = {
        total_hardcoded_values: data.total_hardcoded_values || 0,
        high_priority_count: data.high_priority_count || 0,
        recommendations_count: data.recommendations_count || 0,
        categories: data.categories || {},
        analysis_time_seconds: data.analysis_time_seconds || 0,
        hardcoded_values: data.hardcoded_values || [],
        recommendations: data.recommendations || []
      }
      // Issue #633: Store LLM filtering result if present
      if (data.llm_filtering) {
        llmFilteringResult.value = data.llm_filtering
        logger.info('LLM filtering applied:', data.llm_filtering)
      }
    } else if (data.status === 'no_data') {
      // Issue #543: Handle no_data status from backend
      environmentAnalysis.value = null
      logger.debug('No environment analysis data - run indexing first')
    }
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Failed to load environment analysis:', error)
    envAnalysisError.value = errorMessage
  } finally {
    loadingEnvAnalysis.value = false
  }
}

// Issue #248/#1321: Ownership analysis (useAnalyticsFetch)
const loadOwnershipAnalysis = async () => {
  if (!rootPath.value) return
  await _loadOwnership({ path: rootPath.value })
}

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
  // Clean up job polling interval
  stopJobPolling()
})

// Index codebase first
const indexCodebase = async () => {
  // Check if there's already a job running
  if (currentJobId.value) {
    notify(t('analytics.codebase.notify.indexingAlreadyRunning'), 'warning')
    return
  }

  analyzing.value = true
  progressPercent.value = 10
  progressStatus.value = t('analytics.codebase.status.startingIndexing')

  // Save the path to localStorage for persistence across page refreshes
  localStorage.setItem(STORAGE_KEY_PATH, rootPath.value)

  // Clear previous analysis data before starting new indexing
  problemsReport.value = []
  codebaseStats.value = null
  declarationAnalysis.value = []
  duplicateAnalysis.value = []
  hardcodeAnalysis.value = []
  chartData.value = null

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const indexEndpoint = `${backendUrl}/api/analytics/codebase/index`
    const requestBody = JSON.stringify(
      selectedSource.value
        ? { source_id: selectedSource.value.id }
        : { root_path: rootPath.value }
    )

    // Issue #1249: Retry on 502/503 (backend temporarily unavailable)
    const maxRetries = 2
    let response: Response | null = null
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      response = await fetchWithAuth(indexEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: requestBody,
      })
      if (response.status !== 502 && response.status !== 503) break
      if (attempt < maxRetries) {
        const delay = (attempt + 1) * 3
        progressStatus.value = t('analytics.codebase.status.backendRetrying', { delay })
        logger.warn(`Index request got ${response.status}, retrying (${attempt + 1}/${maxRetries})`)
        await new Promise(r => setTimeout(r, delay * 1000))
      }
    }

    if (!response || !response.ok) {
      const errorText = response ? await response.text() : 'No response'
      const status = response?.status ?? 0
      if (status === 502 || status === 503) {
        throw new Error('Backend is temporarily unavailable. Please try again in a moment.')
      }
      throw new Error(`Status ${status}: ${errorText}`)
    }

    const data = await response.json()

    // Check response status
    if (data.status === 'syncing') {
      // Source needs cloning first — sync started, indexing will auto-follow
      progressStatus.value = t('analytics.codebase.status.syncingRepo')
      notify(t('analytics.codebase.notify.syncStarted'), 'info')
      // Poll /index/current until a job appears (sync auto-triggers indexing)
      startJobPolling()
      return
    } else if (data.status === 'already_running') {
      currentJobId.value = data.task_id
      progressStatus.value = t('analytics.codebase.status.monitoringIndexing')
      notify(t('analytics.codebase.notify.indexingMonitoring'), 'info')
    } else if (data.status === 'queued') {
      progressStatus.value = t('analytics.codebase.status.queued', { position: data.position })
      notify(t('analytics.codebase.notify.indexingQueued'), 'info')
      startJobPolling()
      return
    } else {
      currentJobId.value = data.task_id
      progressStatus.value = t('analytics.codebase.status.initializingIndexing')
      notify(t('analytics.codebase.notify.indexingStarted'), 'success')
    }

    // Poll immediately to get initial phases/stats, then continue at interval
    progressPercent.value = 5  // Start lower, let backend report actual progress
    await pollJobStatus()  // Get initial state immediately (don't wait 2s)
    startJobPolling()
  } catch (error: unknown) {
    logger.error('Indexing failed:', error)
    const errorMessage = error instanceof Error ? error.message : String(error)
    progressStatus.value = t('analytics.codebase.status.indexingFailedToStart', { error: errorMessage })
    notify(t('analytics.codebase.notify.indexingFailed', { error: errorMessage }), 'error')
    analyzing.value = false
  }
}


// Get codebase statistics
const getCodebaseStats = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const statsEndpoint = `${backendUrl}/api/analytics/codebase/stats`
    const response = await fetchWithAuth(statsEndpoint)
    if (!response.ok) {
      throw new Error(`Stats endpoint returned ${response.status}`)
    }
    const data = await response.json()
    if (data.status === 'success' && data.stats) {
      codebaseStats.value = data.stats
    } else if (data.status === 'no_data' || data.status === 'indexing') {
      // Issue #543: Handle no_data and indexing status from backend
      codebaseStats.value = null
      logger.debug('No codebase stats - run indexing first')
    }
  } catch (error: unknown) {
    logger.error('Failed to get stats:', error)
  }
}

// Get problems report
const getProblemsReport = async () => {
  loadingProgress.problems = true
  progressStatus.value = t('analytics.codebase.status.analyzingProblems')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const problemsEndpoint = `${backendUrl}/api/analytics/codebase/problems`
    const response = await fetchWithAuth(problemsEndpoint)
    if (!response.ok) {
      throw new Error(`Problems endpoint returned ${response.status}`)
    }
    const data = await response.json()
    // Issue #543: Handle no_data status from backend
    if (data.status === 'no_data') {
      problemsReport.value = []
      logger.debug('No problems report - run indexing first')
    } else {
      problemsReport.value = data.problems || []
    }
  } catch (error: unknown) {
    logger.error('Failed to get problems:', error)
  } finally {
    loadingProgress.problems = false
  }
}

// Get declarations data with improved error handling (debug button)
const getDeclarationsData = async () => {
  const startTime = Date.now()
  loadingProgress.declarations = true
  progressStatus.value = t('analytics.codebase.status.processingDeclarations')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`
    const response = await fetchWithAuth(declarationsEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }
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

// Get duplicates data (debug button)
const getDuplicatesData = async () => {
  loadingProgress.duplicates = true
  progressStatus.value = t('analytics.codebase.status.findingDuplicates')
  const startTime = Date.now()

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`
    const response = await fetchWithAuth(duplicatesEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }
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

// Get hardcodes data (debug button)
const getHardcodesData = async () => {
  loadingProgress.hardcodes = true
  progressStatus.value = t('analytics.codebase.status.detectingHardcodes')
  const startTime = Date.now()

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const hardcodesEndpoint = `${backendUrl}/api/analytics/codebase/hardcodes`
    const response = await fetchWithAuth(hardcodesEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }
    const data = await response.json()
    const responseTime = Date.now() - startTime

    // Store hardcodes data
    hardcodeAnalysis.value = data.hardcodes || []

    const hardcodeCount = hardcodeAnalysis.value.length
    const hardcodeTypes = hardcodeCount > 0 ? [...new Set(hardcodeAnalysis.value.map(h => h.type))].join(', ') : 'none'
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

// Issue #527: Get API Endpoint Coverage Analysis
const getApiEndpointCoverage = async () => {
  loadingApiEndpoints.value = true
  apiEndpointsError.value = ''
  progressStatus.value = t('analytics.codebase.status.scanningApi')
  const startTime = Date.now()

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/endpoint-analysis`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }

    const data = await response.json()
    const responseTime = Date.now() - startTime

    if (data.status === 'success' && data.analysis) {
      apiEndpointAnalysis.value = data.analysis
      const coverage = data.analysis.coverage_percentage?.toFixed(1) || 0
      const orphaned = data.analysis.orphaned_endpoints || 0
      const missing = data.analysis.missing_endpoints || 0
      notify(t('analytics.codebase.notify.apiCoverageResult', { coverage, orphaned, missing, time: responseTime }), 'success')
    } else {
      throw new Error('Invalid response format')
    }
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

// Issue #527: Get coverage color class based on percentage
const getCoverageClass = (percentage: number): string => {
  if (!percentage || percentage < 50) return 'critical'
  if (percentage < 75) return 'warning'
  if (percentage < 90) return 'info'
  return 'success'
}

// Issue #244: Get Cross-Language Pattern Analysis
const getCrossLanguageAnalysis = async () => {
  loadingCrossLanguage.value = true
  crossLanguageError.value = ''
  progressStatus.value = t('analytics.codebase.status.runningCrossLanguage')
  const startTime = Date.now()

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cross-language/summary`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }

    const data = await response.json()
    const responseTime = Date.now() - startTime

    if (data.status === 'success' && data.summary) {
      // Map the summary format to our expected interface
      crossLanguageAnalysis.value = {
        analysis_id: data.summary.analysis_id,
        scan_timestamp: data.summary.scan_timestamp,
        python_files_analyzed: data.summary.files_analyzed?.python || 0,
        typescript_files_analyzed: data.summary.files_analyzed?.typescript || 0,
        vue_files_analyzed: data.summary.files_analyzed?.vue || 0,
        total_patterns: data.summary.issues?.total || 0,
        critical_issues: data.summary.issues?.critical || 0,
        high_issues: data.summary.issues?.high || 0,
        medium_issues: data.summary.issues?.medium || 0,
        low_issues: data.summary.issues?.low || 0,
        dto_mismatches: [],
        validation_duplications: [],
        api_contract_mismatches: [],
        pattern_matches: [],
        analysis_time_ms: data.summary.performance?.analysis_time_ms || 0
      }

      const totalIssues = data.summary.issues?.total || 0
      const critical = data.summary.issues?.critical || 0
      const high = data.summary.issues?.high || 0
      notify(t('analytics.codebase.notify.crossLanguageResult', { total: totalIssues, critical, high, time: responseTime }), 'success')

      // Load detailed data for the groups
      await loadCrossLanguageDetails()
    } else if (data.status === 'empty') {
      // No cached analysis - show empty state (user needs to click Full Scan)
      crossLanguageAnalysis.value = null
      logger.info('Cross-language analysis: No cached data available')
    } else {
      throw new Error('Invalid response format')
    }
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Cross-language analysis failed:', error)
    crossLanguageError.value = errorMessage
    notify(t('analytics.codebase.notify.crossLanguageFailed', { error: errorMessage, time: responseTime }), 'error')
  } finally {
    loadingCrossLanguage.value = false
    if (!analyzing.value) {
      progressStatus.value = t('analytics.codebase.status.ready')
    }
  }
}

// Issue #244: Load detailed cross-language analysis data
const loadCrossLanguageDetails = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')

    // Load DTO mismatches
    const dtoResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cross-language/dto-mismatches`)
    if (dtoResponse.ok) {
      const dtoData = await dtoResponse.json()
      if (dtoData.status === 'success' && crossLanguageAnalysis.value) {
        crossLanguageAnalysis.value.dto_mismatches = dtoData.mismatches || []
      }
    }

    // Load API mismatches
    const apiResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cross-language/api-mismatches`)
    if (apiResponse.ok) {
      const apiData = await apiResponse.json()
      if (apiData.status === 'success' && crossLanguageAnalysis.value) {
        // Map orphaned and missing to our format
        const orphaned = (apiData.orphaned || []).map((m: Record<string, unknown>) => ({ ...m, mismatch_type: 'orphaned_endpoint' }))
        const missing = (apiData.missing || []).map((m: Record<string, unknown>) => ({ ...m, mismatch_type: 'missing_endpoint' }))
        crossLanguageAnalysis.value.api_contract_mismatches = [...missing, ...orphaned]
      }
    }

    // Load validation duplications
    const valResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cross-language/validation-duplications`)
    if (valResponse.ok) {
      const valData = await valResponse.json()
      if (valData.status === 'success' && crossLanguageAnalysis.value) {
        crossLanguageAnalysis.value.validation_duplications = valData.duplications || []
      }
    }

    // Load semantic matches
    const matchResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cross-language/semantic-matches?min_similarity=0.7&limit=20`)
    if (matchResponse.ok) {
      const matchData = await matchResponse.json()
      if (matchData.status === 'success' && crossLanguageAnalysis.value) {
        crossLanguageAnalysis.value.pattern_matches = matchData.matches || []
      }
    }
  } catch (error: unknown) {
    logger.warn('Failed to load some cross-language details:', error)
  }
}

// Issue #244: Run full cross-language analysis (POST to trigger new scan)
const runCrossLanguageAnalysis = async () => {
  loadingCrossLanguage.value = true
  crossLanguageError.value = ''
  progressStatus.value = t('analytics.codebase.status.runningFullCrossLanguage')
  const startTime = Date.now()

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cross-language/analyze`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        use_llm: true,
        use_cache: true
      })
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }

    const data = await response.json()
    const responseTime = Date.now() - startTime

    if (data.status === 'success') {
      notify(t('analytics.codebase.notify.crossLanguageScanComplete', { time: responseTime }), 'success')
      // Reload the summary with fresh data
      await getCrossLanguageAnalysis()
    } else {
      throw new Error(data.message || 'Analysis failed')
    }
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Cross-language analysis scan failed:', error)
    crossLanguageError.value = errorMessage
    notify(t('analytics.codebase.notify.crossLanguageScanFailed', { error: errorMessage, time: responseTime }), 'error')
  } finally {
    loadingCrossLanguage.value = false
    if (!analyzing.value) {
      progressStatus.value = t('analytics.codebase.status.ready')
    }
  }
}

// Issue #244: Get severity badge class for cross-language issues
const getCrossLanguageSeverityClass = (severity: string): string => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'critical'
    case 'high': return 'warning'
    case 'medium': return 'info'
    case 'low': return 'success'
    default: return 'info'
  }
}

// Issue #208: Pattern Analysis event handlers
const onPatternAnalysisComplete = (report: any) => {
  logger.info('Pattern analysis complete:', report?.analysis_summary)
  notify(t('analytics.codebase.notify.patternAnalysisComplete', { count: report?.analysis_summary?.total_patterns_found || 0 }), 'success')
}

const onPatternAnalysisError = (message: string) => {
  logger.error('Pattern analysis error:', message)
  notify(t('analytics.codebase.notify.patternAnalysisError', { error: message }), 'error')
}

// Issue #538: Truncate long config values for display
const truncateValue = (value: string, maxLength = 50): string => {
  if (!value) return 'Unknown'
  const str = String(value)
  if (str.length <= maxLength) return str
  return str.substring(0, maxLength) + '...'
}

// Issue #538: Get CSS class based on risk score
const getRiskClass = (riskScore: number): string => {
  if (riskScore >= 80) return 'item-critical'
  if (riskScore >= 60) return 'item-warning'
  if (riskScore >= 40) return 'item-info'
  return 'item-success'
}

// Issue #538: Format factor name for display
const formatFactorName = (factor: string): string => {
  return factor
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

// Issue #538: Get CSS class based on grade letter
const getGradeClass = (grade: string): string => {
  const gradeUpper = grade?.toUpperCase() || ''
  if (gradeUpper === 'A' || gradeUpper === 'A+') return 'grade-a'
  if (gradeUpper === 'B' || gradeUpper === 'B+') return 'grade-b'
  if (gradeUpper === 'C' || gradeUpper === 'C+') return 'grade-c'
  if (gradeUpper === 'D' || gradeUpper === 'D+') return 'grade-d'
  return 'grade-f'
}

// Issue #527: Format timestamp for display
const formatTimestamp = (timestamp: string | number | Date | undefined): string => {
  if (!timestamp) return 'Unknown'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch {
    return String(timestamp)
  }
}

// Debug function to check data state
const testDataState = () => {
  const summary = {
    analyzing: analyzing.value,
    rootPath: rootPath.value,
    currentJobId: currentJobId.value,
    problems: problemsReport.value?.length || 0,
    declarations: declarationAnalysis.value?.length || 0,
    duplicates: duplicateAnalysis.value?.length || 0,
    stats: codebaseStats.value ? 'Available' : 'Not loaded'
  }

  logger.info('Debug State:', summary)
  notify(t('analytics.codebase.notify.debugState', { analyzing: summary.analyzing, path: summary.rootPath ? 'set' : 'empty', jobId: summary.currentJobId || 'none', problems: summary.problems }), 'info')
}

// Reset stuck state (debug helper)
const resetState = () => {
  analyzing.value = false
  currentJobId.value = null
  currentJobStatus.value = null
  stopJobPolling()
  progressPercent.value = 0
  progressStatus.value = t('analytics.codebase.status.stateReset')
  notify(t('analytics.codebase.notify.stateReset'), 'success')
}

// Issue #1007: NPU health check via backend proxy (avoids CORS/mixed content)
// Issue #1190: Fixed — was using undefined ApiClient, now uses fetchWithAuth
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
    notify(
      t('analytics.codebase.notify.npuStatus', { status: available ? t('analytics.codebase.available') : t('analytics.codebase.notAvailable'), workers: workerCount, time: responseTime }),
      available ? 'success' : 'warning'
    )
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('NPU connection failed:', error)
    notify(t('analytics.codebase.notify.npuFailed', { error: errorMessage, time: responseTime }), 'error')
  }
}

// NEW: Test all endpoints functionality
const testAllEndpoints = async () => {
  progressStatus.value = t('analytics.codebase.status.testingApis')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const results: string[] = []

    // Test declarations
    try {
      const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`
      const response = await fetchWithAuth(declarationsEndpoint)
      results.push(`Declarations: ${response.ok ? '✅' : '❌'} (${response.status})`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      results.push(`Declarations: ❌ (${msg})`)
    }

    // Test duplicates
    try {
      const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`
      const response = await fetchWithAuth(duplicatesEndpoint)
      results.push(`Duplicates: ${response.ok ? '✅' : '❌'} (${response.status})`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      results.push(`Duplicates: ❌ (${msg})`)
    }

    // Test hardcodes
    try {
      const hardcodesEndpoint = `${backendUrl}/api/analytics/codebase/hardcodes`
      const response = await fetchWithAuth(hardcodesEndpoint)
      results.push(`Hardcodes: ${response.ok ? '✅' : '❌'} (${response.status})`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      results.push(`Hardcodes: ❌ (${msg})`)
    }

    // Test NPU (Issue #1190: was /api/monitoring/hardware/npu which returned 404)
    try {
      const npuEndpoint = `${backendUrl}/api/npu/status`
      const response = await fetchWithAuth(npuEndpoint)
      results.push(`NPU: ${response.ok ? '✅' : '❌'} (${response.status})`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      results.push(`NPU: ❌ (${msg})`)
    }

    // Test stats
    try {
      const statsEndpoint = `${backendUrl}/api/analytics/codebase/stats`
      const response = await fetchWithAuth(statsEndpoint)
      results.push(`Stats: ${response.ok ? '✅' : '❌'} (${response.status})`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      results.push(`Stats: ❌ (${msg})`)
    }

    const passed = results.filter(r => r.includes('✅')).length
    const failed = results.filter(r => r.includes('❌')).length
    const summary = t('analytics.codebase.notify.apiTestResults', { passed, total: results.length })
    notify(summary, failed === 0 ? 'success' : 'warning')
    // Log full results to console for detailed review
    logger.debug('API Test Results:', results.join('\n'))
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('API tests failed:', error)
    notify(t('analytics.codebase.notify.apiTestsFailed', { error: errorMessage }), 'error')
  } finally {
    progressStatus.value = t('analytics.codebase.status.ready')
  }
}

// Code Intelligence: Run anti-pattern/code smell analysis
const runCodeSmellAnalysis = async () => {
  const startTime = Date.now()
  codeSmellsAnalysisType.value = 'smells'

  // Issue #1190: Code sources are cloned on SLM server (.19), not the analysis backend (.20).
  // When rootPath is a code-source UUID path, the analysis server returns 400.
  // Show a clear error rather than crashing.
  const analysisPath = rootPath.value
  if (analysisPath.includes('/data/code-sources/')) {
    notify(
      t('analytics.codebase.notify.codeIntelLocalPathRequired'),
      'warning'
    )
    return
  }

  analyzingCodeSmells.value = true
  progressStatus.value = t('analytics.codebase.status.scanningCodeSmells')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const analyzeEndpoint = `${backendUrl}/api/code-intelligence/analyze`
    const response = await fetchWithAuth(analyzeEndpoint, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        path: analysisPath,
        exclude_dirs: ['node_modules', '.venv', '__pycache__', '.git', 'archives'],
        min_severity: 'low'  // Show low and above
      })
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    codeSmellsReport.value = data.report
    const totalIssues = data.report?.anti_patterns?.length || 0
    const filesAnalyzed = data.report?.total_files || 0
    notify(t('analytics.codebase.notify.codeSmellsFound', { count: totalIssues, files: filesAnalyzed, time: responseTime }), totalIssues > 0 ? 'warning' : 'success')
    progressStatus.value = t('analytics.codebase.status.codeSmellsComplete', { count: totalIssues })
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Code smell analysis failed:', error)
    notify(t('analytics.codebase.notify.codeSmellsFailed', { error: errorMessage, time: responseTime }), 'error')
    progressStatus.value = t('analytics.codebase.status.codeSmellsFailed')
  } finally {
    analyzingCodeSmells.value = false
  }
}

// Code Intelligence: Get codebase health score
const getCodeHealthScore = async () => {
  const startTime = Date.now()
  codeSmellsAnalysisType.value = 'health'

  // Issue #1190: Code sources are on SLM server — guard against invalid path
  const analysisPath = rootPath.value
  if (analysisPath.includes('/data/code-sources/')) {
    notify(
      t('analytics.codebase.notify.healthScoreLocalPathRequired'),
      'warning'
    )
    return
  }

  analyzingCodeSmells.value = true
  progressStatus.value = t('analytics.codebase.status.calculatingHealth')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const healthEndpoint = `${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(analysisPath)}`
    const response = await fetchWithAuth(healthEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      }
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }
    const data = await response.json()
    const responseTime = Date.now() - startTime
    codeHealthScore.value = data
    const score = data.health_score || 0
    const grade = data.grade || 'N/A'
    const issues = data.total_issues || 0
    notify(t('analytics.codebase.notify.healthScoreResult', { score, grade, issues, time: responseTime }), score >= 70 ? 'success' : 'warning')
    progressStatus.value = t('analytics.codebase.status.healthScoreResult', { score, grade })
  } catch (error: unknown) {
    const responseTime = Date.now() - startTime
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Health score failed:', error)
    notify(t('analytics.codebase.notify.healthScoreFailed', { error: errorMessage, time: responseTime }), 'error')
    progressStatus.value = t('analytics.codebase.status.healthScoreFailed')
  } finally {
    analyzingCodeSmells.value = false
  }
}

// Export analysis report as Markdown
// Use quick=true by default for fast export (skips expensive analyses)
// Set quick=false for comprehensive report with bug prediction, duplicates, API analysis
const exportReport = async (quick: boolean = true) => {
  exportingReport.value = true
  progressStatus.value = quick ? t('analytics.codebase.status.generatingQuickReport') : t('analytics.codebase.status.generatingFullReport')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    // Use quick mode by default for responsive UI - skips expensive analyses
    const reportEndpoint = `${backendUrl}/api/analytics/codebase/report?format=markdown&quick=${quick}`
    const response = await fetchWithAuth(reportEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'text/markdown'
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }

    // Get the markdown content
    const reportContent = await response.text()

    // Create a blob and download it
    const blob = new Blob([reportContent], { type: 'text/markdown;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const reportType = quick ? 'quick' : 'full'
    link.download = `code-analysis-report-${reportType}-${timestamp}.md`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    notify(t('analytics.codebase.notify.reportExported'), 'success')
    progressStatus.value = t('analytics.codebase.status.reportExported')
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Report export failed:', error)
    notify(t('analytics.codebase.notify.reportExportFailed', { error: errorMessage }), 'error')
    progressStatus.value = t('analytics.codebase.status.reportExportFailed')
  } finally {
    exportingReport.value = false
  }
}

// Issue #609: Export individual section data as MD or JSON
type SectionType = 'bug-prediction' | 'code-smells' | 'problems' | 'duplicates' |
                   'declarations' | 'api-endpoints' | 'cross-language' | 'config-duplicates' |
                   'code-intelligence' | 'environment' | 'statistics' | 'ownership'

const exportSection = async (section: SectionType, format: 'md' | 'json' = 'md') => {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  let data: unknown = null
  let filename = ''
  let content = ''

  // Get section data
  switch (section) {
    case 'bug-prediction':
      data = bugPredictionAnalysis.value
      filename = `bug-prediction-${timestamp}`
      break
    case 'code-smells':
      data = codeSmellsReport.value
      filename = `code-smells-${timestamp}`
      break
    case 'problems':
      data = problemsReport.value
      filename = `problems-report-${timestamp}`
      break
    case 'duplicates':
      data = duplicateAnalysis.value
      filename = `duplicate-analysis-${timestamp}`
      break
    case 'declarations':
      data = declarationAnalysis.value
      filename = `declarations-${timestamp}`
      break
    case 'api-endpoints':
      data = apiEndpointAnalysis.value
      filename = `api-endpoints-${timestamp}`
      break
    case 'cross-language':
      data = crossLanguageAnalysis.value
      filename = `cross-language-${timestamp}`
      break
    case 'config-duplicates':
      data = configDuplicatesAnalysis.value
      filename = `config-duplicates-${timestamp}`
      break
    case 'code-intelligence':
      data = codeHealthScore.value
      filename = `code-intelligence-scores-${timestamp}`
      break
    case 'environment':
      // Issue #631: Fetch full data from export endpoint to avoid truncation
      try {
        const backendUrl = await appConfig.getServiceUrl('backend')
        const exportResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/env-analysis/export`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        })
        if (exportResponse.ok) {
          data = await exportResponse.json()
          logger.info('Environment export: fetched full data from export endpoint', {
            total_in_export: (data as { total_in_export?: number }).total_in_export,
            total_in_analysis: (data as { total_in_analysis?: number }).total_in_analysis,
          })
        } else {
          // Fallback to cached display data if export fails
          logger.warn('Environment export: export endpoint failed, using display data')
          notify(t('analytics.codebase.notify.usingCachedData'), 'warning')
          data = environmentAnalysis.value
        }
      } catch (err) {
        // Fallback to cached display data
        logger.warn('Environment export: fetch failed, using display data', err)
        notify(t('analytics.codebase.notify.exportEndpointUnavailable'), 'warning')
        data = environmentAnalysis.value
      }
      filename = `environment-analysis-${timestamp}`
      break
    case 'ownership':
      data = ownershipAnalysis.value
      filename = `ownership-analysis-${timestamp}`
      break
    case 'statistics':
      data = codebaseStats.value
      filename = `codebase-statistics-${timestamp}`
      break
    default:
      notify(t('analytics.codebase.notify.unknownSectionType'), 'error')
      return
  }

  if (!data) {
    notify(t('analytics.codebase.notify.noDataAvailable', { section }), 'warning')
    return
  }

  // Format content based on requested format
  if (format === 'json') {
    content = JSON.stringify(data, null, 2)
    filename += '.json'
  } else {
    // Generate Markdown
    content = generateSectionMarkdown(section, data)
    filename += '.md'
  }

  // Download file
  const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/markdown' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)

  notify(t('analytics.codebase.notify.sectionExported', { section, format: format.toUpperCase() }), 'success')
}

// Generate markdown for a section
const generateSectionMarkdown = (section: SectionType, data: unknown): string => {
  const now = new Date().toISOString()
  let md = `# ${section.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')} Report\n\n`
  md += `**Generated:** ${now}\n\n`

  switch (section) {
    case 'bug-prediction': {
      const bp = data as { total_files?: number; high_risk_count?: number; files?: Array<{ file_path: string; risk_score: number; risk_level: string }> }
      md += `## Summary\n\n`
      md += `- **Total Files Analyzed:** ${bp.total_files || 0}\n`
      md += `- **High Risk Files:** ${bp.high_risk_count || 0}\n\n`
      if (bp.files && bp.files.length > 0) {
        md += `## Files by Risk\n\n`
        md += `| File | Risk Score | Risk Level |\n`
        md += `|------|------------|------------|\n`
        bp.files.forEach(f => {
          md += `| ${f.file_path} | ${f.risk_score} | ${f.risk_level} |\n`
        })
      }
      break
    }
    case 'code-smells': {
      const cs = data as { summary?: { total_smells: number }; smells_by_severity?: Record<string, number> }
      md += `## Summary\n\n`
      md += `- **Total Code Smells:** ${cs.summary?.total_smells || 0}\n\n`
      if (cs.smells_by_severity) {
        md += `## By Severity\n\n`
        Object.entries(cs.smells_by_severity).forEach(([severity, count]) => {
          md += `- **${severity}:** ${count}\n`
        })
      }
      break
    }
    case 'problems': {
      // Fix #612: Use correct property names from Problem interface
      const probs = data as Array<{
        file_path: string
        severity: string
        message?: string
        description?: string
        line?: number
        line_number?: number
        problem_type?: string
      }>
      md += `## Total Problems: ${probs.length}\n\n`
      if (probs.length > 0) {
        md += `| File | Severity | Line | Message |\n`
        md += `|------|----------|------|----------|\n`
        probs.forEach(p => {
          const lineNum = p.line || p.line_number || '-'
          const msg = p.message || p.description || ''
          md += `| ${p.file_path || 'unknown'} | ${p.severity || 'unknown'} | ${lineNum} | ${msg} |\n`
        })
      }
      break
    }
    case 'statistics': {
      const stats = data as Record<string, unknown>
      md += `## Codebase Statistics\n\n`
      const statsObj = stats as { stats?: Record<string, unknown> }
      const s = statsObj.stats || stats
      md += `| Metric | Value |\n`
      md += `|--------|-------|\n`
      md += `| Total Files | ${(s as Record<string, number>).total_files?.toLocaleString() || 0} |\n`
      md += `| Python Files | ${(s as Record<string, number>).python_files?.toLocaleString() || 0} |\n`
      md += `| TypeScript Files | ${(s as Record<string, number>).typescript_files?.toLocaleString() || 0} |\n`
      md += `| Vue Files | ${(s as Record<string, number>).vue_files?.toLocaleString() || 0} |\n`
      md += `| Total Lines | ${(s as Record<string, number>).total_lines?.toLocaleString() || 0} |\n`
      md += `| Total Functions | ${(s as Record<string, number>).total_functions?.toLocaleString() || 0} |\n`
      md += `| Total Classes | ${(s as Record<string, number>).total_classes?.toLocaleString() || 0} |\n`
      break
    }
    case 'duplicates': {
      const dups = data as Array<{ file1: string; file2: string; similarity: number; lines: number }>
      md += `## Duplicate Code Analysis\n\n`
      md += `**Total Duplicate Pairs Found:** ${dups.length}\n\n`
      if (dups.length > 0) {
        md += `| File 1 | File 2 | Similarity | Lines |\n`
        md += `|--------|--------|------------|-------|\n`
        dups.forEach(d => {
          md += `| ${d.file1} | ${d.file2} | ${(d.similarity * 100).toFixed(1)}% | ${d.lines} |\n`
        })
      }
      break
    }
    case 'declarations': {
      const decls = data as Array<{ file: string; name: string; type: string; line: number }>
      md += `## Code Declarations\n\n`
      md += `**Total Declarations:** ${decls.length}\n\n`
      if (decls.length > 0) {
        md += `| File | Name | Type | Line |\n`
        md += `|------|------|------|------|\n`
        decls.forEach(d => {
          md += `| ${d.file} | ${d.name} | ${d.type} | ${d.line} |\n`
        })
      }
      break
    }
    case 'api-endpoints': {
      const api = data as { total_endpoints?: number; endpoints?: Array<{ path: string; method: string; file: string }> }
      md += `## API Endpoint Analysis\n\n`
      md += `**Total Endpoints:** ${api.total_endpoints || api.endpoints?.length || 0}\n\n`
      if (api.endpoints && api.endpoints.length > 0) {
        md += `| Method | Path | File |\n`
        md += `|--------|------|------|\n`
        api.endpoints.forEach(e => {
          md += `| ${e.method} | ${e.path} | ${e.file} |\n`
        })
      }
      break
    }
    case 'cross-language': {
      const cl = data as { dto_mismatches?: unknown[]; api_mismatches?: unknown[]; validation_duplications?: unknown[] }
      md += `## Cross-Language Pattern Analysis\n\n`
      md += `| Category | Count |\n`
      md += `|----------|-------|\n`
      md += `| DTO Mismatches | ${cl.dto_mismatches?.length || 0} |\n`
      md += `| API Mismatches | ${cl.api_mismatches?.length || 0} |\n`
      md += `| Validation Duplications | ${cl.validation_duplications?.length || 0} |\n\n`
      md += `### Details\n\n`
      md += '```json\n' + JSON.stringify(data, null, 2) + '\n```\n'
      break
    }
    case 'config-duplicates': {
      const cfg = data as { duplicates?: Array<{ key: string; files: string[]; count: number }> }
      md += `## Configuration Duplicates\n\n`
      md += `**Total Duplicates:** ${cfg.duplicates?.length || 0}\n\n`
      if (cfg.duplicates && cfg.duplicates.length > 0) {
        md += `| Config Key | Files | Occurrences |\n`
        md += `|------------|-------|-------------|\n`
        cfg.duplicates.forEach(d => {
          md += `| ${d.key} | ${d.files.join(', ')} | ${d.count} |\n`
        })
      }
      break
    }
    case 'environment': {
      // Issue #631: Updated to handle new export format with hardcoded_values
      // Issue #706: Fixed field names to match backend API response
      // Backend returns 'file' and 'line', not 'file_path' and 'line_number'
      interface EnvExportData {
        total_in_export?: number
        total_in_analysis?: number
        total_hardcoded_values?: number
        high_priority_count?: number
        categories?: Record<string, number>
        hardcoded_values?: Array<{
          type: string
          severity: string
          value: string
          file?: string           // Backend returns 'file', not 'file_path'
          line?: number           // Backend returns 'line', not 'line_number'
          variable_name?: string
          suggested_env_var?: string
          context?: string
          current_usage?: string
        }>
        recommendations?: Array<{
          priority?: string
          description?: string
          env_var_name?: string
        }>
      }
      const env = data as EnvExportData

      md += `## Environment Analysis Report\n\n`

      // Summary section
      md += `### Summary\n\n`
      const totalItems = env.total_in_export ?? env.total_hardcoded_values ?? 0
      const totalAnalysis = env.total_in_analysis ?? env.total_hardcoded_values ?? 0
      md += `- **Total Items Exported:** ${totalItems.toLocaleString()}\n`
      if (env.total_in_analysis && env.total_in_export !== env.total_in_analysis) {
        md += `- **Total in Analysis:** ${totalAnalysis.toLocaleString()}\n`
      }
      if (env.high_priority_count !== undefined) {
        md += `- **High Priority Items:** ${env.high_priority_count}\n`
      }
      md += `\n`

      // Categories breakdown
      if (env.categories && Object.keys(env.categories).length > 0) {
        md += `### Categories\n\n`
        md += `| Category | Count |\n`
        md += `|----------|-------|\n`
        Object.entries(env.categories).forEach(([cat, count]) => {
          md += `| ${cat} | ${count} |\n`
        })
        md += `\n`
      }

      // Hardcoded values - group by severity
      if (env.hardcoded_values && env.hardcoded_values.length > 0) {
        const byPriority = { high: [], medium: [], low: [] } as Record<string, typeof env.hardcoded_values>
        env.hardcoded_values.forEach(v => {
          const sev = (v.severity || 'low').toLowerCase()
          if (!byPriority[sev]) byPriority[sev] = []
          byPriority[sev].push(v)
        })

        // High priority first
        if (byPriority.high.length > 0) {
          md += `### 🔴 High Priority (${byPriority.high.length})\n\n`
          md += `| Type | Value | File | Line |\n`
          md += `|------|-------|------|------|\n`
          byPriority.high.forEach(v => {
            const val = String(v.value).substring(0, 50) + (String(v.value).length > 50 ? '...' : '')
            md += `| ${v.type} | \`${val}\` | ${v.file || '-'} | ${v.line || '-'} |\n`
          })
          md += `\n`
        }

        if (byPriority.medium.length > 0) {
          md += `### 🟡 Medium Priority (${byPriority.medium.length})\n\n`
          md += `| Type | Value | File | Line |\n`
          md += `|------|-------|------|------|\n`
          byPriority.medium.forEach(v => {
            const val = String(v.value).substring(0, 50) + (String(v.value).length > 50 ? '...' : '')
            md += `| ${v.type} | \`${val}\` | ${v.file || '-'} | ${v.line || '-'} |\n`
          })
          md += `\n`
        }

        if (byPriority.low.length > 0) {
          md += `### 🟢 Low Priority (${byPriority.low.length})\n\n`
          md += `| Type | Value | File | Line |\n`
          md += `|------|-------|------|------|\n`
          byPriority.low.forEach(v => {
            const val = String(v.value).substring(0, 50) + (String(v.value).length > 50 ? '...' : '')
            md += `| ${v.type} | \`${val}\` | ${v.file || '-'} | ${v.line || '-'} |\n`
          })
          md += `\n`
        }
      }

      // Recommendations
      if (env.recommendations && env.recommendations.length > 0) {
        md += `### Recommendations\n\n`
        env.recommendations.forEach((rec, i) => {
          md += `${i + 1}. **[${rec.priority || 'medium'}]** ${rec.description || ''}`
          if (rec.env_var_name) {
            md += ` → \`${rec.env_var_name}\``
          }
          md += `\n`
        })
      }
      break
    }
    case 'code-intelligence': {
      const ci = data as { security_score?: number; performance_score?: number; maintainability_score?: number }
      md += `## Code Intelligence Scores\n\n`
      md += `| Metric | Score |\n`
      md += `|--------|-------|\n`
      md += `| Security | ${ci.security_score || 'N/A'} |\n`
      md += `| Performance | ${ci.performance_score || 'N/A'} |\n`
      md += `| Maintainability | ${ci.maintainability_score || 'N/A'} |\n`
      break
    }
    case 'ownership': {
      const own = data as OwnershipAnalysisResult
      md += `## Code Ownership & Expertise Map\n\n`
      md += `### Summary\n\n`
      md += `- **Total Files Analyzed:** ${own.summary.total_files}\n`
      md += `- **Total Contributors:** ${own.summary.total_contributors}\n`
      md += `- **Knowledge Gaps:** ${own.summary.knowledge_gaps_count}\n`
      md += `- **Critical Gaps:** ${own.summary.critical_gaps}\n\n`
      md += `### Metrics\n\n`
      md += `- **Bus Factor:** ${own.metrics.overall_bus_factor}\n`
      md += `- **Ownership Concentration:** ${own.metrics.ownership_concentration}%\n`
      md += `- **Team Coverage:** ${own.metrics.team_coverage}%\n\n`
      if (own.expertise_scores.length > 0) {
        md += `### Top Contributors\n\n`
        md += `| Rank | Name | Lines | Score |\n`
        md += `|------|------|-------|-------|\n`
        own.expertise_scores.slice(0, 10).forEach((e, i) => {
          md += `| ${i + 1} | ${e.author_name} | ${e.total_lines.toLocaleString()} | ${e.overall_score.toFixed(0)} |\n`
        })
        md += `\n`
      }
      if (own.knowledge_gaps.length > 0) {
        md += `### Knowledge Gaps\n\n`
        own.knowledge_gaps.slice(0, 10).forEach(g => {
          md += `- **[${g.risk_level.toUpperCase()}]** ${g.area}: ${g.description}\n`
        })
      }
      break
    }
    default:
      // Generic JSON dump for unknown sections
      md += '```json\n' + JSON.stringify(data, null, 2) + '\n```\n'
  }

  return md
}

// Clear analysis cache (both Redis and ChromaDB)
const clearCache = async () => {
  clearingCache.value = true
  progressStatus.value = t('analytics.codebase.status.clearingCache')

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/cache`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`Status ${response.status}: ${errorText}`)
    }

    const result = await response.json()

    // Clear local state as well
    codebaseStats.value = null
    problemsReport.value = []
    declarationAnalysis.value = []
    duplicateAnalysis.value = []
    hardcodeAnalysis.value = []
    chartData.value = null

    notify(t('analytics.codebase.notify.cacheCleared', { count: result.deleted_keys || 0 }), 'success')
    progressStatus.value = t('analytics.codebase.status.cacheCleared')
  } catch (error: unknown) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error('Cache clear failed:', error)
    notify(t('analytics.codebase.notify.cacheClearFailed', { error: errorMessage }), 'error')
    progressStatus.value = t('analytics.codebase.status.cacheClearFailed')
  } finally {
    clearingCache.value = false
  }
}

// Run full analysis - triggers indexing then runs all analyses sequentially.
// Each step runs to completion regardless of whether previous steps failed.
// Progress is always displayed. Each analysis is independently runnable.
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

// Enhanced Analytics Methods (#1304: background task)
const loadSystemOverview = async () => {
  try {
    const ok = await dashboardTask.start()
    if (ok && dashboardTask.result.value) {
      const result = dashboardTask.result.value as Record<string, unknown>

      // Extract relevant data from the comprehensive dashboard response
      const commPatterns = (result.communication_patterns || {}) as Record<string, unknown>
      const perfMetrics = (result.performance_metrics || {}) as Record<string, unknown>
      const sysHealth = (result.system_health || {}) as Record<string, unknown>
      const realtimeMetrics = (result.realtime_metrics || {}) as Record<string, unknown>

      const totalCalls = (commPatterns.total_api_calls as number) || 0
      const avgResponseTime = (commPatterns.avg_response_time as number)
        || (perfMetrics.avg_response_time as number) || 0
      const activeConns = (realtimeMetrics.active_connections as Record<string, unknown>)
      const activeConnections = (sysHealth.active_connections as number)
        || (activeConns?.value as number) || 0

      let healthStatus = 'Unknown'
      if (sysHealth.status) {
        healthStatus = sysHealth.status as string
      } else if (sysHealth.cpu_percent !== undefined) {
        healthStatus = (sysHealth.cpu_percent as number) < 80 ? 'Healthy' : 'Warning'
      }

      systemOverview.value = {
        api_requests_per_minute: totalCalls,
        average_response_time: Math.round(avgResponseTime * 1000),
        active_connections: activeConnections,
        system_health: healthStatus,
      }
    }
  } catch (error: unknown) {
    logger.error('loadSystemOverview failed:', error)
    systemOverview.value = null
  }
}

const loadCommunicationPatterns = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetchWithAuth(`${backendUrl}/api/analytics/communication/patterns`)

    if (!response.ok) {
      throw new Error(`Status ${response.status}`)
    }

    const result = await response.json()

    // Extract WebSocket activity and API patterns
    const wsActivity = result.websocket_activity || {}
    const apiPatterns = result.api_patterns || []
    const totalCalls = result.total_api_calls || 0
    const uniqueEndpoints = result.unique_endpoints || 0

    // Calculate WebSocket connections from activity or use total
    const wsConnections = Object.keys(wsActivity).length || 0

    // Calculate API frequency (calls per minute estimate)
    // Use the pattern data to estimate frequency
    const apiFrequency = apiPatterns.length > 0
      ? Math.round(apiPatterns.reduce((sum: number, p: any) => sum + (p.frequency || 0), 0) / Math.max(apiPatterns.length, 1))
      : totalCalls

    // Estimate data transfer rate from response times and call count
    const avgResponseTime = result.avg_response_time || 0
    const estimatedDataRate = Math.round((totalCalls * avgResponseTime * 10) / 100) / 10 // Rough estimate in KB/s

    communicationPatterns.value = {
      websocket_connections: wsConnections,
      api_call_frequency: apiFrequency,
      data_transfer_rate: estimatedDataRate
    }
  } catch (error: unknown) {
    logger.error('loadCommunicationPatterns failed:', error)
    // Set empty state on error
    communicationPatterns.value = null
  }
}

const loadCodeQuality = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')

    // Fetch health score from quality API
    const healthResponse = await fetchWithAuth(`${backendUrl}/api/quality/health-score`)
    const healthData = healthResponse.ok ? await healthResponse.json() : null

    // Fetch duplicates count
    const duplicatesResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/duplicates`)
    const duplicatesData = duplicatesResponse.ok ? await duplicatesResponse.json() : null

    // Fetch technical debt summary
    const debtResponse = await fetchWithAuth(`${backendUrl}/api/debt/summary`)
    const debtData = debtResponse.ok ? await debtResponse.json() : null

    // Issue #543: Handle no_data status from backend
    // If all primary APIs return no_data, set codeQuality to null
    if (healthData?.status === 'no_data' && debtData?.status === 'no_data') {
      codeQuality.value = null
      logger.debug('No code quality data - run indexing first')
      return
    }

    // Calculate test coverage from testability score
    const testCoverage = healthData?.breakdown?.testability || 0

    const data = {
      overall_score: Math.round(healthData?.overall || 0),
      test_coverage: Math.round(testCoverage),
      code_duplicates: duplicatesData?.total || 0,
      technical_debt: debtData?.summary?.total_hours || 0
    }
    codeQuality.value = data
  } catch (error: unknown) {
    // Silent failure for dashboard cards
    logger.error('loadCodeQuality failed:', error)
  }
}

const loadPerformanceMetrics = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')

    // Fetch performance summary from performance analytics
    const summaryResponse = await fetchWithAuth(`${backendUrl}/api/performance/summary`)
    const summaryData = summaryResponse.ok ? await summaryResponse.json() : null

    // Fetch monitoring status for uptime
    const monitoringResponse = await fetchWithAuth(`${backendUrl}/api/monitoring/status`)
    const monitoringData = monitoringResponse.ok ? await monitoringResponse.json() : null

    // Fetch quality metrics for performance breakdown
    const qualityResponse = await fetchWithAuth(`${backendUrl}/api/quality/health-score`)
    const qualityData = qualityResponse.ok ? await qualityResponse.json() : null

    // Issue #543: Handle no_data status from backend
    if (summaryData?.status === 'no_data' && qualityData?.status === 'no_data') {
      performanceMetrics.value = null
      logger.debug('No performance metrics data - run indexing first')
      return
    }

    // Get performance score from quality breakdown or performance analysis
    const performanceScore = qualityData?.breakdown?.performance || 0
    const efficiencyScore = summaryData?.average_score || performanceScore

    // Get patterns analyzed count as a proxy for activity
    const patternsEnabled = summaryData?.patterns_enabled || 0

    const data = {
      efficiency_score: Math.round(efficiencyScore) || Math.round(performanceScore),
      memory_usage: patternsEnabled > 0 ? patternsEnabled * 15 : 0, // Patterns as memory proxy
      cpu_usage: Math.round(100 - performanceScore), // Inverse of performance
      load_time: monitoringData?.uptime_seconds
        ? Math.round(monitoringData.uptime_seconds)
        : 0
    }
    performanceMetrics.value = data
  } catch (error: unknown) {
    // Silent failure for dashboard cards
    logger.error('loadPerformanceMetrics failed:', error)
  }
}

const refreshAllMetrics = async () => {
  // #1432: Only fetch cached GET endpoints on interval refresh.
  // Background tasks (POST /analyze) are NOT re-triggered here to
  // avoid 409 retry storms when analysis takes longer than the
  // 30-second refresh interval.
  await Promise.all([
    // Enhanced analytics (top section) — all GET-only
    loadCommunicationPatterns(),
    loadCodeQuality(),
    loadPerformanceMetrics(),

    // Codebase analytics (bottom section) — GET-only
    getCodebaseStats(),
    getProblemsReport(),
    loadDeclarations(),
  ])
}

const toggleRealTime = () => {
  if (realTimeEnabled.value) {
    refreshInterval.value = setInterval(refreshAllMetrics, 30000) // 30 seconds
  } else {
    if (refreshInterval.value) {
      clearInterval(refreshInterval.value)
      refreshInterval.value = null
    }
  }
}

// Utility functions
const getScoreClass = (score: number): string => {
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-medium'
  return 'score-low'
}

const getPriorityClass = (severity: string | undefined): string => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'priority-critical'
    case 'high': return 'priority-high'
    case 'medium': return 'priority-medium'
    default: return 'priority-low'
  }
}

/**
 * Helper to get CSS variable value at runtime.
 * Used for JavaScript color values (charts, Cytoscape, D3, etc.)
 * Falls back to provided default for SSR/testing safety.
 */
function getCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

const getSeverityColor = (severity: string | undefined): string => {
  switch (severity?.toLowerCase()) {
    case 'critical': return getCssVar('--color-error-hover', '#dc2626')
    case 'high': return getCssVar('--chart-orange', '#ea580c')
    case 'medium': return getCssVar('--color-warning-hover', '#d97706')
    default: return getCssVar('--color-success-hover', '#059669')
  }
}

const formatProblemType = (type: string | undefined): string => {
  return type?.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()) || 'Unknown'
}

// Group problems by severity for summary view
const problemsBySeverity = computed((): Record<string, Problem[]> => {
  if (!problemsReport.value || problemsReport.value.length === 0) return {}
  const grouped: Record<string, Problem[]> = {}
  const severityOrder = ['critical', 'high', 'medium', 'low']

  for (const problem of problemsReport.value) {
    const severity = problem.severity?.toLowerCase() || 'low'
    if (!grouped[severity]) {
      grouped[severity] = []
    }
    grouped[severity].push(problem)
  }

  // Return in severity order
  const ordered: Record<string, Problem[]> = {}
  for (const sev of severityOrder) {
    if (grouped[sev]) {
      ordered[sev] = grouped[sev]
    }
  }
  return ordered
})

// Problem group with severity counts
interface ProblemGroup {
  problems: Problem[]
  severityCounts: { critical: number; high: number; medium: number; low: number }
}

// Group problems by type, then by severity within each type
const problemsByType = computed((): Record<string, ProblemGroup> => {
  if (!problemsReport.value || problemsReport.value.length === 0) return {}
  const grouped: Record<string, ProblemGroup> = {}

  for (const problem of problemsReport.value) {
    const type = problem.type || 'unknown'
    if (!grouped[type]) {
      grouped[type] = {
        problems: [],
        severityCounts: { critical: 0, high: 0, medium: 0, low: 0 }
      }
    }
    grouped[type].problems.push(problem)
    const sev = problem.severity?.toLowerCase() || 'low'
    if (sev in grouped[type].severityCounts) {
      grouped[type].severityCounts[sev as keyof typeof grouped[typeof type]['severityCounts']]++
    }
  }

  // Sort by total count (highest first)
  return Object.fromEntries(
    Object.entries(grouped).sort((a, b) => b[1].problems.length - a[1].problems.length)
  )
})

// Track which problem groups are expanded
const expandedProblemTypes = ref<Record<string, boolean>>({})

const toggleProblemType = (type: string): void => {
  expandedProblemTypes.value[type] = !expandedProblemTypes.value[type]
}

// Filter code smells from indexed problems
// Issue #609: Code smell types that should appear in the Code Smells section
const CODE_SMELL_TYPES = new Set([
  // Anti-patterns and code smells
  'long_function',
  'debug_code',
  'race_condition',
  // Technical debt
  'technical_debt_bug',
  'technical_debt_todo',
  'technical_debt_fixme',
  'technical_debt_deprecated',
  // Performance issues (code smells)
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

const codeSmellsFromProblems = computed(() => {
  if (!problemsReport.value || problemsReport.value.length === 0) return []
  return problemsReport.value.filter(p =>
    p.type && CODE_SMELL_TYPES.has(p.type)
  )
})

// Adapter: map Problem[] to the shape CodeSmellsSection expects (#1469)
const codeSmellsForPanel = computed(() =>
  codeSmellsFromProblems.value.map(p => ({
    severity: p.severity,
    description: p.description || p.message,
    file_path: p.file_path,
    line_number: p.line_number ?? p.line,
    suggestion: p.suggestion,
    smell_type: p.type,
  }))
)

// Adapter: map Declaration[] to the shape DeclarationsSection expects (#1469)
const declarationsForPanel = computed(() =>
  declarationAnalysis.value.map(d => ({
    name: d.name,
    file_path: d.file_path,
    line_number: d.line_number ?? d.line ?? 0,
    is_exported: d.is_exported ?? false,
    declaration_type: d.type,
  }))
)

// Unified item severity class for consistent styling
const getItemSeverityClass = (severity: string | undefined): string => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'item-critical'
    case 'high': return 'item-high'
    case 'medium': return 'item-medium'
    case 'low': return 'item-low'
    case 'info': return 'item-info'
    default: return 'item-unknown'
  }
}

// All variables and functions are automatically available in <script setup>
// No export default needed in <script setup> syntax
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

.analytics-header {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  margin-bottom: var(--spacing-6);
  box-shadow: var(--shadow-lg);
}

.header-content h2 {
  margin: 0 0 16px 0;
  color: var(--text-on-primary);
  font-size: 1.5em;
  font-weight: var(--font-semibold);
}

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.path-input {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  min-width: 300px;
  font-family: var(--font-mono);
}

.path-input:focus {
  outline: none;
  border-color: var(--color-info-hover);
  box-shadow: var(--shadow-focus);
}

.btn-primary, .btn-secondary, .btn-debug {
  padding: 10px 20px;
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background: var(--chart-green);
  color: var(--text-on-success);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-success-dark);
  transform: translateY(-1px);
}

.btn-secondary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  transform: translateY(-1px);
}

.btn-primary:disabled, .btn-secondary:disabled {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: not-allowed;
  transform: none;
}

.btn-cancel {
  background: var(--color-error-hover);
  color: var(--text-on-error);
  padding: 10px 20px;
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-cancel:hover {
  background: var(--color-error-dark);
  transform: translateY(-1px);
}

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-md);
  transition: color var(--duration-200), background var(--duration-200);
}

.btn-back:hover {
  color: var(--color-info);
  background: var(--bg-tertiary);
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

.debug-controls {
  width: 100%;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.btn-debug {
  font-size: 0.85em;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-debug:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.progress-container {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  border: 1px solid var(--border-default);
}

/* Issue #1190: Idle state — lighter styling when showing last-known status */
.progress-container--idle {
  opacity: 0.85;
  border-color: var(--border-subtle, var(--border-default));
}

.progress-container--idle .progress-title {
  color: var(--text-secondary);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--chart-green);
  font-weight: var(--font-semibold);
}

.job-id {
  color: var(--text-tertiary);
  font-size: 0.8em;
  font-family: var(--font-mono);
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: var(--color-success);
  transition: width 0.3s ease;
  border-radius: var(--radius-default);
}

.progress-fill.indeterminate {
  width: 30%;
  animation: indeterminate 1.5s infinite ease-in-out;
}

@keyframes indeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(400%);
  }
}

.code-smells-progress {
  border-left: 4px solid var(--chart-pink);
}

.code-smells-progress .progress-fill {
  background: var(--chart-purple);
}

.progress-status {
  color: var(--text-primary);
  font-size: 0.9em;
  font-weight: var(--font-medium);
}

/* Phase Progress */
.phase-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.phase-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  font-size: 0.85em;
  transition: var(--transition-all);
}

.phase-item.phase-completed {
  color: var(--chart-green);
  background: var(--color-success-bg-hover);
  border: 1px solid var(--color-success-border);
}

.phase-item.phase-running {
  color: var(--chart-blue);
  background: var(--color-info-bg-hover);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.phase-item.phase-pending {
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.phase-item i {
  font-size: 0.9em;
}

/* Batch Progress */
.batch-progress {
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.batch-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.batch-label {
  color: var(--text-secondary);
  font-size: 0.85em;
}

.batch-count {
  color: var(--chart-green);
  font-weight: var(--font-semibold);
  font-family: var(--font-mono);
}

.batch-bar {
  width: 100%;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.batch-fill {
  height: 100%;
  background: var(--color-success);
  transition: width 0.3s ease;
  border-radius: 3px;
}

/* Live Stats */
.live-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-card);
  border-radius: 6px;
}

.live-stats .stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 0.85em;
}

.live-stats .stat-item i {
  color: var(--chart-blue);
  width: 16px;
  text-align: center;
}

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

/* Unified Accordion Groups */
.accordion-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accordion-group {
  background: var(--bg-card);
  border-radius: 8px;
  border: 1px solid var(--bg-tertiary);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  cursor: pointer;
  background: var(--bg-secondary);
  transition: background 0.2s ease;
}

.accordion-header:hover {
  background: var(--bg-tertiary);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-info i {
  color: var(--text-muted);
  font-size: 0.75em;
  transition: transform 0.2s ease;
}

.header-name {
  font-weight: 600;
  color: var(--text-secondary);
}

.header-count {
  color: var(--text-muted);
  font-size: 0.9em;
}

.header-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* Unified Severity Badges */
.severity-badge {
  font-size: 0.7em;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.severity-badge.critical { background: var(--color-error-bg); color: var(--color-error-light); }
.severity-badge.high { background: var(--color-warning-bg); color: var(--chart-orange-light); }
.severity-badge.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.severity-badge.low { background: var(--color-success-bg); color: var(--color-success-light); }



/* Accordion Items Container */
.accordion-items {
  padding: 12px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Accordion Transition */
.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}

.accordion-enter-to,
.accordion-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* Unified List Items */
.list-item {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 14px 16px;
  border-left: 4px solid var(--text-tertiary);
  transition: all 0.2s ease;
}

.list-item:hover {
  transform: translateX(4px);
  background: var(--bg-secondary);
}

/* List Item Severity Variants */
.list-item.item-critical { border-left-color: var(--color-error); }
.list-item.item-high { border-left-color: var(--chart-orange); }
.list-item.item-medium { border-left-color: var(--color-warning); }
.list-item.item-low { border-left-color: var(--chart-green); }
.list-item.item-info { border-left-color: var(--chart-blue); }

/* Show More / Muted Utilities */
.show-more {
  text-align: center;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  margin-top: 8px;
}

.muted {
  color: var(--text-tertiary);
  font-style: italic;
}

/* Item Header */
.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.item-name {
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

.item-severity {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.item-severity.critical { background: var(--color-error-bg); color: var(--color-error-light); }
.item-severity.high { background: var(--color-warning-bg); color: var(--chart-orange-light); }
.item-severity.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.item-severity.low { background: var(--color-success-bg); color: var(--color-success-light); }
.item-severity.info { background: var(--color-info-dark); color: var(--color-info-light); }

/* Item Content */
.item-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  margin-bottom: 8px;
}

.item-location {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
  margin-bottom: 4px;
}

.item-suggestion {
  color: var(--chart-green);
  font-size: 0.85em;
  padding: 8px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 4px;
  margin-top: 8px;
}

/* Duplicate-specific Styles */
.item-similarity {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.item-similarity.high { background: var(--color-error-bg); color: var(--color-error-light); }
.item-similarity.medium { background: var(--color-warning-bg); color: var(--color-warning-light); }
.item-similarity.low { background: var(--color-success-bg); color: var(--color-success-light); }

.item-lines {
  color: var(--text-muted);
  font-size: 0.8em;
}

.item-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-file {
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

/* Responsive Design */
@media (max-width: 768px) {
  .codebase-analytics {
    padding: 12px;
  }

  .header-controls {
    flex-direction: column;
    align-items: stretch;
  }

  .path-input {
    min-width: unset;
    width: 100%;
  }

  .debug-controls {
    flex-direction: column;
    gap: 8px;
  }

  .btn-debug {
    width: 100%;
    justify-content: center;
  }

  .enhanced-analytics-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .real-time-controls {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .problem-header, .duplicate-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}

/* Charts Section Styles */
.charts-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.charts-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.charts-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.charts-section .section-header h3 i {
  color: var(--chart-blue);
}

.section-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* Category Filter Tabs */
.category-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
  padding: 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.category-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(51, 65, 85, 0.5);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.category-tab:hover {
  background: rgba(71, 85, 105, 0.5);
  color: var(--text-secondary);
  border-color: rgba(100, 116, 139, 0.5);
}

.category-tab.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary);
}

.category-tab i {
  font-size: 0.875rem;
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}

.category-tab.active .tab-count {
  background: rgba(255, 255, 255, 0.2);
}

.charts-loading,
.charts-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 12px;
  color: var(--text-muted);
}

.charts-loading i {
  font-size: 32px;
  color: var(--chart-blue);
}

.charts-error i {
  font-size: 32px;
  color: var(--color-error);
}

.charts-error {
  color: var(--color-error-light);
}

.charts-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.chart-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.summary-stat {
  background: rgba(51, 65, 85, 0.5);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid rgba(71, 85, 105, 0.5);
  transition: all 0.2s ease;
}

.summary-stat:hover {
  background: rgba(51, 65, 85, 0.7);
  border-color: rgba(59, 130, 246, 0.5);
}

.summary-stat.race-highlight {
  background: rgba(249, 115, 22, 0.2);
  border-color: rgba(249, 115, 22, 0.5);
}

.summary-stat.race-highlight:hover {
  background: rgba(249, 115, 22, 0.3);
}

.summary-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-secondary);
  line-height: 1;
}

.summary-stat.race-highlight .summary-value {
  color: var(--chart-orange);
}

.summary-label {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 4px;
  display: block;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

/* Chart items (BaseChart components) - minimal layout adjustment */
.chart-item {
  min-height: 350px;
}

/* Empty state placeholder (when chart has no data) */
.chart-empty-slot {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  min-height: 350px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Responsive charts */
@media (max-width: 1200px) {
  .chart-summary {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .chart-summary {
    grid-template-columns: 1fr;
  }

  .summary-value {
    font-size: 1.5rem;
  }
}

/* Dependency Section Styles */
.dependency-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dependency-section .section-header h3 i {
  color: var(--chart-purple);
}

.dependency-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Circular Dependencies Warning */
.circular-deps-warning {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 16px;
}

.circular-deps-warning .warning-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--color-error-light);
  margin-bottom: 12px;
}

.circular-deps-warning .warning-header i {
  color: var(--color-error);
}

.circular-deps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.circular-dep-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.circular-dep-item i {
  color: var(--color-warning);
}

/* External Dependencies Table */
.external-deps-table {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.external-deps-table h4 {
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.external-deps-table h4 i {
  color: var(--chart-teal);
}

.deps-table-content {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.dep-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(51, 65, 85, 0.4);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dep-row:hover {
  background: rgba(51, 65, 85, 0.6);
}

.dep-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.dep-count {
  font-size: 0.8rem;
  color: var(--text-muted);
  background: rgba(59, 130, 246, 0.2);
  padding: 2px 8px;
  border-radius: 4px;
}

/* Import Tree Section */
.import-tree-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.import-tree-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.import-tree-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-tree-section .section-header h3 i {
  color: var(--chart-teal);
}

.import-tree-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--color-error-light);
}

.import-tree-section .section-error i {
  color: var(--color-error);
}

.import-tree-content {
  margin-top: 16px;
}

/* Call Graph Section */
.call-graph-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.call-graph-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.call-graph-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.call-graph-section .section-header h3 i {
  color: var(--chart-purple);
}

.call-graph-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--color-error-light);
}

.call-graph-section .section-error i {
  color: var(--color-error);
}

.call-graph-content {
  margin-top: 16px;
}

/* Issue #527: API Endpoint Checker Section */
.api-endpoints-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.api-endpoints-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 20px 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
}

.api-endpoints-section h3 i {
  color: var(--chart-blue);
}

.api-endpoints-section .loading-state,
.api-endpoints-section .error-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.api-endpoints-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.api-endpoints-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

/* Coverage Bar */
.coverage-bar-container {
  margin: 20px 0;
  padding: 16px;
  background: rgba(30, 41, 59, 0.8);
  border-radius: 8px;
}

.coverage-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.coverage-value {
  font-weight: 600;
  font-size: 1rem;
}

.coverage-value.success { color: var(--chart-green); }
.coverage-value.info { color: var(--chart-blue); }
.coverage-value.warning { color: var(--color-warning); }
.coverage-value.critical { color: var(--color-error); }

.coverage-bar {
  height: 12px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  overflow: hidden;
}

.coverage-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.3s ease;
}

.coverage-fill.success { background: var(--color-success); }
.coverage-fill.info { background: var(--color-primary); }
.coverage-fill.warning { background: var(--color-warning); }
.coverage-fill.critical { background: var(--color-error); }

/* HTTP Method Badges */
.method-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  margin-right: 8px;
}

.method-badge.get { background: var(--chart-green)20; color: var(--chart-green); border: 1px solid var(--chart-green)40; }
.method-badge.post { background: var(--chart-blue)20; color: var(--chart-blue); border: 1px solid var(--chart-blue)40; }
.method-badge.put { background: var(--color-warning)20; color: var(--color-warning); border: 1px solid var(--color-warning)40; }
.method-badge.patch { background: var(--chart-purple)20; color: var(--chart-purple); border: 1px solid var(--chart-purple)40; }
.method-badge.delete { background: var(--color-error)20; color: var(--color-error); border: 1px solid var(--color-error)40; }
.method-badge.unknown { background: var(--text-tertiary)20; color: var(--text-tertiary); border: 1px solid var(--text-tertiary)40; }

/* API Path Display */
.item-path {
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* Call Count Badge */
.call-count-badge {
  display: inline-block;
  padding: 2px 8px;
  margin-left: auto;
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 500;
}

/* Item Details */
.item-details {
  margin-top: 4px;
  padding: 6px 10px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-style: italic;
}

/* Item Variants for API Endpoints */
.list-item.item-success {
  border-left: 3px solid var(--chart-green);
  background: rgba(34, 197, 94, 0.05);
}

.list-item.item-warning {
  border-left: 3px solid var(--color-warning);
  background: rgba(245, 158, 11, 0.05);
}

.list-item.item-critical {
  border-left: 3px solid var(--color-error);
  background: rgba(239, 68, 68, 0.05);
}

/* Accordion Header Variants */
.accordion-header.success {
  border-left: 3px solid var(--chart-green);
}

.accordion-header.warning {
  border-left: 3px solid var(--color-warning);
}

.accordion-header.critical {
  border-left: 3px solid var(--color-error);
}

/* Severity Badge Variants for API Endpoints */
.severity-badge.success {
  background: rgba(34, 197, 94, 0.2);
  color: var(--chart-green);
}

.severity-badge.warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning);
}

/* Summary Card Variants */
.summary-card.success {
  border-color: var(--chart-green);
}

.summary-card.success .summary-value {
  color: var(--chart-green);
}

.summary-card.info {
  border-color: var(--chart-blue);
}

.summary-card.info .summary-value {
  color: var(--chart-blue);
}

/* Scan Timestamp */
.scan-timestamp {
  margin-top: 16px;
  padding: 8px 12px;
  background: rgba(30, 41, 59, 0.8);
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.scan-timestamp i {
  color: var(--text-muted);
}

/* Issue #244: Cross-Language Pattern Analysis Section */
.cross-language-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.cross-language-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 20px 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
}

.cross-language-section h3 i {
  color: var(--chart-purple);
}

.cross-language-section .loading-state,
.cross-language-section .error-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.cross-language-section .loading-state {
  background: rgba(139, 92, 246, 0.1);
  border: 1px solid rgba(139, 92, 246, 0.3);
  color: var(--chart-purple-light);
}

.cross-language-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

/* Language Breakdown */
.language-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 16px 0;
  padding: 12px;
  background: rgba(30, 41, 59, 0.8);
  border-radius: 8px;
}

.language-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
}

.language-badge.python {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.language-badge.typescript {
  background: rgba(49, 120, 198, 0.2);
  color: var(--chart-blue-light);
  border: 1px solid rgba(49, 120, 198, 0.3);
}

.language-badge.vue {
  background: rgba(66, 184, 131, 0.2);
  color: var(--chart-green);
  border: 1px solid rgba(66, 184, 131, 0.3);
}

/* Cross-language Type Badges */
.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  margin-right: 8px;
  background: rgba(139, 92, 246, 0.2);
  color: var(--chart-purple-light);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

.type-badge.missing {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.type-badge.orphaned {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

/* Validation Type Badge */
.validation-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  margin-right: 8px;
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

/* Similarity Score */
.similarity-score {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.similarity-score.highlight {
  background: rgba(139, 92, 246, 0.2);
  color: var(--chart-purple-light);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

/* Match Type */
.match-type {
  display: inline-block;
  padding: 2px 8px;
  margin-left: 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  background: rgba(100, 116, 139, 0.2);
  color: var(--text-muted);
  border: 1px solid rgba(100, 116, 139, 0.3);
}

/* Item Locations for cross-language */
.item-locations {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  align-items: center;
}

.item-locations .location {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.item-locations .location.python {
  color: var(--color-info);
}

.item-locations .location.typescript {
  color: var(--chart-blue-light);
}

.item-locations .arrow {
  color: var(--text-tertiary);
  font-weight: bold;
}

/* Item Field */
.item-field {
  margin-top: 4px;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.item-field code {
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

/* Item Name */
.item-name {
  color: var(--text-secondary);
  font-weight: 500;
}

/* Item Recommendation */
.item-recommendation {
  margin-top: 6px;
  padding: 8px 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 6px;
  color: var(--color-info-light);
  font-size: 0.8rem;
  border-left: 2px solid var(--chart-blue);
}

/* Analysis Time */
.analysis-time {
  color: var(--text-tertiary);
  font-size: 0.75rem;
  margin-left: 4px;
}

/* Scan Button */
.btn-scan {
  padding: 4px 10px;
  background: var(--chart-purple);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s;
}

.btn-scan:hover:not(:disabled) {
  background: var(--chart-purple-dark);
}

.btn-scan:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Issue #538: Config Duplicates Section */
.config-duplicates-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.config-duplicates-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.config-duplicates-section h3 i {
  color: var(--color-warning);
}

.config-duplicates-section .loading-state,
.config-duplicates-section .error-state,
.config-duplicates-section .success-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.config-duplicates-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.config-duplicates-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.config-duplicates-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.config-duplicates-section .success-state i {
  color: var(--chart-green);
}

.config-duplicates-section .duplicates-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.config-duplicates-section .item-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.config-duplicates-section .config-value-badge {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
  padding: 4px 10px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.85em;
}

.config-duplicates-section .location-count {
  color: var(--text-muted);
  font-size: 0.85em;
}

.config-duplicates-section .item-locations {
  padding-left: 12px;
  border-left: 2px solid rgba(245, 158, 11, 0.3);
}

.config-duplicates-section .location-item {
  color: var(--text-muted);
  font-size: 0.85em;
  padding: 2px 0;
}

.config-duplicates-section .more-locations {
  color: var(--text-tertiary);
  font-size: 0.8em;
  font-style: italic;
  padding-top: 4px;
}

.config-duplicates-section .recommendation-box {
  margin-top: 20px;
  padding: 12px 16px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  color: var(--color-info-light);
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-duplicates-section .recommendation-box i {
  color: var(--color-warning-light);
}

.config-duplicates-section .recommendation-box code {
  background: rgba(30, 41, 59, 0.8);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

/* Issue #538: Bug Prediction Section */
.bug-prediction-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.bug-prediction-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.bug-prediction-section h3 i {
  color: var(--color-error);
}

.bug-prediction-section .loading-state,
.bug-prediction-section .error-state,
.bug-prediction-section .success-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.bug-prediction-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.bug-prediction-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.bug-prediction-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.bug-prediction-section .success-state i {
  color: var(--chart-green);
}

/* Risk Files List */
.bug-prediction-section .risk-files-list {
  margin-top: 20px;
}

.bug-prediction-section .risk-files-list h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  font-weight: 600;
}

.bug-prediction-section .list-item {
  padding: 16px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 4px solid var(--text-tertiary);
  transition: all 0.2s ease;
}

.bug-prediction-section .list-item:hover {
  background: rgba(17, 24, 39, 0.7);
}

.bug-prediction-section .list-item.item-critical {
  border-left-color: var(--color-error);
}

.bug-prediction-section .list-item.item-warning {
  border-left-color: var(--color-warning);
}

.bug-prediction-section .list-item.item-info {
  border-left-color: var(--chart-blue);
}

.bug-prediction-section .list-item.item-success {
  border-left-color: var(--chart-green);
}

.bug-prediction-section .item-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.bug-prediction-section .risk-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.85em;
  min-width: 50px;
  text-align: center;
}

.bug-prediction-section .risk-badge.item-critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.bug-prediction-section .risk-badge.item-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.bug-prediction-section .risk-badge.item-info {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
}

.bug-prediction-section .risk-badge.item-success {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.bug-prediction-section .item-path {
  color: var(--text-secondary);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.9em;
  flex: 1;
  word-break: break-all;
}

.bug-prediction-section .risk-level-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75em;
  text-transform: uppercase;
  font-weight: 600;
}

.bug-prediction-section .risk-level-badge.critical,
.bug-prediction-section .risk-level-badge.high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.bug-prediction-section .risk-level-badge.medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.bug-prediction-section .risk-level-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

/* Risk Factors */
.bug-prediction-section .risk-factors {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.bug-prediction-section .factor-badge {
  padding: 3px 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  font-size: 0.8em;
  color: var(--text-muted);
}

/* Prevention Tips */
.bug-prediction-section .prevention-tips {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 6px;
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.bug-prediction-section .prevention-tips i {
  color: var(--color-warning-light);
  margin-top: 2px;
}

.bug-prediction-section .prevention-tips span {
  color: var(--color-info-light);
  font-size: 0.85em;
  line-height: 1.4;
}

.bug-prediction-section .show-more {
  text-align: center;
  padding: 10px;
}

.bug-prediction-section .show-more .muted {
  color: var(--text-tertiary);
  font-size: 0.85em;
}

/* Enhanced Bug Prediction Styles */
.summary-card.clickable { cursor: pointer; transition: transform 0.2s; }
.summary-card.clickable:hover { transform: translateY(-2px); }
.top-risk-factors-summary { margin: 20px 0; padding: 16px; background: rgba(17, 24, 39, 0.6); border-radius: 10px; border: 1px solid rgba(239, 68, 68, 0.2); }
.top-risk-factors-summary h4 { color: var(--color-error-light); font-size: 1em; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
.top-risk-factors-summary h4 i { color: var(--color-error); }
.risk-factors-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.risk-factor-card { display: flex; align-items: flex-start; gap: 12px; padding: 14px; background: rgba(30, 41, 59, 0.5); border-radius: 8px; border-left: 3px solid var(--text-tertiary); }
.risk-factor-card.critical { border-left-color: var(--color-error); background: rgba(239, 68, 68, 0.1); }
.risk-factor-card.high { border-left-color: var(--chart-orange); background: rgba(249, 115, 22, 0.1); }
.risk-factor-card.medium { border-left-color: var(--color-warning); background: rgba(234, 179, 8, 0.1); }
.risk-factor-card .factor-icon { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; background: rgba(71, 85, 105, 0.4); border-radius: 8px; }
.risk-factor-card .factor-icon i { font-size: 1.1em; color: var(--text-muted); }
.risk-factor-card.critical .factor-icon i { color: var(--color-error-light); }
.risk-factor-card.high .factor-icon i { color: var(--chart-orange-light); }
.risk-factor-card .factor-details { flex: 1; }
.risk-factor-card .factor-name { color: var(--text-primary); font-weight: 600; font-size: 0.95em; margin-bottom: 4px; }
.risk-factor-card .factor-count { color: var(--color-warning-light); font-size: 0.85em; font-weight: 500; margin-bottom: 4px; }
.risk-factor-card .factor-description { color: var(--text-muted); font-size: 0.8em; line-height: 1.4; }
.risk-filter-tabs { display: flex; gap: 8px; margin: 20px 0 16px; flex-wrap: wrap; }
.risk-filter-tabs button { padding: 8px 16px; border: 1px solid rgba(71, 85, 105, 0.5); background: rgba(30, 41, 59, 0.5); color: var(--text-muted); border-radius: 6px; font-size: 0.85em; cursor: pointer; transition: all 0.2s; }
.risk-filter-tabs button:hover:not(:disabled) { background: rgba(71, 85, 105, 0.5); color: var(--text-secondary); }
.risk-filter-tabs button.active { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.5); color: var(--color-info-light); }
.risk-filter-tabs button:disabled { opacity: 0.5; cursor: not-allowed; }
.risk-files-list.detailed h4 { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); margin-bottom: 12px; }
.risk-files-list.detailed h4 .file-count { color: var(--text-tertiary); font-weight: normal; font-size: 0.9em; }
.risk-files-list .no-files-message { padding: 20px; text-align: center; color: var(--color-success-light); background: rgba(34, 197, 94, 0.1); border-radius: 8px; }
.risk-file-item { background: rgba(17, 24, 39, 0.5); border-radius: 8px; margin-bottom: 10px; border-left: 4px solid var(--text-tertiary); overflow: hidden; transition: all 0.2s; }
.risk-file-item.item-critical { border-left-color: var(--color-error); }
.risk-file-item.item-warning { border-left-color: var(--color-warning); }
.risk-file-item.item-info { border-left-color: var(--chart-blue); }
.risk-file-item.item-success { border-left-color: var(--chart-green); }
.risk-file-item.expanded { background: rgba(17, 24, 39, 0.8); }
.risk-file-item .file-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; cursor: pointer; transition: background 0.2s; }
.risk-file-item .file-header:hover { background: rgba(71, 85, 105, 0.2); }
.risk-file-item .file-info { display: flex; align-items: center; gap: 10px; flex: 1; flex-wrap: wrap; }
.risk-file-item .risk-score-badge { padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 0.85em; min-width: 40px; text-align: center; }
.risk-file-item .risk-score-badge.item-critical { background: rgba(239, 68, 68, 0.3); color: var(--color-error-light); }
.risk-file-item .risk-score-badge.item-warning { background: rgba(245, 158, 11, 0.3); color: var(--color-warning-light); }
.risk-file-item .risk-score-badge.item-info { background: rgba(59, 130, 246, 0.3); color: var(--color-info-light); }
.risk-file-item .risk-score-badge.item-success { background: rgba(34, 197, 94, 0.3); color: var(--color-success-light); }
.risk-file-item .file-path { color: var(--text-secondary); font-family: monospace; font-size: 0.85em; flex: 1; word-break: break-all; }
.risk-file-item .risk-level-tag { padding: 2px 8px; border-radius: 4px; font-size: 0.7em; text-transform: uppercase; font-weight: 600; }
.risk-file-item .risk-level-tag.high, .risk-file-item .risk-level-tag.critical { background: rgba(239, 68, 68, 0.2); color: var(--color-error-light); }
.risk-file-item .risk-level-tag.medium { background: rgba(245, 158, 11, 0.2); color: var(--color-warning-light); }
.risk-file-item .risk-level-tag.low, .risk-file-item .risk-level-tag.minimal { background: rgba(34, 197, 94, 0.2); color: var(--color-success-light); }
.risk-file-item .expand-icon { color: var(--text-tertiary); padding: 4px 8px; }
.quick-risk-indicators { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 12px; }
.quick-risk-indicators .indicator { display: flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 500; }
.quick-risk-indicators .indicator.critical { background: rgba(239, 68, 68, 0.2); color: var(--color-error-light); }
.quick-risk-indicators .indicator.high { background: rgba(249, 115, 22, 0.2); color: var(--chart-orange-light); }
.quick-risk-indicators .indicator.warning { background: rgba(234, 179, 8, 0.2); color: var(--color-warning-light); }
.quick-risk-indicators .indicator.info { background: rgba(59, 130, 246, 0.2); color: var(--color-info-light); }
.quick-risk-indicators .indicator.muted { background: rgba(100, 116, 139, 0.2); color: var(--text-muted); }
.file-details { padding: 16px; background: rgba(15, 23, 42, 0.5); border-top: 1px solid rgba(71, 85, 105, 0.3); }
.file-details .detail-section { margin-bottom: 16px; }
.file-details .detail-section:last-child { margin-bottom: 0; }
.file-details h5 { color: var(--text-secondary); font-size: 0.9em; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.file-details h5 i { color: var(--text-tertiary); }
.factors-breakdown { display: flex; flex-direction: column; gap: 8px; }
.factor-row { display: flex; align-items: center; gap: 12px; }
.factor-row .factor-label { width: 140px; color: var(--text-muted); font-size: 0.85em; display: flex; align-items: center; gap: 6px; }
.factor-row .factor-label i { width: 16px; text-align: center; color: var(--text-tertiary); }
.factor-row.high-value .factor-label { color: var(--color-error-light); }
.factor-row.high-value .factor-label i { color: var(--color-error); }
.factor-row.medium-value .factor-label { color: var(--color-warning-light); }
.factor-row .factor-bar-container { flex: 1; height: 8px; background: rgba(71, 85, 105, 0.3); border-radius: 4px; overflow: hidden; }
.factor-row .factor-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.factor-row .factor-bar.bar-critical { background: var(--color-error); }
.factor-row .factor-bar.bar-warning { background: var(--color-warning); }
.factor-row .factor-bar.bar-ok { background: var(--color-success); }
.factor-row .factor-value { width: 40px; text-align: right; font-weight: 600; font-size: 0.85em; color: var(--text-secondary); }
.factor-row.high-value .factor-value { color: var(--color-error-light); }
.factor-row.medium-value .factor-value { color: var(--color-warning-light); }
.tips-list, .tests-list { list-style: none; padding: 0; margin: 0; }
.tips-list li, .tests-list li { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: rgba(30, 41, 59, 0.5); border-radius: 6px; margin-bottom: 6px; font-size: 0.85em; line-height: 1.4; }
.tips-list li i { color: var(--color-warning-light); margin-top: 2px; }
.tips-list li { color: var(--text-secondary); border-left: 3px solid var(--color-warning-light); }
.tests-list li i { color: var(--chart-purple-light); margin-top: 2px; }
.tests-list li { color: var(--chart-purple-light); border-left: 3px solid var(--chart-purple-light); }
.show-more-container { text-align: center; margin-top: 16px; }
.show-more-btn { padding: 10px 24px; background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.4); color: var(--color-info-light); border-radius: 6px; cursor: pointer; font-size: 0.9em; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s; }
.show-more-btn:hover { background: rgba(59, 130, 246, 0.3); }

/* Issue #538: Code Intelligence Scores Section */
.code-intelligence-scores-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.code-intelligence-scores-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 20px;
  font-size: 1.2em;
  font-weight: 600;
}

.code-intelligence-scores-section h3 i {
  color: var(--chart-blue);
}

/* Score Cards Grid */
.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.score-card {
  background: rgba(17, 24, 39, 0.6);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(71, 85, 105, 0.4);
  transition: all 0.2s ease;
}

.score-card:hover {
  border-color: rgba(71, 85, 105, 0.7);
  background: rgba(17, 24, 39, 0.8);
}

.score-card .score-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  font-size: 1.1em;
  font-weight: 600;
  color: var(--text-secondary);
}

.score-card .score-header .card-refresh-btn {
  margin-left: auto;
  padding: 4px 8px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 4px;
  color: var(--color-info-light);
  cursor: pointer;
  font-size: 0.8em;
  transition: all 0.2s ease;
}

.score-card .score-header .card-refresh-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.5);
  color: var(--color-info);
}

.score-card .score-header .card-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.score-card.security-card .score-header i {
  color: var(--color-error);
}

.score-card.performance-card .score-header i {
  color: var(--color-warning);
}

.score-card.redis-card .score-header i {
  color: var(--chart-green);
}

.score-card .score-loading {
  display: flex;
  justify-content: center;
  padding: 30px;
  color: var(--color-info-light);
  font-size: 1.5em;
}

.score-card .score-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 8px;
  color: var(--color-error-light);
  font-size: 0.85em;
}

.score-card .score-error i {
  color: var(--color-error);
}

.score-card .score-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.score-card .score-value {
  font-size: 3em;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 8px;
}

.score-card .score-value.score-high {
  color: var(--chart-green);
}

.score-card .score-value.score-medium {
  color: var(--color-warning);
}

.score-card .score-value.score-low {
  color: var(--color-error);
}

.score-card .score-grade {
  font-size: 1.5em;
  font-weight: 700;
  padding: 4px 16px;
  border-radius: 8px;
  margin-bottom: 10px;
}

.score-card .score-grade.grade-a {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.score-card .score-grade.grade-b {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-success-light);
}

.score-card .score-grade.grade-c {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.score-card .score-grade.grade-d {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error-light);
}

.score-card .score-grade.grade-f {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.score-card .score-status {
  color: var(--text-muted);
  font-size: 0.9em;
  margin-bottom: 12px;
}

.score-card .score-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.score-card .detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.8em;
}

.score-card .detail-item.critical {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.score-card .detail-item.warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.score-card .detail-item.info {
  background: rgba(59, 130, 246, 0.2);
  color: var(--color-info-light);
}

.score-card .score-empty {
  display: flex;
  justify-content: center;
  padding: 30px;
  color: var(--text-tertiary);
  font-style: italic;
}

/* Issue #566: View Details Button */
.view-details-btn {
  width: 100%;
  margin-top: 12px;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(99, 102, 241, 0.4);
  border-radius: 6px;
  color: var(--chart-indigo-light);
  font-size: 0.85em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.view-details-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.3);
  border-color: rgba(99, 102, 241, 0.6);
  color: var(--chart-indigo-light);
}

.view-details-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Issue #566: Findings Panel Styles */
.findings-panel {
  margin-top: 16px;
  background: rgba(30, 41, 59, 0.6);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  overflow: hidden;
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    max-height: 2000px;
    transform: translateY(0);
  }
}

.findings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.8);
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.findings-header h4 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 1.1em;
  font-weight: 600;
}

.security-findings-panel .findings-header h4 i { color: var(--color-error-light); }
.performance-findings-panel .findings-header h4 i { color: var(--color-warning-light); }
.redis-findings-panel .findings-header h4 i { color: var(--color-info); }

.findings-count {
  padding: 4px 12px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 20px;
  color: var(--text-muted);
  font-size: 0.85em;
  font-weight: 500;
}

.findings-loading,
.findings-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: var(--text-muted);
  font-size: 0.95em;
}

.findings-empty i {
  color: var(--chart-green);
  font-size: 1.2em;
}

.findings-list {
  padding: 12px;
  max-height: 500px;
  overflow-y: auto;
}

.finding-item {
  background: rgba(15, 23, 42, 0.6);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 10px;
  border-left: 4px solid var(--text-tertiary);
  transition: all 0.2s ease;
}

.finding-item:last-child {
  margin-bottom: 0;
}

.finding-item:hover {
  background: rgba(15, 23, 42, 0.8);
}

.finding-item.severity-critical {
  border-left-color: var(--color-error);
  background: rgba(239, 68, 68, 0.08);
}

.finding-item.severity-high {
  border-left-color: var(--chart-orange);
  background: rgba(249, 115, 22, 0.08);
}

.finding-item.severity-medium {
  border-left-color: var(--color-warning);
  background: rgba(234, 179, 8, 0.08);
}

.finding-item.severity-low {
  border-left-color: var(--chart-green);
  background: rgba(34, 197, 94, 0.08);
}

.finding-item.severity-info {
  border-left-color: var(--chart-blue);
  background: rgba(59, 130, 246, 0.08);
}

.finding-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.finding-severity {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75em;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.finding-severity.severity-critical {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.finding-severity.severity-high {
  background: rgba(249, 115, 22, 0.3);
  color: var(--chart-orange-light);
}

.finding-severity.severity-medium {
  background: rgba(234, 179, 8, 0.3);
  color: var(--color-warning-light);
}

.finding-severity.severity-low {
  background: rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.finding-severity.severity-info {
  background: rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.finding-type {
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 0.9em;
}

.finding-category {
  padding: 2px 8px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 4px;
  font-size: 0.75em;
  color: var(--text-muted);
}

.finding-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  line-height: 1.5;
  margin-bottom: 10px;
}

.finding-location {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-tertiary);
  font-size: 0.85em;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.finding-location i {
  color: var(--chart-indigo);
}

.finding-location .function-name {
  color: var(--chart-indigo-light);
  font-style: italic;
}

.finding-recommendation {
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 6px;
  border-left: 3px solid var(--chart-green);
  color: var(--color-success-light);
  font-size: 0.85em;
  line-height: 1.4;
}

.finding-recommendation i {
  color: var(--chart-green);
  margin-right: 6px;
}

.finding-owasp {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 0.8em;
}

.finding-owasp i {
  color: var(--chart-orange);
  margin-right: 4px;
}

/* Issue #538: Environment Analysis Section */
.environment-analysis-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.environment-analysis-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.environment-analysis-section h3 i {
  color: var(--chart-green);
}

.environment-analysis-section .loading-state,
.environment-analysis-section .error-state,
.environment-analysis-section .success-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.environment-analysis-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.environment-analysis-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.environment-analysis-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

.environment-analysis-section .success-state i {
  color: var(--chart-green);
}

/* Categories Breakdown */
.environment-analysis-section .categories-breakdown {
  margin-top: 20px;
}

.environment-analysis-section .categories-breakdown h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
}

.environment-analysis-section .category-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.environment-analysis-section .category-badge {
  padding: 4px 10px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  font-size: 0.85em;
  color: var(--text-muted);
}

/* Recommendations List */
.environment-analysis-section .recommendations-list {
  margin-top: 20px;
}

.environment-analysis-section .recommendations-list h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
}

.environment-analysis-section .recommendation-item {
  padding: 14px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  margin-bottom: 10px;
  border-left: 4px solid var(--text-tertiary);
}

.environment-analysis-section .recommendation-item.priority-high {
  border-left-color: var(--color-error);
}

.environment-analysis-section .recommendation-item.priority-medium {
  border-left-color: var(--color-warning);
}

.environment-analysis-section .recommendation-item.priority-low {
  border-left-color: var(--chart-green);
}

.environment-analysis-section .rec-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.environment-analysis-section .env-var-name {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.9em;
}

.environment-analysis-section .priority-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.7em;
  text-transform: uppercase;
  font-weight: 600;
}

.environment-analysis-section .priority-badge.high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.environment-analysis-section .priority-badge.medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.environment-analysis-section .priority-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.environment-analysis-section .rec-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  margin-bottom: 6px;
}

.environment-analysis-section .rec-default {
  color: var(--text-muted);
  font-size: 0.85em;
}

.environment-analysis-section .rec-default code {
  background: rgba(30, 41, 59, 0.8);
  padding: 1px 5px;
  border-radius: 3px;
}

/* Hardcoded Values Preview */
.environment-analysis-section .hardcoded-preview {
  margin-top: 20px;
}

.environment-analysis-section .hardcoded-preview h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
}

/* Issue #631: Truncation warning style */
.environment-analysis-section .truncation-warning {
  font-size: 0.85em;
  color: var(--color-warning);
  font-weight: normal;
  margin-left: 8px;
}

.environment-analysis-section .hardcoded-item {
  padding: 12px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 6px;
  margin-bottom: 8px;
  border-left: 3px solid var(--text-tertiary);
}

.environment-analysis-section .hardcoded-item.severity-high {
  border-left-color: var(--color-error);
}

.environment-analysis-section .hardcoded-item.severity-medium {
  border-left-color: var(--color-warning);
}

.environment-analysis-section .hardcoded-item.severity-low {
  border-left-color: var(--chart-green);
}

.environment-analysis-section .hv-location {
  margin-bottom: 6px;
}

.environment-analysis-section .file-path {
  color: var(--color-info-light);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.85em;
}

.environment-analysis-section .line-number {
  color: var(--text-tertiary);
  font-size: 0.85em;
}

.environment-analysis-section .hv-value {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.environment-analysis-section .hv-value code {
  background: rgba(245, 158, 11, 0.1);
  color: var(--color-warning-light);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
}

.environment-analysis-section .value-type {
  color: var(--text-tertiary);
  font-size: 0.75em;
  text-transform: uppercase;
}

.environment-analysis-section .hv-suggestion {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 4px;
  font-size: 0.85em;
}

.environment-analysis-section .hv-suggestion i {
  color: var(--color-warning-light);
}

.environment-analysis-section .hv-suggestion code {
  color: var(--color-success-light);
  background: transparent;
}

/* Issue #248: Code Ownership and Expertise Map Section */
.ownership-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.ownership-section h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.ownership-section h3 i {
  color: var(--chart-purple-light);
}

.ownership-section .loading-state,
.ownership-section .error-state,
.ownership-section .success-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 8px;
}

.ownership-section .loading-state {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--color-info-light);
}

.ownership-section .error-state {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.ownership-section .success-state {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-success-light);
}

/* Ownership Tabs */
.ownership-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
  padding-bottom: 12px;
}

.ownership-tabs .tab-btn {
  padding: 8px 16px;
  background: rgba(71, 85, 105, 0.3);
  border: 1px solid rgba(71, 85, 105, 0.5);
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9em;
  transition: all 0.2s ease;
}

.ownership-tabs .tab-btn:hover {
  background: rgba(71, 85, 105, 0.5);
  color: var(--text-secondary);
}

.ownership-tabs .tab-btn.active {
  background: rgba(167, 139, 250, 0.2);
  border-color: rgba(167, 139, 250, 0.5);
  color: var(--chart-purple-light);
}

.ownership-tabs .gap-badge {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 0.75em;
}

.ownership-tabs .gap-badge.critical {
  background: rgba(239, 68, 68, 0.5);
}

/* Ownership Overview */
.ownership-overview .ownership-metrics {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ownership-metrics .metric-item {
  display: grid;
  grid-template-columns: 180px 80px 1fr;
  align-items: center;
  gap: 12px;
}

.ownership-metrics .metric-label {
  color: var(--text-muted);
  font-size: 0.9em;
}

.ownership-metrics .metric-value {
  color: var(--text-secondary);
  font-weight: 600;
}

.ownership-metrics .metric-value.high-concentration {
  color: var(--color-warning-light);
}

.ownership-metrics .metric-bar {
  height: 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  overflow: hidden;
}

.ownership-metrics .metric-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.ownership-metrics .metric-bar-fill.ok {
  background: var(--color-success);
}

.ownership-metrics .metric-bar-fill.warning {
  background: var(--color-warning);
}

.ownership-metrics .metric-bar-fill.critical {
  background: var(--color-error);
}

/* Top Contributors Preview */
.top-contributors-preview {
  margin-top: 24px;
}

.top-contributors-preview h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.top-contributors-preview h4 i {
  color: var(--color-warning-light);
}

.contributor-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.contributor-item {
  display: grid;
  grid-template-columns: 40px 1fr 120px 80px;
  align-items: center;
  padding: 10px 14px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.contributor-item .rank {
  color: var(--chart-purple-light);
  font-weight: 600;
}

.contributor-item .name {
  color: var(--text-secondary);
  font-weight: 500;
}

.contributor-item .lines {
  color: var(--text-muted);
  font-size: 0.85em;
  text-align: right;
}

.contributor-item .score {
  color: var(--color-success-light);
  font-weight: 600;
  text-align: right;
}

/* Risk Distribution */
.risk-distribution {
  margin-top: 24px;
}

.risk-distribution h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.risk-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.risk-badge {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.85em;
  font-weight: 500;
}

.risk-badge.risk-low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.risk-badge.risk-medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
  border: 1px solid rgba(245, 158, 11, 0.4);
}

.risk-badge.risk-high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.risk-badge.risk-critical {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
  border: 1px solid rgba(239, 68, 68, 0.6);
}

/* Contributors Tab */
.ownership-contributors {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.expert-card {
  padding: 16px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 10px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.expert-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.expert-rank {
  color: var(--chart-purple-light);
  font-weight: 700;
  font-size: 1.1em;
}

.expert-name {
  color: var(--text-secondary);
  font-weight: 600;
  flex: 1;
}

.expert-score {
  background: var(--chart-purple);
  color: var(--text-on-primary);
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 700;
  font-size: 0.9em;
}

.expert-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.expert-stats .stat {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 0.85em;
}

.expert-stats .stat i {
  color: var(--text-tertiary);
}

.expert-scores {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.score-bar {
  display: grid;
  grid-template-columns: 60px 1fr 40px;
  align-items: center;
  gap: 8px;
}

.score-label {
  color: var(--text-muted);
  font-size: 0.8em;
}

.score-track {
  height: 6px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 3px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 3px;
}

.score-fill.impact {
  background: var(--color-primary);
}

.score-fill.recency {
  background: var(--color-success);
}

.score-value {
  color: var(--text-secondary);
  font-size: 0.8em;
  text-align: right;
}

.expertise-areas {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.area-tag {
  padding: 3px 8px;
  background: rgba(71, 85, 105, 0.4);
  border-radius: 4px;
  font-size: 0.75em;
  color: var(--text-muted);
}

/* Files Tab */
.ownership-files .directories-section,
.ownership-files .files-section {
  margin-bottom: 24px;
}

.ownership-files h4 {
  color: var(--text-secondary);
  font-size: 1em;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ownership-files h4 i {
  color: var(--color-info);
}

.directory-list,
.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.directory-item,
.file-item {
  padding: 12px 14px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 8px;
  border-left: 3px solid var(--color-success-light);
}

.directory-item.risk-medium,
.file-item.risk-medium {
  border-left-color: var(--color-warning-light);
}

.directory-item.risk-high,
.file-item.risk-high {
  border-left-color: var(--color-error-light);
}

.directory-item.risk-critical,
.file-item.risk-critical {
  border-left-color: var(--color-error);
}

.dir-path,
.file-path {
  color: var(--text-secondary);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.9em;
  margin-bottom: 6px;
}

.dir-meta,
.file-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 0.85em;
}

.dir-owner,
.file-owner {
  color: var(--chart-purple-light);
  font-weight: 500;
}

.dir-pct,
.file-pct {
  color: var(--text-muted);
}

.dir-bus-factor,
.file-bus-factor {
  color: var(--color-success-light);
}

.dir-bus-factor.low,
.file-bus-factor.low {
  color: var(--color-error-light);
}

.dir-lines,
.file-lines {
  color: var(--text-tertiary);
}

/* Knowledge Gaps Tab */
.ownership-gaps .gaps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gap-item {
  padding: 16px;
  background: rgba(17, 24, 39, 0.5);
  border-radius: 10px;
  border-left: 4px solid var(--color-error-light);
}

.gap-item.risk-medium {
  border-left-color: var(--color-warning-light);
}

.gap-item.risk-low {
  border-left-color: var(--color-success-light);
}

.gap-item.risk-critical {
  border-left-color: var(--color-error);
  background: rgba(239, 68, 68, 0.05);
}

.gap-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.gap-risk-badge {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 0.75em;
  font-weight: 700;
  text-transform: uppercase;
}

.gap-risk-badge.critical {
  background: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
}

.gap-risk-badge.high {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error-light);
}

.gap-risk-badge.medium {
  background: rgba(245, 158, 11, 0.2);
  color: var(--color-warning-light);
}

.gap-risk-badge.low {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-success-light);
}

.gap-type {
  color: var(--text-muted);
  font-size: 0.9em;
}

.gap-lines {
  color: var(--text-tertiary);
  font-size: 0.85em;
  margin-left: auto;
}

.gap-area {
  color: var(--chart-purple-light);
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 0.9em;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.gap-area i {
  color: var(--text-tertiary);
}

.gap-description {
  color: var(--text-secondary);
  font-size: 0.9em;
  line-height: 1.4;
  margin-bottom: 10px;
}

.gap-recommendation {
  color: var(--color-success-light);
  font-size: 0.85em;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 6px;
}

.gap-recommendation i {
  color: var(--color-warning-light);
  margin-top: 2px;
}

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

/* Scan Runner Progress (#1418) */
.scan-runner-progress {
  margin: var(--spacing-3) 0;
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}
.scan-runner-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}
.scan-runner-title {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}
.scan-runner-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.scan-runner-progress .mini-progress {
  width: 100%;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xs);
  overflow: hidden;
  margin-bottom: var(--spacing-2);
}
.scan-runner-progress .mini-progress-bar {
  height: 100%;
  background: var(--color-purple);
  transition: width 0.3s ease;
}
.scan-runner-items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}
.scan-runner-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: 2px var(--spacing-2);
  font-size: var(--text-xs);
  border-radius: var(--radius-xs);
  background: var(--bg-tertiary);
}
.scan-runner-item.scan-completed { color: var(--color-success); }
.scan-runner-item.scan-failed { color: var(--color-error); }
.scan-runner-item.scan-running { color: var(--color-info); }
.scan-runner-item.scan-skipped { color: var(--text-tertiary); }
.scan-runner-item.scan-pending { color: var(--text-secondary); }
.scan-label {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scan-duration {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}
.scan-error {
  color: var(--color-error);
  font-size: var(--text-xs);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
