<template>
  <div class="codebase-analytics">
    <!-- Header Controls -->
    <div class="analytics-header">
      <div class="header-content">
        <h2><i class="fas fa-code"></i> Real-time Codebase Analytics</h2>
        <div class="header-controls">
          <input
            v-model="rootPath"
            placeholder="/path/to/analyze"
            class="path-input"
            @keyup.enter="runFullAnalysis"
          />
          <button @click="indexCodebase" :disabled="analyzing" class="btn-primary">
            <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-database'"></i>
            {{ analyzing ? 'Indexing...' : 'Index Codebase' }}
          </button>
          <button v-if="analyzing && currentJobId" @click="cancelIndexingJob" class="btn-cancel">
            <i class="fas fa-stop-circle"></i>
            Cancel
          </button>
          <button @click="runFullAnalysis" :disabled="analyzing || !rootPath" class="btn-secondary">
            <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-chart-bar'"></i>
            {{ analyzing ? 'Analyzing...' : 'Analyze All' }}
          </button>

          <!-- Enhanced Debug Controls -->
          <div class="debug-controls" style="margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap;">
            <button @click="getDeclarationsData" class="btn-debug" style="padding: 5px 10px; background: #4CAF50; color: white; border: none; border-radius: 4px;">Test Declarations</button>
            <button @click="getDuplicatesData" class="btn-debug" style="padding: 5px 10px; background: #FF9800; color: white; border: none; border-radius: 4px;">Test Duplicates</button>
            <button @click="getHardcodesData" class="btn-debug" style="padding: 5px 10px; background: #F44336; color: white; border: none; border-radius: 4px;">Test Hardcodes</button>
            <button @click="testNpuConnection" class="btn-debug" style="padding: 5px 10px; background: #9C27B0; color: white; border: none; border-radius: 4px;">Test NPU</button>
            <button @click="testDataState" class="btn-debug" style="padding: 5px 10px; background: #2196F3; color: white; border: none; border-radius: 4px;">Debug State</button>
            <button @click="testAllEndpoints" class="btn-debug" style="padding: 5px 10px; background: #00BCD4; color: white; border: none; border-radius: 4px;">Test All APIs</button>
            <!-- Code Intelligence / Anti-Pattern Detection -->
            <button @click="runCodeSmellAnalysis" :disabled="analyzingCodeSmells" class="btn-debug" style="padding: 5px 10px; background: #E91E63; color: white; border: none; border-radius: 4px;">
              <i :class="analyzingCodeSmells ? 'fas fa-spinner fa-spin' : 'fas fa-bug'"></i>
              {{ analyzingCodeSmells ? 'Scanning...' : 'Code Smells' }}
            </button>
            <button @click="getCodeHealthScore" :disabled="analyzingCodeSmells" class="btn-debug" style="padding: 5px 10px; background: #673AB7; color: white; border: none; border-radius: 4px;">
              <i class="fas fa-heartbeat"></i> Health Score
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Progress Indicator -->
    <div v-if="analyzing" class="progress-container">
      <div class="progress-header">
        <div class="progress-title">
          <i class="fas fa-spinner fa-spin"></i>
          Indexing in Progress
        </div>
        <div v-if="currentJobId" class="job-id">Job: {{ currentJobId.substring(0, 8) }}...</div>
      </div>

      <!-- Phase Progress -->
      <div v-if="jobPhases" class="phase-progress">
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

      <!-- Main Progress Bar -->
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="progress-status">{{ progressStatus }}</div>

      <!-- Batch Progress -->
      <div v-if="jobBatches && jobBatches.total_batches > 0" class="batch-progress">
        <div class="batch-header">
          <span class="batch-label">Batch Progress:</span>
          <span class="batch-count">{{ jobBatches.completed_batches }} / {{ jobBatches.total_batches }}</span>
        </div>
        <div class="batch-bar">
          <div
            class="batch-fill"
            :style="{ width: (jobBatches.completed_batches / jobBatches.total_batches * 100) + '%' }"
          ></div>
        </div>
      </div>

      <!-- Live Stats -->
      <div v-if="jobStats" class="live-stats">
        <div class="stat-item">
          <i class="fas fa-file-code"></i>
          <span>{{ jobStats.files_scanned }} files</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ jobStats.problems_found }} problems</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-code"></i>
          <span>{{ jobStats.functions_found }} functions</span>
        </div>
        <div class="stat-item">
          <i class="fas fa-cubes"></i>
          <span>{{ jobStats.classes_found }} classes</span>
        </div>
        <div class="stat-item" v-if="jobStats.items_stored > 0">
          <i class="fas fa-database"></i>
          <span>{{ jobStats.items_stored }} stored</span>
        </div>
      </div>
    </div>

    <!-- Enhanced Analytics Dashboard Cards -->
    <div class="enhanced-analytics-grid">
      <!-- System Overview -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-tachometer-alt"></i> System Overview</h3>
            <div class="refresh-indicator" :class="{ active: realTimeEnabled }">
              <i class="fas fa-circle"></i>
              {{ realTimeEnabled ? 'Live' : 'Static' }}
            </div>
          </div>
        </template>
        <div v-if="systemOverview" class="metrics-grid">
          <div class="metric-item">
            <div class="metric-label">API Requests/Min</div>
            <div class="metric-value">{{ systemOverview.api_requests_per_minute || 0 }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Avg Response Time</div>
            <div class="metric-value">{{ systemOverview.average_response_time || 0 }}ms</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Active Connections</div>
            <div class="metric-value">{{ systemOverview.active_connections || 0 }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">System Health</div>
            <div class="metric-value" :class="getHealthClass(systemOverview.system_health)">
              {{ systemOverview.system_health || 'Unknown' }}
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-database"
          message="No system metrics available"
        >
          <template #actions>
            <button @click="loadSystemOverview" class="btn-link">Load Metrics</button>
          </template>
        </EmptyState>
      </BasePanel>

      <!-- Communication Patterns -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-network-wired"></i> Communication Patterns</h3>
            <button @click="loadCommunicationPatterns" class="refresh-btn">
              <i class="fas fa-sync"></i>
            </button>
          </div>
        </template>
        <div v-if="communicationPatterns" class="communication-metrics">
          <div class="pattern-item">
            <div class="pattern-label">WebSocket Connections</div>
            <div class="pattern-value">{{ communicationPatterns.websocket_connections || 0 }}</div>
          </div>
          <div class="pattern-item">
            <div class="pattern-label">API Call Frequency</div>
            <div class="pattern-value">{{ communicationPatterns.api_call_frequency || 0 }}/min</div>
          </div>
          <div class="pattern-item">
            <div class="pattern-label">Data Transfer Rate</div>
            <div class="pattern-value">{{ communicationPatterns.data_transfer_rate || 0 }} KB/s</div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-wifi"
          message="No communication data"
        />
      </BasePanel>

      <!-- Code Quality -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-code-branch"></i> Code Quality</h3>
            <button @click="loadCodeQuality" class="refresh-btn">
              <i class="fas fa-sync"></i>
            </button>
          </div>
        </template>
        <div v-if="codeQuality" class="quality-metrics">
          <div class="quality-score" :class="getQualityClass(codeQuality.overall_score)">
            <div class="score-value">{{ codeQuality.overall_score || 0 }}</div>
            <div class="score-label">Overall Score</div>
          </div>
          <div class="quality-details">
            <div class="quality-item">
              <span class="quality-label">Test Coverage:</span>
              <span class="quality-value">{{ codeQuality.test_coverage || 0 }}%</span>
            </div>
            <div class="quality-item">
              <span class="quality-label">Code Duplicates:</span>
              <span class="quality-value">{{ codeQuality.code_duplicates || 0 }}</span>
            </div>
            <div class="quality-item">
              <span class="quality-label">Technical Debt:</span>
              <span class="quality-value">{{ codeQuality.technical_debt || 0 }}h</span>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-star"
          message="No quality metrics"
        />
      </BasePanel>

      <!-- Performance Metrics -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-bolt"></i> Performance Metrics</h3>
            <button @click="loadPerformanceMetrics" class="refresh-btn">
              <i class="fas fa-sync"></i>
            </button>
          </div>
        </template>
        <div v-if="performanceMetrics" class="performance-metrics">
          <div class="performance-gauge" :class="getEfficiencyClass(performanceMetrics.efficiency_score)">
            <div class="gauge-value">{{ performanceMetrics.efficiency_score || 0 }}%</div>
            <div class="gauge-label">Efficiency</div>
          </div>
          <div class="performance-details">
            <div class="performance-item">
              <span class="performance-label">Memory Usage:</span>
              <span class="performance-value">{{ performanceMetrics.memory_usage || 0 }}MB</span>
            </div>
            <div class="performance-item">
              <span class="performance-label">CPU Usage:</span>
              <span class="performance-value">{{ performanceMetrics.cpu_usage || 0 }}%</span>
            </div>
            <div class="performance-item">
              <span class="performance-label">Load Time:</span>
              <span class="performance-value">{{ performanceMetrics.load_time || 0 }}ms</span>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-rocket"
          message="No performance data"
        />
      </BasePanel>
    </div>

    <!-- Traditional Analytics Section -->
    <div class="analytics-section">
      <!-- Real-time Toggle -->
      <div class="real-time-controls">
        <label class="toggle-switch">
          <input type="checkbox" v-model="realTimeEnabled" @change="toggleRealTime">
          <span class="toggle-slider"></span>
          Real-time Updates
        </label>
        <button @click="refreshAllMetrics" class="refresh-all-btn">
          <i class="fas fa-sync-alt"></i> Refresh All
        </button>
      </div>

      <!-- Codebase Statistics -->
      <div class="stats-section">
        <h3><i class="fas fa-chart-pie"></i> Codebase Statistics</h3>
        <div v-if="codebaseStats" class="stats-grid">
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
            <div class="stat-label">Total Files</div>
          </BasePanel>
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_lines || 0 }}</div>
            <div class="stat-label">Lines of Code</div>
          </BasePanel>
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_functions || 0 }}</div>
            <div class="stat-label">Functions</div>
          </BasePanel>
          <BasePanel variant="elevated" size="small">
            <div class="stat-value">{{ codebaseStats.total_classes || 0 }}</div>
            <div class="stat-label">Classes</div>
          </BasePanel>
        </div>
        <EmptyState
          v-else
          icon="fas fa-chart-bar"
          message="No codebase statistics available. Run analysis to generate data."
        />
      </div>

      <!-- Analytics Charts Section -->
      <div class="charts-section">
        <div class="section-header">
          <h3><i class="fas fa-chart-bar"></i> Problem Analytics</h3>
          <button @click="loadChartData" class="refresh-btn" :disabled="chartDataLoading">
            <i :class="chartDataLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>

        <div v-if="chartDataLoading" class="charts-loading">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading chart data...</span>
        </div>

        <div v-else-if="chartDataError" class="charts-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ chartDataError }}</span>
          <button @click="loadChartData" class="btn-link">Retry</button>
        </div>

        <div v-else-if="chartData" class="charts-grid">
          <!-- Summary Stats -->
          <div v-if="chartData.summary" class="chart-summary">
            <div class="summary-stat">
              <span class="summary-value">{{ chartData.summary.total_problems?.toLocaleString() || 0 }}</span>
              <span class="summary-label">Total Problems</span>
            </div>
            <div class="summary-stat">
              <span class="summary-value">{{ chartData.summary.unique_problem_types || 0 }}</span>
              <span class="summary-label">Problem Types</span>
            </div>
            <div class="summary-stat">
              <span class="summary-value">{{ chartData.summary.files_with_problems || 0 }}</span>
              <span class="summary-label">Files Affected</span>
            </div>
            <div class="summary-stat race-highlight">
              <span class="summary-value">{{ chartData.summary.race_condition_count || 0 }}</span>
              <span class="summary-label">Race Conditions</span>
            </div>
          </div>

          <!-- Charts Row 1: Problem Types + Severity -->
          <div class="charts-row">
            <div class="chart-container">
              <ProblemTypesChart
                v-if="chartData.problem_types && chartData.problem_types.length > 0"
                :data="chartData.problem_types"
                title="Problem Types Distribution"
                :height="320"
              />
              <EmptyState v-else icon="fas fa-chart-pie" message="No problem type data" />
            </div>
            <div class="chart-container">
              <SeverityBarChart
                v-if="chartData.severity_counts && chartData.severity_counts.length > 0"
                :data="chartData.severity_counts"
                title="Problems by Severity"
                :height="320"
              />
              <EmptyState v-else icon="fas fa-signal" message="No severity data" />
            </div>
          </div>

          <!-- Charts Row 2: Race Conditions + Top Files -->
          <div class="charts-row">
            <div class="chart-container">
              <RaceConditionsDonut
                v-if="chartData.race_conditions && chartData.race_conditions.length > 0"
                :data="chartData.race_conditions"
                title="Race Conditions by Category"
                :height="320"
              />
              <EmptyState v-else icon="fas fa-exclamation-circle" message="No race condition data" />
            </div>
            <div class="chart-container chart-wide">
              <TopFilesChart
                v-if="chartData.top_files && chartData.top_files.length > 0"
                :data="chartData.top_files"
                title="Top Files with Most Problems"
                :height="400"
                :maxFiles="10"
              />
              <EmptyState v-else icon="fas fa-file-code" message="No file data" />
            </div>
          </div>
        </div>

        <EmptyState
          v-else
          icon="fas fa-chart-area"
          message="No chart data available. Run codebase indexing to generate analytics."
        >
          <template #actions>
            <button @click="indexCodebase" class="btn-primary" :disabled="analyzing">
              <i class="fas fa-database"></i> Index Codebase
            </button>
          </template>
        </EmptyState>
      </div>

      <!-- Dependency Analysis Section -->
      <div class="dependency-section">
        <div class="section-header">
          <h3><i class="fas fa-project-diagram"></i> Dependency Analysis</h3>
          <button @click="loadDependencyData" class="refresh-btn" :disabled="dependencyLoading">
            <i :class="dependencyLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          </button>
        </div>

        <div v-if="dependencyLoading" class="charts-loading">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Analyzing dependencies...</span>
        </div>

        <div v-else-if="dependencyError" class="charts-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ dependencyError }}</span>
          <button @click="loadDependencyData" class="btn-link">Retry</button>
        </div>

        <div v-else-if="dependencyData" class="dependency-grid">
          <!-- Summary Stats -->
          <div v-if="dependencyData.summary" class="chart-summary">
            <div class="summary-stat">
              <span class="summary-value">{{ dependencyData.summary.total_modules?.toLocaleString() || 0 }}</span>
              <span class="summary-label">Python Modules</span>
            </div>
            <div class="summary-stat">
              <span class="summary-value">{{ dependencyData.summary.total_import_relationships?.toLocaleString() || 0 }}</span>
              <span class="summary-label">Import Relationships</span>
            </div>
            <div class="summary-stat">
              <span class="summary-value">{{ dependencyData.summary.external_dependency_count || 0 }}</span>
              <span class="summary-label">External Packages</span>
            </div>
            <div class="summary-stat" :class="{ 'race-highlight': dependencyData.summary.circular_dependency_count > 0 }">
              <span class="summary-value">{{ dependencyData.summary.circular_dependency_count || 0 }}</span>
              <span class="summary-label">Circular Dependencies</span>
            </div>
          </div>

          <!-- Charts Row: External Dependencies + Top Importing Modules -->
          <div class="charts-row">
            <div class="chart-container">
              <DependencyTreemap
                v-if="dependencyData.external_dependencies && dependencyData.external_dependencies.length > 0"
                :data="dependencyData.external_dependencies"
                title="External Dependencies"
                subtitle="Package usage across codebase"
                :height="350"
              />
              <EmptyState v-else icon="fas fa-cube" message="No external dependencies found" />
            </div>
            <div class="chart-container">
              <ModuleImportsChart
                v-if="dependencyData.modules && dependencyData.modules.length > 0"
                :data="dependencyData.modules.filter(m => m.import_count > 0)"
                title="Modules with Most Imports"
                subtitle="Files with highest dependency count"
                :height="350"
                :maxModules="12"
              />
              <EmptyState v-else icon="fas fa-file-import" message="No module data available" />
            </div>
          </div>

          <!-- Circular Dependencies Warning -->
          <div v-if="dependencyData.circular_dependencies && dependencyData.circular_dependencies.length > 0" class="circular-deps-warning">
            <div class="warning-header">
              <i class="fas fa-exclamation-triangle"></i>
              <span>Circular Dependencies Detected</span>
            </div>
            <div class="circular-deps-list">
              <div
                v-for="(cycle, index) in dependencyData.circular_dependencies.slice(0, 10)"
                :key="index"
                class="circular-dep-item"
              >
                <i class="fas fa-sync-alt"></i>
                <span>{{ cycle.join(' ↔ ') }}</span>
              </div>
            </div>
            <div v-if="dependencyData.circular_dependencies.length > 10" class="show-more">
              <span class="muted">and {{ dependencyData.circular_dependencies.length - 10 }} more...</span>
            </div>
          </div>

          <!-- Top External Dependencies Table -->
          <div v-if="dependencyData.external_dependencies && dependencyData.external_dependencies.length > 0" class="external-deps-table">
            <h4><i class="fas fa-cube"></i> Top External Dependencies</h4>
            <div class="deps-table-content">
              <div
                v-for="(dep, index) in dependencyData.external_dependencies.slice(0, 20)"
                :key="index"
                class="dep-row"
              >
                <span class="dep-name">{{ dep.package }}</span>
                <span class="dep-count">{{ dep.usage_count }} imports</span>
              </div>
            </div>
          </div>
        </div>

        <EmptyState
          v-else
          icon="fas fa-project-diagram"
          message="No dependency data available. Click refresh to analyze."
        >
          <template #actions>
            <button @click="loadDependencyData" class="btn-primary" :disabled="dependencyLoading">
              <i class="fas fa-project-diagram"></i> Analyze Dependencies
            </button>
          </template>
        </EmptyState>
      </div>

      <!-- Import Tree Section -->
      <div class="import-tree-section">
        <div class="section-header">
          <h3><i class="fas fa-sitemap"></i> File Import Tree</h3>
          <button @click="loadImportTreeData" class="refresh-btn" :disabled="importTreeLoading">
            <i :class="importTreeLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
            {{ importTreeLoading ? 'Loading...' : 'Refresh' }}
          </button>
        </div>

        <!-- Error state -->
        <div v-if="importTreeError" class="section-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ importTreeError }}</span>
          <button @click="loadImportTreeData" class="btn-link">Retry</button>
        </div>

        <!-- Import Tree Content -->
        <div v-else-if="importTreeData && importTreeData.length > 0" class="import-tree-content">
          <ImportTreeChart
            :data="importTreeData"
            title="File Import Relationships"
            subtitle="Click to expand and see imports/importers"
            :height="500"
            :loading="importTreeLoading"
            :error="importTreeError"
            @navigate="handleFileNavigate"
          />
        </div>

        <!-- Empty state -->
        <EmptyState
          v-else-if="!importTreeLoading"
          icon="fas fa-sitemap"
          message="No import data available yet. Click 'Refresh' to analyze file imports."
          variant="info"
        >
          <template #actions>
            <button @click="loadImportTreeData" class="btn-primary" :disabled="importTreeLoading">
              <i class="fas fa-sitemap"></i> Analyze Imports
            </button>
          </template>
        </EmptyState>
      </div>

      <!-- Function Call Graph Section -->
      <div class="call-graph-section">
        <div class="section-header">
          <h3><i class="fas fa-project-diagram"></i> Function Call Graph</h3>
          <button @click="loadCallGraphData" class="refresh-btn" :disabled="callGraphLoading">
            <i :class="callGraphLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
            {{ callGraphLoading ? 'Loading...' : 'Refresh' }}
          </button>
        </div>

        <!-- Error state -->
        <div v-if="callGraphError" class="section-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ callGraphError }}</span>
          <button @click="loadCallGraphData" class="btn-link">Retry</button>
        </div>

        <!-- Call Graph Content -->
        <div v-else-if="callGraphData && callGraphData.nodes?.length > 0" class="call-graph-content">
          <FunctionCallGraph
            :data="callGraphData"
            :summary="callGraphSummary"
            title="Function Call Relationships"
            subtitle="View which functions call which other functions"
            :height="600"
            :loading="callGraphLoading"
            :error="callGraphError"
            @select="handleFunctionSelect"
          />
        </div>

        <!-- Empty state -->
        <EmptyState
          v-else-if="!callGraphLoading"
          icon="fas fa-project-diagram"
          message="No function call data available. Click 'Refresh' to analyze function calls."
          variant="info"
        >
          <template #actions>
            <button @click="loadCallGraphData" class="btn-primary" :disabled="callGraphLoading">
              <i class="fas fa-project-diagram"></i> Analyze Calls
            </button>
          </template>
        </EmptyState>
      </div>

      <!-- Problems Report -->
      <div class="problems-section">
        <h3><i class="fas fa-exclamation-triangle"></i> Code Problems</h3>
        <div v-if="problemsReport && problemsReport.length > 0" class="problems-list">
          <div
            v-for="(problem, index) in (showAllProblems ? problemsReport : problemsReport.slice(0, 10))"
            :key="index"
            class="problem-item"
            :class="getPriorityClass(problem.severity)"
          >
            <div class="problem-header">
              <span class="problem-type">{{ formatProblemType(problem.type) }}</span>
              <span class="problem-severity" :style="{ color: getSeverityColor(problem.severity) }">
                {{ problem.severity }}
              </span>
            </div>
            <div class="problem-description">{{ problem.description }}</div>
            <div class="problem-file">{{ problem.file_path }}:{{ problem.line_number }}</div>
            <div class="problem-suggestion">💡 {{ problem.suggestion }}</div>
          </div>
          <div v-if="problemsReport.length > 10" class="show-more">
            <button @click="showAllProblems = !showAllProblems" class="btn-link">
              {{ showAllProblems ? 'Show less' : `Show all ${problemsReport.length} problems` }}
            </button>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-check-circle"
          message="No code problems detected or analysis not run yet."
          variant="success"
        />
      </div>

      <!-- Code Intelligence: Anti-Pattern / Code Smells Report -->
      <div class="code-smells-section">
        <h3>
          <i class="fas fa-bug"></i> Code Smells & Anti-Patterns
          <span v-if="codeHealthScore" class="health-badge" :class="getHealthGradeClass(codeHealthScore.grade)">
            {{ codeHealthScore.grade }} ({{ codeHealthScore.health_score }}/100)
          </span>
        </h3>
        <div v-if="codeSmellsReport && codeSmellsReport.anti_patterns && codeSmellsReport.anti_patterns.length > 0" class="code-smells-list">
          <!-- Summary Cards -->
          <div class="smells-summary">
            <div class="summary-card">
              <div class="summary-value">{{ codeSmellsReport.total_files || 0 }}</div>
              <div class="summary-label">Files Analyzed</div>
            </div>
            <div class="summary-card warning">
              <div class="summary-value">{{ codeSmellsReport.anti_patterns.length }}</div>
              <div class="summary-label">Issues Found</div>
            </div>
            <div v-if="codeSmellsReport.severity_distribution" class="summary-card critical">
              <div class="summary-value">{{ codeSmellsReport.severity_distribution.critical || 0 }}</div>
              <div class="summary-label">Critical</div>
            </div>
            <div v-if="codeSmellsReport.severity_distribution" class="summary-card high">
              <div class="summary-value">{{ codeSmellsReport.severity_distribution.high || 0 }}</div>
              <div class="summary-label">High</div>
            </div>
          </div>
          <!-- Anti-Pattern List -->
          <div
            v-for="(pattern, index) in codeSmellsReport.anti_patterns.slice(0, 20)"
            :key="index"
            class="smell-item"
            :class="getSmellSeverityClass(pattern.severity)"
          >
            <div class="smell-header">
              <span class="smell-type">{{ formatSmellType(pattern.pattern_type) }}</span>
              <span class="smell-severity" :class="pattern.severity">{{ pattern.severity }}</span>
            </div>
            <div class="smell-description">{{ pattern.description }}</div>
            <div class="smell-location">📁 {{ pattern.file_path }}:{{ pattern.line_number }}</div>
            <div v-if="pattern.suggestion" class="smell-suggestion">💡 {{ pattern.suggestion }}</div>
          </div>
          <div v-if="codeSmellsReport.anti_patterns.length > 20" class="show-more">
            <span class="muted">Showing 20 of {{ codeSmellsReport.anti_patterns.length }} issues</span>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-sparkles"
          message="No code smells detected. Click 'Code Smells' button to run analysis."
          variant="info"
        />
      </div>

      <!-- Duplicate Code Analysis -->
      <div class="duplicates-section">
        <h3><i class="fas fa-copy"></i> Duplicate Code Detection</h3>
        <div v-if="duplicateAnalysis && duplicateAnalysis.length > 0" class="duplicates-list">
          <div
            v-for="(duplicate, index) in duplicateAnalysis.slice(0, 5)"
            :key="index"
            class="duplicate-item"
          >
            <div class="duplicate-header">
              <span class="duplicate-similarity">{{ duplicate.similarity }}% similar</span>
              <span class="duplicate-lines">{{ duplicate.lines }} lines</span>
            </div>
            <div class="duplicate-files">
              <div class="duplicate-file">📄 {{ duplicate.file1 }}</div>
              <div class="duplicate-file">📄 {{ duplicate.file2 }}</div>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-check-circle"
          message="No duplicate code detected or analysis not run yet."
          variant="success"
        />
      </div>

      <!-- Function Declarations -->
      <div class="declarations-section">
        <h3><i class="fas fa-function"></i> Function Declarations</h3>
        <div v-if="declarationAnalysis && declarationAnalysis.length > 0" class="declarations-list">
          <div
            v-for="(declaration, index) in declarationAnalysis.slice(0, 8)"
            :key="index"
            class="declaration-item"
          >
            <div class="declaration-name">{{ declaration.name }}</div>
            <div class="declaration-type">{{ declaration.type }}</div>
            <div class="declaration-file">{{ declaration.file_path }}:{{ declaration.line_number }}</div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-function"
          message="No function declarations found or analysis not run yet."
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { NetworkConstants } from '@/constants/network.ts'
import EmptyState from '@/components/ui/EmptyState.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { useToast } from '@/composables/useToast'

// ApexCharts components
import {
  ProblemTypesChart,
  SeverityBarChart,
  RaceConditionsDonut,
  TopFilesChart,
  DependencyTreemap,
  ModuleImportsChart,
  ImportTreeChart,
  FunctionCallGraph
} from '@/components/charts'

// Toast notifications
const { showToast } = useToast()

// Notification helper for error handling
const notify = (message, type = 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// Reactive data
// FIXED: Fetch project root from backend config (no hardcoding)
const rootPath = ref('/home/kali/Desktop/AutoBot')
const analyzing = ref(false)
const progressPercent = ref(0)
const progressStatus = ref('Ready')
const realTimeEnabled = ref(false)
const refreshInterval = ref(null)

// Indexing job state tracking
const currentJobId = ref(null)
const currentJobStatus = ref(null)
const jobPollingInterval = ref(null)

// Enhanced progress tracking with phases and batches
const jobPhases = ref(null)
const jobBatches = ref(null)
const jobStats = ref(null)

// Helper to get phase icon based on status
const getPhaseIcon = (status) => {
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

// Analytics data
const codebaseStats = ref(null)
const problemsReport = ref([])
const duplicateAnalysis = ref([])
const declarationAnalysis = ref([])
const refactoringSuggestions = ref([])

// Code Intelligence / Anti-Pattern Detection data
const codeSmellsReport = ref(null)
const codeHealthScore = ref(null)
const analyzingCodeSmells = ref(false)

// Enhanced analytics data
const systemOverview = ref(null)
const communicationPatterns = ref(null)
const codeQuality = ref(null)
const performanceMetrics = ref(null)

// Chart data for visualizations
const chartData = ref(null)
const chartDataLoading = ref(false)
const chartDataError = ref('')

// Dependency analysis data
const dependencyData = ref(null)
const dependencyLoading = ref(false)
const dependencyError = ref('')

// Import tree data
const importTreeData = ref([])
const importTreeLoading = ref(false)
const importTreeError = ref('')

// Function call graph data
const callGraphData = ref({ nodes: [], edges: [] })
const callGraphSummary = ref(null)
const callGraphLoading = ref(false)
const callGraphError = ref('')

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

  // Fetch project root from backend config
  await loadProjectRoot()

  // Check if there's already an indexing job running
  await checkCurrentIndexingJob()

  // Load initial data - Enhanced analytics (top section)
  loadSystemOverview()
  loadCommunicationPatterns()
  loadCodeQuality()
  loadPerformanceMetrics()

  // Load codebase analytics data (bottom section)
  loadCodebaseAnalyticsData()
})

// Check if there's a running indexing job
const checkCurrentIndexingJob = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetch(`${backendUrl}/api/analytics/codebase/index/current`)
    if (response.ok) {
      const data = await response.json()
      if (data.has_active_job) {
        // Job is running - update UI and start polling
        currentJobId.value = data.task_id
        currentJobStatus.value = data.status
        analyzing.value = true
        progressStatus.value = data.progress?.step || 'Indexing in progress...'
        progressPercent.value = data.progress?.percent || 20

        // Start polling for updates
        startJobPolling()
        notify('Indexing job already in progress', 'info')
      } else if (data.task_id && data.status !== 'idle') {
        // Job recently completed
        progressStatus.value = `Last job: ${data.status}`
      }
    }
  } catch (error) {
    console.warn('[CodebaseAnalytics] Could not check for running job:', error.message)
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
    const response = await fetch(`${backendUrl}/api/analytics/codebase/index/current`)
    if (response.ok) {
      const data = await response.json()
      currentJobStatus.value = data.status

      if (data.has_active_job) {
        // Keep analyzing true while job is active
        analyzing.value = true

        // Update progress - use correct field names from backend
        if (data.progress) {
          progressPercent.value = data.progress.percent || 0

          // Build status from operation and current_file
          const operation = data.progress.operation || 'Processing'
          const currentFile = data.progress.current_file || ''
          progressStatus.value = currentFile ? `${operation}: ${currentFile}` : operation
        }

        // Update phase tracking
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

        // Also poll for intermediate results
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
          progressStatus.value = 'Indexing completed!'
          progressPercent.value = 100
          notify('Codebase indexing completed', 'success')

          // Refresh data
          await loadCodebaseAnalyticsData()
        } else if (data.status === 'cancelled') {
          progressStatus.value = 'Indexing cancelled'
          notify('Indexing was cancelled', 'warning')
        } else if (data.status === 'failed' || data.error) {
          progressStatus.value = `Indexing failed: ${data.error || 'Unknown error'}`
          notify(`Indexing failed: ${data.error || 'Unknown error'}`, 'error')
        }

        currentJobId.value = null
      }
    }
  } catch (error) {
    console.warn('[CodebaseAnalytics] Job polling error:', error.message)
  }
}

// Poll for intermediate results during indexing
const pollIntermediateResults = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')

    // Poll for problems found so far
    const problemsResponse = await fetch(`${backendUrl}/api/analytics/codebase/problems`)
    if (problemsResponse.ok) {
      const problemsData = await problemsResponse.json()
      if (problemsData.problems && problemsData.problems.length > 0) {
        problemsReport.value = problemsData.problems
      }
    }

    // Poll for stats
    const statsResponse = await fetch(`${backendUrl}/api/analytics/codebase/stats`)
    if (statsResponse.ok) {
      const statsData = await statsResponse.json()
      if (statsData.stats) {
        codebaseStats.value = statsData.stats
        const filesIndexed = statsData.stats.total_files || 0
        const problemsFound = problemsReport.value.length
        progressStatus.value = `Indexed ${filesIndexed} files, ${problemsFound} problems found...`
      }
    }
  } catch (error) {
    // Silent - don't interrupt polling
  }
}

// Cancel the running indexing job
const cancelIndexingJob = async () => {
  if (!currentJobId.value) {
    notify('No active job to cancel', 'warning')
    return
  }

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetch(`${backendUrl}/api/analytics/codebase/index/cancel`, {
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
        progressStatus.value = 'Indexing cancelled by user'
        notify('Indexing job cancelled', 'success')
      } else {
        notify(data.message || 'Could not cancel job', 'warning')
      }
    } else {
      notify('Failed to cancel job', 'error')
    }
  } catch (error) {
    notify(`Error cancelling job: ${error.message}`, 'error')
  }
}

// Fetch project root from backend configuration
const loadProjectRoot = async () => {
  const { execute: fetchConfig } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const configEndpoint = `${backendUrl}/api/frontend-config`
      const response = await fetch(configEndpoint)
      if (!response.ok) {
        throw new Error(`Failed to fetch config: ${response.status}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (config) => {
        if (config.project && config.project.root_path) {
          rootPath.value = config.project.root_path
        } else {
          console.warn('⚠️ Project root not found in config, using default')
        }
      },
      onError: () => {
        progressStatus.value = 'Please enter project path to analyze'
      }
    }
  )

  await fetchConfig()
}

// Load all codebase analytics data (silent mode - no alerts)
const loadCodebaseAnalyticsData = async () => {

  try {
    // Load all analytics data in parallel (silent mode)
    await Promise.all([
      getCodebaseStats(),
      getProblemsReport(),
      loadDeclarations(),    // Silent version
      loadDuplicates(),      // Silent version
      loadChartData(),       // Load chart data for visualizations
      loadDependencyData(),  // Load dependency analysis
      loadImportTreeData(),  // Load import tree data
      loadCallGraphData()    // Load function call graph
    ])

  } catch (error) {
    console.error('❌ Failed to load codebase analytics data:', error)
    // Provide user feedback for critical failures
    progressStatus.value = `Failed to load analytics: ${error.message}`
  }
}

// Load chart data for visualizations
const loadChartData = async () => {
  chartDataLoading.value = true
  chartDataError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetch(`${backendUrl}/api/analytics/codebase/analytics/charts`, {
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
      console.log('[CodebaseAnalytics] Chart data loaded:', {
        problemTypes: data.chart_data.problem_types?.length || 0,
        severities: data.chart_data.severity_counts?.length || 0,
        raceConditions: data.chart_data.race_conditions?.length || 0,
        topFiles: data.chart_data.top_files?.length || 0
      })
    } else if (data.status === 'no_data') {
      chartData.value = null
      console.log('[CodebaseAnalytics] No chart data available - run indexing first')
    }

  } catch (error) {
    console.error('[CodebaseAnalytics] Failed to load chart data:', error)
    chartDataError.value = error.message
  } finally {
    chartDataLoading.value = false
  }
}

// Load dependency analysis data
const loadDependencyData = async () => {
  dependencyLoading.value = true
  dependencyError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetch(`${backendUrl}/api/analytics/codebase/analytics/dependencies`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`Dependency analysis endpoint returned ${response.status}`)
    }

    const data = await response.json()

    if (data.status === 'success' && data.dependency_data) {
      dependencyData.value = data.dependency_data
      console.log('[CodebaseAnalytics] Dependency data loaded:', {
        modules: data.dependency_data.modules?.length || 0,
        relationships: data.dependency_data.import_relationships?.length || 0,
        externalDeps: data.dependency_data.external_dependencies?.length || 0,
        circularDeps: data.dependency_data.circular_dependencies?.length || 0
      })
    }

  } catch (error) {
    console.error('[CodebaseAnalytics] Failed to load dependency data:', error)
    dependencyError.value = error.message
  } finally {
    dependencyLoading.value = false
  }
}

// Load import tree data for bidirectional file import visualization
const loadImportTreeData = async () => {
  importTreeLoading.value = true
  importTreeError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetch(`${backendUrl}/api/analytics/codebase/analytics/import-tree`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`Import tree endpoint returned ${response.status}`)
    }

    const data = await response.json()

    if (data.status === 'success' && data.import_tree) {
      importTreeData.value = data.import_tree
      console.log('[CodebaseAnalytics] Import tree loaded:', {
        files: data.import_tree.length,
        summary: data.summary
      })
    }

  } catch (error) {
    console.error('[CodebaseAnalytics] Failed to load import tree:', error)
    importTreeError.value = error.message
  } finally {
    importTreeLoading.value = false
  }
}

// Handle file navigation from import tree
const handleFileNavigate = (filePath: string) => {
  console.log('[CodebaseAnalytics] Navigate to file:', filePath)
  // Could scroll to file in problems list or open in editor
  // For now, just log it - can be extended later
  showToast(`Selected: ${filePath}`, 'info', 2000)
}

// Load function call graph data
const loadCallGraphData = async () => {
  callGraphLoading.value = true
  callGraphError.value = ''

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const response = await fetch(`${backendUrl}/api/analytics/codebase/analytics/call-graph`, {
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
      console.log('[CodebaseAnalytics] Call graph loaded:', {
        nodes: data.call_graph.nodes?.length || 0,
        edges: data.call_graph.edges?.length || 0,
        summary: data.summary
      })
    }

  } catch (error) {
    console.error('[CodebaseAnalytics] Failed to load call graph:', error)
    callGraphError.value = error.message
  } finally {
    callGraphLoading.value = false
  }
}

// Handle function selection from call graph
const handleFunctionSelect = (funcId: string) => {
  console.log('[CodebaseAnalytics] Selected function:', funcId)
  showToast(`Selected: ${funcId}`, 'info', 2000)
}

// Silent version of declarations loading (no alerts)
const loadDeclarations = async () => {
  loadingProgress.declarations = true

  const { execute: fetchDeclarations } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`
      const response = await fetch(declarationsEndpoint, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      if (!response.ok) {
        throw new Error(`Declarations endpoint returned ${response.status}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        declarationAnalysis.value = data.declarations || []
      },
      onFinally: () => {
        loadingProgress.declarations = false
      }
    }
  )

  await fetchDeclarations()
}

// Silent version of duplicates loading (no alerts)
const loadDuplicates = async () => {
  loadingProgress.duplicates = true

  const { execute: fetchDuplicates } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`
      const response = await fetch(duplicatesEndpoint, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      if (!response.ok) {
        throw new Error(`Duplicates endpoint returned ${response.status}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        duplicateAnalysis.value = data.duplicates || []
      },
      onFinally: () => {
        loadingProgress.duplicates = false
      }
    }
  )

  await fetchDuplicates()
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
    notify('Indexing is already in progress', 'warning')
    return
  }

  analyzing.value = true
  progressPercent.value = 10
  progressStatus.value = 'Starting codebase indexing...'

  const { execute: runIndexing } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const indexEndpoint = `${backendUrl}/api/analytics/codebase/index`

      const response = await fetch(indexEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ root_path: rootPath.value })
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }

      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: async (data) => {
        // Check if this is a new job or already running
        if (data.status === 'already_running') {
          currentJobId.value = data.task_id
          progressStatus.value = 'Indexing already in progress, monitoring...'
          notify('Indexing job already running, now monitoring', 'info')
        } else {
          currentJobId.value = data.task_id
          progressStatus.value = 'Indexing started...'
          notify('Codebase indexing started', 'success')
        }

        // Start polling for job status updates
        progressPercent.value = 20
        startJobPolling()
      },
      onError: (error) => {
        progressStatus.value = `Indexing failed to start: ${error.message}`
        notify(`Indexing failed: ${error.message}`, 'error')
        analyzing.value = false
      }
    }
  )

  await runIndexing()
}


// Get codebase statistics
const getCodebaseStats = async () => {
  const { execute: fetchStats } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const statsEndpoint = `${backendUrl}/api/analytics/codebase/stats`
      const response = await fetch(statsEndpoint)
      if (!response.ok) {
        throw new Error(`Stats endpoint returned ${response.status}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        if (data.status === 'success' && data.stats) {
          codebaseStats.value = data.stats
        }
      }
    }
  )

  await fetchStats()
}

// Get problems report
const getProblemsReport = async () => {
  loadingProgress.problems = true
  progressStatus.value = 'Analyzing code problems...'

  const { execute: fetchProblems } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const problemsEndpoint = `${backendUrl}/api/analytics/codebase/problems`
      const response = await fetch(problemsEndpoint)
      if (!response.ok) {
        throw new Error(`Problems endpoint returned ${response.status}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        problemsReport.value = data.problems || []
      },
      onFinally: () => {
        loadingProgress.problems = false
      }
    }
  )

  await fetchProblems()
}

// Get declarations data with improved error handling (debug button)
const getDeclarationsData = async () => {
  const startTime = Date.now()
  loadingProgress.declarations = true
  progressStatus.value = 'Processing declarations...'

  const { execute: fetchDeclarations } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`
      const response = await fetch(declarationsEndpoint, {
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
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        const responseTime = Date.now() - startTime
        declarationAnalysis.value = data.declarations || []
        notify(`Found ${declarationAnalysis.value.length} declarations (${responseTime}ms)`, 'success')
      },
      onError: (error) => {
        const responseTime = Date.now() - startTime
        notify(`Declarations failed: ${error.message} (${responseTime}ms)`, 'error')
      },
      onFinally: () => {
        loadingProgress.declarations = false
        progressStatus.value = 'Ready'
      }
    }
  )

  await fetchDeclarations()
}

// Get duplicates data (debug button)
const getDuplicatesData = async () => {
  loadingProgress.duplicates = true
  progressStatus.value = 'Finding duplicate code...'
  const startTime = Date.now()

  const { execute: fetchDuplicates } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`
      const response = await fetch(duplicatesEndpoint, {
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
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        const responseTime = Date.now() - startTime
        duplicateAnalysis.value = data.duplicates || []
        notify(`Found ${duplicateAnalysis.value.length} duplicates (${responseTime}ms)`, 'success')
      },
      onError: (error) => {
        const responseTime = Date.now() - startTime
        notify(`Duplicates failed: ${error.message} (${responseTime}ms)`, 'error')
      },
      onFinally: () => {
        loadingProgress.duplicates = false
        progressStatus.value = 'Ready'
      }
    }
  )

  await fetchDuplicates()
}

// Get hardcodes data (debug button)
const getHardcodesData = async () => {
  loadingProgress.hardcodes = true
  progressStatus.value = 'Detecting hardcoded values...'
  const startTime = Date.now()

  const { execute: fetchHardcodes } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const hardcodesEndpoint = `${backendUrl}/api/analytics/codebase/hardcodes`
      const response = await fetch(hardcodesEndpoint, {
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
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        const responseTime = Date.now() - startTime
        const hardcodeCount = data.hardcodes ? data.hardcodes.length : 0
        const hardcodeTypes = data.hardcodes ? [...new Set(data.hardcodes.map(h => h.type))].join(', ') : 'none'
        notify(`Found ${hardcodeCount} hardcodes (${hardcodeTypes}) - ${responseTime}ms`, 'success')
      },
      onError: (error) => {
        const responseTime = Date.now() - startTime
        notify(`Hardcodes failed: ${error.message} (${responseTime}ms)`, 'error')
      },
      onFinally: () => {
        loadingProgress.hardcodes = false
        progressStatus.value = 'Ready'
      }
    }
  )

  await fetchHardcodes()
}

// Debug function to check data state
const testDataState = () => {
  const summary = {
    problems: problemsReport.value?.length || 0,
    declarations: declarationAnalysis.value?.length || 0,
    duplicates: duplicateAnalysis.value?.length || 0,
    stats: codebaseStats.value ? 'Available' : 'Not loaded'
  }

  notify(`State: ${summary.problems} problems, ${summary.declarations} declarations, ${summary.duplicates} duplicates, Stats: ${summary.stats}`, 'info')
}

// FIXED: Check NPU worker endpoint directly (not via backend proxy)
const testNpuConnection = async () => {
  const startTime = Date.now()

  const { execute: testNpu } = useAsyncHandler(
    async () => {
      const npuWorkerUrl = `http://${import.meta.env.VITE_NPU_WORKER_HOST || NetworkConstants.NPU_WORKER_VM_IP}:${import.meta.env.VITE_NPU_WORKER_PORT || NetworkConstants.NPU_WORKER_PORT}`
      const npuEndpoint = `${npuWorkerUrl}/health`
      const response = await fetch(npuEndpoint, {
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
      return response.json()
    },
    {
      errorMessage: 'NPU connection failed',
      notify,
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        const responseTime = Date.now() - startTime
        const npuStatus = data.available ? 'Available' : 'Not Available'
        notify(`NPU: ${npuStatus} (${responseTime}ms)`, data.available ? 'success' : 'warning')
      },
      onError: (error) => {
        const responseTime = Date.now() - startTime
        notify(`NPU failed: ${error.message} (${responseTime}ms)`, 'error')
      }
    }
  )

  await testNpu()
}

// NEW: Test all endpoints functionality
const testAllEndpoints = async () => {
  progressStatus.value = 'Testing all API endpoints...'

  const { execute: runTests } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const results = []

      // Test declarations
      try {
        const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`
        const response = await fetch(declarationsEndpoint)
        results.push(`Declarations: ${response.ok ? '✅' : '❌'} (${response.status})`)
      } catch (error) {
        results.push(`Declarations: ❌ (${error.message})`)
      }

      // Test duplicates
      try {
        const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`
        const response = await fetch(duplicatesEndpoint)
        results.push(`Duplicates: ${response.ok ? '✅' : '❌'} (${response.status})`)
      } catch (error) {
        results.push(`Duplicates: ❌ (${error.message})`)
      }

      // Test hardcodes
      try {
        const hardcodesEndpoint = `${backendUrl}/api/analytics/codebase/hardcodes`
        const response = await fetch(hardcodesEndpoint)
        results.push(`Hardcodes: ${response.ok ? '✅' : '❌'} (${response.status})`)
      } catch (error) {
        results.push(`Hardcodes: ❌ (${error.message})`)
      }

      // Test NPU
      try {
        const npuEndpoint = `${backendUrl}/api/monitoring/phase9/hardware/npu`
        const response = await fetch(npuEndpoint)
        results.push(`NPU: ${response.ok ? '✅' : '❌'} (${response.status})`)
      } catch (error) {
        results.push(`NPU: ❌ (${error.message})`)
      }

      // Test stats
      try {
        const statsEndpoint = `${backendUrl}/api/analytics/codebase/stats`
        const response = await fetch(statsEndpoint)
        results.push(`Stats: ${response.ok ? '✅' : '❌'} (${response.status})`)
      } catch (error) {
        results.push(`Stats: ❌ (${error.message})`)
      }

      return results
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (results) => {
        const passed = results.filter(r => r.includes('✅')).length
        const failed = results.filter(r => r.includes('❌')).length
        const summary = `API Tests: ${passed}/${results.length} passed`
        notify(summary, failed === 0 ? 'success' : 'warning')
        // Log full results to console for detailed review
        console.log('API Test Results:', results.join('\n'))
      },
      onError: (error) => {
        notify(`API tests failed: ${error.message}`, 'error')
      },
      onFinally: () => {
        progressStatus.value = 'Ready'
      }
    }
  )

  await runTests()
}

// Code Intelligence: Run anti-pattern/code smell analysis
const runCodeSmellAnalysis = async () => {
  const startTime = Date.now()
  analyzingCodeSmells.value = true
  progressStatus.value = 'Scanning for code smells and anti-patterns...'

  const { execute: fetchCodeSmells } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const analyzeEndpoint = `${backendUrl}/api/code-intelligence/analyze`
      const response = await fetch(analyzeEndpoint, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          path: rootPath.value,
          exclude_dirs: ['node_modules', '.venv', '__pycache__', '.git', 'archives'],
          min_severity: 'low'  // Show low and above
        })
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        const responseTime = Date.now() - startTime
        codeSmellsReport.value = data.report
        const totalIssues = data.report?.anti_patterns?.length || 0
        const filesAnalyzed = data.report?.total_files || 0
        notify(`Found ${totalIssues} code smells in ${filesAnalyzed} files (${responseTime}ms)`, totalIssues > 0 ? 'warning' : 'success')
        progressStatus.value = `Code smell scan complete: ${totalIssues} issues found`
      },
      onError: (error) => {
        const responseTime = Date.now() - startTime
        notify(`Code smell analysis failed: ${error.message} (${responseTime}ms)`, 'error')
        progressStatus.value = 'Code smell analysis failed'
      },
      onFinally: () => {
        analyzingCodeSmells.value = false
      }
    }
  )

  await fetchCodeSmells()
}

// Code Intelligence: Get codebase health score
const getCodeHealthScore = async () => {
  const startTime = Date.now()
  analyzingCodeSmells.value = true
  progressStatus.value = 'Calculating codebase health score...'

  const { execute: fetchHealthScore } = useAsyncHandler(
    async () => {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const healthEndpoint = `${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(rootPath.value)}`
      const response = await fetch(healthEndpoint, {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        }
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      return response.json()
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        const responseTime = Date.now() - startTime
        codeHealthScore.value = data
        const score = data.health_score || 0
        const grade = data.grade || 'N/A'
        const issues = data.total_issues || 0
        notify(`Health Score: ${score}/100 (Grade: ${grade}) - ${issues} issues (${responseTime}ms)`, score >= 70 ? 'success' : 'warning')
        progressStatus.value = `Health Score: ${score}/100 (${grade})`
      },
      onError: (error) => {
        const responseTime = Date.now() - startTime
        notify(`Health score failed: ${error.message} (${responseTime}ms)`, 'error')
        progressStatus.value = 'Health score calculation failed'
      },
      onFinally: () => {
        analyzingCodeSmells.value = false
      }
    }
  )

  await fetchHealthScore()
}

// Run full analysis
const runFullAnalysis = async () => {
  if (analyzing.value) return

  analyzing.value = true
  progressPercent.value = 0
  const analysisStartTime = Date.now()

  const { execute: executeFullAnalysis } = useAsyncHandler(
    async () => {
      progressStatus.value = 'Starting comprehensive analysis...'
      progressPercent.value = 10

      // First ensure codebase is indexed
      await indexCodebase()
      progressPercent.value = 30

      await getCodebaseStats()
      progressPercent.value = 40

      await getProblemsReport()
      progressPercent.value = 50

      await getDeclarationsData()
      progressPercent.value = 70

      await getDuplicatesData()
      progressPercent.value = 85

      await getHardcodesData()
      progressPercent.value = 100

      return Date.now() - analysisStartTime
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (totalAnalysisTime) => {
        progressStatus.value = `Analysis complete! (${totalAnalysisTime}ms)`
        notify(`Full analysis completed in ${totalAnalysisTime}ms`, 'success')
      },
      onError: (error) => {
        progressStatus.value = `Analysis failed: ${error.message}`
        notify(`Analysis failed: ${error.message}`, 'error')
      },
      onFinally: () => {
        analyzing.value = false
        setTimeout(() => {
          progressPercent.value = 0
          progressStatus.value = 'Ready'
        }, 5000)
      }
    }
  )

  await executeFullAnalysis()
}

// Enhanced Analytics Methods
// TODO: Replace mock data with actual API calls when endpoints are ready
const loadSystemOverview = async () => {
  const { execute: fetchOverview } = useAsyncHandler(
    async () => {
      // Mock data for now - replace with actual API call
      // const backendUrl = await appConfig.getServiceUrl('backend')
      // const response = await fetch(`${backendUrl}/api/analytics/system/overview`)
      return {
        api_requests_per_minute: 142,
        average_response_time: 85,
        active_connections: 23,
        system_health: 'Healthy'
      }
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        systemOverview.value = data
      },
      onError: () => {
        // Silent failure for dashboard cards
      }
    }
  )

  await fetchOverview()
}

const loadCommunicationPatterns = async () => {
  const { execute: fetchPatterns } = useAsyncHandler(
    async () => {
      // Mock data for now - replace with actual API call
      // const backendUrl = await appConfig.getServiceUrl('backend')
      // const response = await fetch(`${backendUrl}/api/analytics/system/communication`)
      return {
        websocket_connections: 5,
        api_call_frequency: 34,
        data_transfer_rate: 1.2
      }
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        communicationPatterns.value = data
      },
      onError: () => {
        // Silent failure for dashboard cards
      }
    }
  )

  await fetchPatterns()
}

const loadCodeQuality = async () => {
  const { execute: fetchQuality } = useAsyncHandler(
    async () => {
      // Mock data for now - replace with actual API call
      // const backendUrl = await appConfig.getServiceUrl('backend')
      // const response = await fetch(`${backendUrl}/api/analytics/system/quality`)
      return {
        overall_score: 87,
        test_coverage: 76,
        code_duplicates: 3,
        technical_debt: 2.4
      }
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        codeQuality.value = data
      },
      onError: () => {
        // Silent failure for dashboard cards
      }
    }
  )

  await fetchQuality()
}

const loadPerformanceMetrics = async () => {
  const { execute: fetchPerformance } = useAsyncHandler(
    async () => {
      // Mock data for now - replace with actual API call
      // const backendUrl = await appConfig.getServiceUrl('backend')
      // const response = await fetch(`${backendUrl}/api/analytics/system/performance`)
      return {
        efficiency_score: 92,
        memory_usage: 256,
        cpu_usage: 23,
        load_time: 1240
      }
    },
    {
      logErrors: true,
      errorPrefix: '[CodebaseAnalytics]',
      onSuccess: (data) => {
        performanceMetrics.value = data
      },
      onError: () => {
        // Silent failure for dashboard cards
      }
    }
  )

  await fetchPerformance()
}

const refreshAllMetrics = async () => {

  await Promise.all([
    // Enhanced analytics (top section)
    loadSystemOverview(),
    loadCommunicationPatterns(),
    loadCodeQuality(),
    loadPerformanceMetrics(),

    // Codebase analytics (bottom section) - using silent versions
    getCodebaseStats(),
    getProblemsReport(),
    loadDeclarations(),  // Silent version without alerts
    loadDuplicates()     // Silent version without alerts
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
const getScoreClass = (score) => {
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-medium'
  return 'score-low'
}

const getPriorityClass = (severity) => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'priority-critical'
    case 'high': return 'priority-high'
    case 'medium': return 'priority-medium'
    default: return 'priority-low'
  }
}

const getSeverityColor = (severity) => {
  switch (severity?.toLowerCase()) {
    case 'critical': return '#dc2626'
    case 'high': return '#ea580c'
    case 'medium': return '#d97706'
    default: return '#059669'
  }
}

const formatProblemType = (type) => {
  return type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Unknown'
}

const getHealthClass = (health) => {
  switch (health?.toLowerCase()) {
    case 'healthy': return 'health-good'
    case 'warning': return 'health-warning'
    case 'critical': return 'health-critical'
    default: return 'health-unknown'
  }
}

const getEfficiencyClass = (score) => {
  if (score >= 80) return 'efficiency-high'
  if (score >= 60) return 'efficiency-medium'
  return 'efficiency-low'
}

const getQualityClass = (score) => {
  if (score >= 80) return 'quality-high'
  if (score >= 60) return 'quality-medium'
  return 'quality-low'
}

// Code Intelligence helper methods
const getHealthGradeClass = (grade) => {
  switch (grade?.toUpperCase()) {
    case 'A': return 'grade-a'
    case 'B': return 'grade-b'
    case 'C': return 'grade-c'
    case 'D': return 'grade-d'
    case 'F': return 'grade-f'
    default: return 'grade-unknown'
  }
}

const getSmellSeverityClass = (severity) => {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'smell-critical'
    case 'high': return 'smell-high'
    case 'medium': return 'smell-medium'
    case 'low': return 'smell-low'
    case 'info': return 'smell-info'
    default: return 'smell-unknown'
  }
}

const formatSmellType = (type) => {
  return type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Unknown'
}

// All variables and functions are automatically available in <script setup>
// No export default needed in <script setup> syntax
</script>

<style scoped>
.codebase-analytics {
  padding: 20px;
  background: #0f0f0f;
  color: #ffffff;
  min-height: 100vh;
}

.analytics-header {
  background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.header-content h2 {
  margin: 0 0 16px 0;
  color: #ffffff;
  font-size: 1.5em;
  font-weight: 600;
}

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.path-input {
  background: #1f2937;
  border: 1px solid #374151;
  color: #ffffff;
  padding: 10px 16px;
  border-radius: 8px;
  min-width: 300px;
  font-family: 'JetBrains Mono', monospace;
}

.path-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
}

.btn-primary, .btn-secondary, .btn-debug {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background: #22c55e;
  color: #ffffff;
}

.btn-primary:hover:not(:disabled) {
  background: #16a34a;
  transform: translateY(-1px);
}

.btn-secondary {
  background: #6366f1;
  color: #ffffff;
}

.btn-secondary:hover:not(:disabled) {
  background: #4f46e5;
  transform: translateY(-1px);
}

.btn-primary:disabled, .btn-secondary:disabled {
  background: #374151;
  color: #9ca3af;
  cursor: not-allowed;
  transform: none;
}

.btn-cancel {
  background: #dc2626;
  color: #ffffff;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-cancel:hover {
  background: #b91c1c;
  transform: translateY(-1px);
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
  background: #1f2937;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
  border: 1px solid #374151;
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
  color: #22c55e;
  font-weight: 600;
}

.job-id {
  color: #6b7280;
  font-size: 0.8em;
  font-family: 'JetBrains Mono', monospace;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #374151;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
  transition: width 0.3s ease;
  border-radius: 4px;
}

.progress-status {
  color: #d1d5db;
  font-size: 0.9em;
  font-weight: 500;
}

/* Phase Progress */
.phase-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #111827;
  border-radius: 6px;
}

.phase-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #1f2937;
  border-radius: 4px;
  font-size: 0.85em;
  transition: all 0.2s;
}

.phase-item.phase-completed {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.phase-item.phase-running {
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.phase-item.phase-pending {
  color: #6b7280;
  background: #1f2937;
  border: 1px solid #374151;
}

.phase-item i {
  font-size: 0.9em;
}

/* Batch Progress */
.batch-progress {
  margin-top: 16px;
  padding: 12px;
  background: #111827;
  border-radius: 6px;
}

.batch-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.batch-label {
  color: #9ca3af;
  font-size: 0.85em;
}

.batch-count {
  color: #22c55e;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}

.batch-bar {
  width: 100%;
  height: 6px;
  background: #374151;
  border-radius: 3px;
  overflow: hidden;
}

.batch-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
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
  background: #111827;
  border-radius: 6px;
}

.live-stats .stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #d1d5db;
  font-size: 0.85em;
}

.live-stats .stat-item i {
  color: #3b82f6;
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
  color: #f9fafb;
  font-size: 1.1em;
  font-weight: 600;
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8em;
  color: #9ca3af;
}

.refresh-indicator.active {
  color: #22c55e;
}

.refresh-indicator .fas {
  font-size: 0.7em;
}

.refresh-btn {
  background: #374151;
  border: 1px solid #4b5563;
  color: #d1d5db;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: #4b5563;
  color: #ffffff;
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
  color: #9ca3af;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 1.4em;
  font-weight: 700;
  color: #ffffff;
}

.metric-value.health-good { color: #22c55e; }
.metric-value.health-warning { color: #f59e0b; }
.metric-value.health-critical { color: #ef4444; }
.metric-value.health-unknown { color: #6b7280; }

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
  border-bottom: 1px solid #374151;
}

.pattern-item:last-child, .performance-item:last-child, .quality-item:last-child {
  border-bottom: none;
}

.pattern-label, .performance-label, .quality-label {
  color: #d1d5db;
  font-size: 0.9em;
}

.pattern-value, .performance-value, .quality-value {
  color: #ffffff;
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
  color: #9ca3af;
}

.quality-high, .efficiency-high {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.quality-medium, .efficiency-medium {
  background: rgba(251, 191, 36, 0.1);
  color: #fbbf24;
}

.quality-low, .efficiency-low {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.btn-link {
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  text-decoration: underline;
  font-size: 0.9em;
}

.btn-link:hover {
  color: #2563eb;
}

/* Traditional Analytics Section */
.analytics-section {
  background: #1f2937;
  border-radius: 12px;
  padding: 24px;
  border: 1px solid #374151;
}

.real-time-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #374151;
}

.toggle-switch {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  color: #d1d5db;
}

.toggle-switch input {
  display: none;
}

.toggle-slider {
  width: 40px;
  height: 20px;
  background: #374151;
  border-radius: 10px;
  position: relative;
  transition: all 0.3s;
}

.toggle-slider:before {
  content: '';
  width: 16px;
  height: 16px;
  background: #ffffff;
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: all 0.3s;
}

.toggle-switch input:checked + .toggle-slider {
  background: #22c55e;
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(20px);
}

.refresh-all-btn {
  background: #6366f1;
  color: #ffffff;
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
  background: #4f46e5;
}

.stats-section, .problems-section, .duplicates-section, .declarations-section {
  margin-bottom: 32px;
}

.stats-section h3, .problems-section h3, .duplicates-section h3, .declarations-section h3 {
  color: #f9fafb;
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
  color: #22c55e;
  margin-bottom: 4px;
  text-align: center;
}

.stat-label {
  color: #9ca3af;
  font-size: 0.9em;
  text-align: center;
}

.problems-list, .duplicates-list, .declarations-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.problem-item, .duplicate-item, .declaration-item {
  background: #111827;
  border: 1px solid #374151;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.problem-item:hover, .duplicate-item:hover, .declaration-item:hover {
  border-color: #4b5563;
  transform: translateX(4px);
}

.problem-item.priority-critical {
  border-left: 4px solid #dc2626;
}

.problem-item.priority-high {
  border-left: 4px solid #ea580c;
}

.problem-item.priority-medium {
  border-left: 4px solid #d97706;
}

.problem-item.priority-low {
  border-left: 4px solid #059669;
}

.problem-header, .duplicate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.problem-type, .duplicate-similarity {
  font-weight: 600;
  color: #ffffff;
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
  color: #d1d5db;
}

.problem-file {
  color: #9ca3af;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

.problem-suggestion {
  color: #fbbf24;
  font-style: italic;
}

.duplicate-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}

.duplicate-file {
  color: #9ca3af;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

.declaration-name {
  font-weight: 600;
  color: #22c55e;
  margin-bottom: 4px;
}

.declaration-type {
  color: #3b82f6;
  font-size: 0.8em;
  margin-bottom: 4px;
}

.declaration-file {
  color: #9ca3af;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
}

.show-more {
  text-align: center;
  padding: 16px;
  border-top: 1px solid #374151;
}

/* Code Smells Section */
.code-smells-section {
  margin-top: 24px;
  padding: 20px;
  background: #1f2937;
  border-radius: 12px;
  border: 1px solid #374151;
}

.code-smells-section h3 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 16px 0;
  color: #e5e7eb;
  font-size: 1.1em;
}

.health-badge {
  font-size: 0.8em;
  padding: 4px 12px;
  border-radius: 20px;
  font-weight: 600;
}

.grade-a { background: #10b981; color: white; }
.grade-b { background: #22c55e; color: white; }
.grade-c { background: #eab308; color: black; }
.grade-d { background: #f97316; color: white; }
.grade-f { background: #ef4444; color: white; }
.grade-unknown { background: #6b7280; color: white; }

.smells-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.summary-card {
  background: #111827;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid #374151;
}

.summary-card.warning { border-color: #f59e0b; }
.summary-card.critical { border-color: #ef4444; }
.summary-card.high { border-color: #f97316; }

.summary-value {
  font-size: 1.8em;
  font-weight: 700;
  color: #ffffff;
}

.summary-card.warning .summary-value { color: #f59e0b; }
.summary-card.critical .summary-value { color: #ef4444; }
.summary-card.high .summary-value { color: #f97316; }

.summary-label {
  font-size: 0.75em;
  color: #9ca3af;
  text-transform: uppercase;
  margin-top: 4px;
}

.code-smells-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.smell-item {
  background: #111827;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #6b7280;
  transition: all 0.2s ease;
}

.smell-item:hover {
  transform: translateX(4px);
  background: #1a232f;
}

.smell-item.smell-critical { border-left-color: #ef4444; }
.smell-item.smell-high { border-left-color: #f97316; }
.smell-item.smell-medium { border-left-color: #eab308; }
.smell-item.smell-low { border-left-color: #22c55e; }
.smell-item.smell-info { border-left-color: #3b82f6; }

.smell-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.smell-type {
  font-weight: 600;
  color: #e5e7eb;
}

.smell-severity {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.smell-severity.critical { background: #7f1d1d; color: #fca5a5; }
.smell-severity.high { background: #7c2d12; color: #fdba74; }
.smell-severity.medium { background: #713f12; color: #fde047; }
.smell-severity.low { background: #14532d; color: #86efac; }
.smell-severity.info { background: #1e3a8a; color: #93c5fd; }

.smell-description {
  color: #d1d5db;
  font-size: 0.9em;
  margin-bottom: 8px;
}

.smell-location {
  color: #9ca3af;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8em;
  margin-bottom: 4px;
}

.smell-suggestion {
  color: #22c55e;
  font-size: 0.85em;
  padding: 8px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 4px;
  margin-top: 8px;
}

.muted {
  color: #6b7280;
  font-style: italic;
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
  color: #e2e8f0;
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.charts-section .section-header h3 i {
  color: #3b82f6;
}

.charts-loading,
.charts-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 12px;
  color: #94a3b8;
}

.charts-loading i {
  font-size: 32px;
  color: #3b82f6;
}

.charts-error i {
  font-size: 32px;
  color: #ef4444;
}

.charts-error {
  color: #f87171;
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
  color: #e2e8f0;
  line-height: 1;
}

.summary-stat.race-highlight .summary-value {
  color: #f97316;
}

.summary-label {
  font-size: 0.85rem;
  color: #94a3b8;
  margin-top: 4px;
  display: block;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.chart-container {
  background: rgba(30, 41, 59, 0.7);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  min-height: 350px;
}

.chart-container.chart-wide {
  grid-column: span 1;
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

  .chart-container.chart-wide {
    grid-column: span 1;
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
  color: #e2e8f0;
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dependency-section .section-header h3 i {
  color: #8b5cf6;
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
  color: #f87171;
  margin-bottom: 12px;
}

.circular-deps-warning .warning-header i {
  color: #ef4444;
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
  color: #e2e8f0;
}

.circular-dep-item i {
  color: #f59e0b;
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
  color: #e2e8f0;
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.external-deps-table h4 i {
  color: #06b6d4;
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
  color: #e2e8f0;
}

.dep-count {
  font-size: 0.8rem;
  color: #94a3b8;
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
  color: #e2e8f0;
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-tree-section .section-header h3 i {
  color: #06b6d4;
}

.import-tree-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #fca5a5;
}

.import-tree-section .section-error i {
  color: #ef4444;
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
  color: #e2e8f0;
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.call-graph-section .section-header h3 i {
  color: #8b5cf6;
}

.call-graph-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #fca5a5;
}

.call-graph-section .section-error i {
  color: #ef4444;
}

.call-graph-content {
  margin-top: 16px;
}
</style>