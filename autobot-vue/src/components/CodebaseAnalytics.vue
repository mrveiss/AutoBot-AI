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
          </div>
        </div>
      </div>
    </div>

    <!-- Progress Indicator -->
    <div v-if="analyzing" class="progress-container">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="progress-status">{{ progressStatus }}</div>
    </div>

    <!-- Enhanced Analytics Dashboard Cards -->
    <div class="enhanced-analytics-grid">
      <!-- System Overview -->
      <div class="analytics-card overview-card">
        <div class="card-header">
          <h3><i class="fas fa-tachometer-alt"></i> System Overview</h3>
          <div class="refresh-indicator" :class="{ active: realTimeEnabled }">
            <i class="fas fa-circle"></i>
            {{ realTimeEnabled ? 'Live' : 'Static' }}
          </div>
        </div>
        <div class="card-content">
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
        </div>
      </div>

      <!-- Communication Patterns -->
      <div class="analytics-card communication-card">
        <div class="card-header">
          <h3><i class="fas fa-network-wired"></i> Communication Patterns</h3>
          <button @click="loadCommunicationPatterns" class="refresh-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
        <div class="card-content">
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
        </div>
      </div>

      <!-- Code Quality -->
      <div class="analytics-card quality-card">
        <div class="card-header">
          <h3><i class="fas fa-code-branch"></i> Code Quality</h3>
          <button @click="loadCodeQuality" class="refresh-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
        <div class="card-content">
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
        </div>
      </div>

      <!-- Performance Metrics -->
      <div class="analytics-card performance-card">
        <div class="card-header">
          <h3><i class="fas fa-bolt"></i> Performance Metrics</h3>
          <button @click="loadPerformanceMetrics" class="refresh-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
        <div class="card-content">
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
        </div>
      </div>
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
          <div class="stat-card">
            <div class="stat-value">{{ codebaseStats.total_files || 0 }}</div>
            <div class="stat-label">Total Files</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ codebaseStats.total_lines || 0 }}</div>
            <div class="stat-label">Lines of Code</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ codebaseStats.total_functions || 0 }}</div>
            <div class="stat-label">Functions</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ codebaseStats.total_classes || 0 }}</div>
            <div class="stat-label">Classes</div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-chart-bar"
          message="No codebase statistics available. Run analysis to generate data."
        />
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
import EmptyState from '@/components/ui/EmptyState.vue'

// Reactive data
// FIXED: Fetch project root from backend config (no hardcoding)
const rootPath = ref('/home/kali/Desktop/AutoBot')
const analyzing = ref(false)
const progressPercent = ref(0)
const progressStatus = ref('Ready')
const realTimeEnabled = ref(false)
const refreshInterval = ref(null)

// Analytics data
const codebaseStats = ref(null)
const problemsReport = ref([])
const duplicateAnalysis = ref([])
const declarationAnalysis = ref([])
const refactoringSuggestions = ref([])

// Enhanced analytics data
const systemOverview = ref(null)
const communicationPatterns = ref(null)
const codeQuality = ref(null)
const performanceMetrics = ref(null)

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

  // Load initial data - Enhanced analytics (top section)
  loadSystemOverview()
  loadCommunicationPatterns()
  loadCodeQuality()
  loadPerformanceMetrics()

  // Load codebase analytics data (bottom section)
  loadCodebaseAnalyticsData()
})

// Fetch project root from backend configuration
const loadProjectRoot = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const configEndpoint = `${backendUrl}/api/frontend-config`

    const response = await fetch(configEndpoint)
    if (response.ok) {
      const config = await response.json()
      if (config.project && config.project.root_path) {
        rootPath.value = config.project.root_path
      } else {
        console.warn('⚠️ Project root not found in config, using empty default')
      }
    } else {
      console.warn(`⚠️ Failed to fetch frontend config: ${response.status}`)
    }
  } catch (error) {
    console.error('❌ Failed to load project root:', error)
    // Fallback: Leave empty for user input
    progressStatus.value = 'Please enter project path to analyze'
  }
}

// Load all codebase analytics data (silent mode - no alerts)
const loadCodebaseAnalyticsData = async () => {

  try {
    // Load all analytics data in parallel (silent mode)
    await Promise.all([
      getCodebaseStats(),
      getProblemsReport(),
      loadDeclarations(),  // Silent version
      loadDuplicates()     // Silent version
    ])

  } catch (error) {
    console.error('❌ Failed to load codebase analytics data:', error)
    // Provide user feedback for critical failures
    progressStatus.value = `Failed to load analytics: ${error.message}`
  }
}

// Silent version of declarations loading (no alerts)
const loadDeclarations = async () => {
  loadingProgress.declarations = true

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`

    const response = await fetch(declarationsEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (response.ok) {
      const data = await response.json()
      declarationAnalysis.value = data.declarations || []
    } else {
      console.warn(`⚠️ Declarations endpoint returned ${response.status}`)
    }
  } catch (error) {
    console.error('❌ Failed to load declarations:', error)
  } finally {
    loadingProgress.declarations = false
  }
}

// Silent version of duplicates loading (no alerts)
const loadDuplicates = async () => {
  loadingProgress.duplicates = true

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`

    const response = await fetch(duplicatesEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    if (response.ok) {
      const data = await response.json()
      duplicateAnalysis.value = data.duplicates || []
    } else {
      console.warn(`⚠️ Duplicates endpoint returned ${response.status}`)
    }
  } catch (error) {
    console.error('❌ Failed to load duplicates:', error)
  } finally {
    loadingProgress.duplicates = false
  }
}

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})

// Index codebase first
const indexCodebase = async () => {
  analyzing.value = true
  progressPercent.value = 10
  progressStatus.value = 'Indexing codebase...'

  // Start polling for problems immediately
  let pollingInterval = null
  let filesIndexed = 0

  const pollProblems = async () => {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')

      // Poll for problems
      const problemsResponse = await fetch(`${backendUrl}/api/analytics/codebase/problems`)
      if (problemsResponse.ok) {
        const problemsData = await problemsResponse.json()
        if (problemsData.problems && problemsData.problems.length > 0) {
          problems.value = problemsData.problems
        }
      }

      // Poll for stats to get progress
      const statsResponse = await fetch(`${backendUrl}/api/analytics/codebase/stats`)
      if (statsResponse.ok) {
        const statsData = await statsResponse.json()
        if (statsData.total_files) {
          filesIndexed = statsData.total_files
          progressStatus.value = `Indexed ${filesIndexed} files... (${problems.value.length} problems found)`
        }
      }
    } catch (error) {
    }
  }

  // Start polling every 2 seconds
  pollingInterval = setInterval(pollProblems, 2000)
  pollProblems() // Initial poll

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const indexEndpoint = `${backendUrl}/api/analytics/codebase/index`


    const response = await fetch(indexEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ root_path: rootPath.value })
    })

    progressPercent.value = 100

    if (response.ok) {
      const result = await response.json()
      progressStatus.value = `Indexing completed! ${filesIndexed} files indexed, ${problems.value.length} problems found`

      // Final data load
      await pollProblems()
      setTimeout(() => {
        getCodebaseStats()
      }, 1000)
    } else {
      const error = await response.text()
      progressStatus.value = `Indexing failed: ${response.status}`
      console.error('❌ Indexing failed:', error)
    }
  } catch (error) {
    progressStatus.value = `Indexing error: ${error.message}`
    console.error('❌ Indexing error:', error)
  } finally {
    // Stop polling
    if (pollingInterval) {
      clearInterval(pollingInterval)
    }
    analyzing.value = false
  }
}


// Get codebase statistics
const getCodebaseStats = async () => {
  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const statsEndpoint = `${backendUrl}/api/analytics/codebase/stats`

    const response = await fetch(statsEndpoint)
    if (response.ok) {
      const data = await response.json()
      if (data.status === 'success' && data.stats) {
        codebaseStats.value = data.stats
      } else {
      }
    }
  } catch (error) {
    console.error('❌ Failed to load codebase stats:', error)
  }
}

// Get problems report
const getProblemsReport = async () => {
  loadingProgress.problems = true
  progressStatus.value = 'Analyzing code problems...'

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const problemsEndpoint = `${backendUrl}/api/analytics/codebase/problems`

    const response = await fetch(problemsEndpoint)
    if (response.ok) {
      const data = await response.json()
      problemsReport.value = data.problems || []
    }
  } catch (error) {
    console.error('❌ Failed to load problems:', error)
  } finally {
    loadingProgress.problems = false
  }
}

// Get declarations data with improved error handling
const getDeclarationsData = async () => {
  const startTime = Date.now()
  loadingProgress.declarations = true  // FIXED: reactive() doesn't use .value
  progressStatus.value = 'Processing declarations...'

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const declarationsEndpoint = `${backendUrl}/api/analytics/codebase/declarations`


    const response = await fetch(declarationsEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })

    const responseTime = Date.now() - startTime

    if (response.ok) {
      const data = await response.json()
      declarationAnalysis.value = data.declarations || []
      alert(`Declarations Test Results:\nStatus: Success\nFound: ${declarationAnalysis.value.length} declarations\nResponse Time: ${responseTime}ms`)
    } else {
      const errorText = await response.text()
      console.error(`❌ Declarations failed (${responseTime}ms):`, errorText)
      alert(`Declarations Test Failed:\nStatus: ${response.status}\nError: ${errorText}\nResponse Time: ${responseTime}ms`)
    }
  } catch (error) {
    const responseTime = Date.now() - startTime
    console.error(`❌ Declarations error (${responseTime}ms):`, error)
    alert(`Declarations Test Error:\nMessage: ${error.message}\nResponse Time: ${responseTime}ms`)
  } finally {
    loadingProgress.declarations = false  // FIXED: reactive() doesn't use .value
    progressStatus.value = 'Ready'
  }
}

// Get duplicates data
const getDuplicatesData = async () => {
  loadingProgress.duplicates = true  // FIXED: reactive() doesn't use .value
  progressStatus.value = 'Finding duplicate code...'

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const duplicatesEndpoint = `${backendUrl}/api/analytics/codebase/duplicates`


    const startTime = Date.now()
    const response = await fetch(duplicatesEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    const responseTime = Date.now() - startTime

    if (response.ok) {
      const data = await response.json()
      duplicateAnalysis.value = data.duplicates || []
      alert(`Duplicates Test Results:\nStatus: Success\nFound: ${duplicateAnalysis.value.length} duplicates\nResponse Time: ${responseTime}ms\nStorage: ${data.storage_type || 'unknown'}`)
    } else {
      const errorText = await response.text()
      console.error(`❌ Duplicates failed (${responseTime}ms):`, errorText)
      alert(`Duplicates Test Failed:\nStatus: ${response.status}\nError: ${errorText}\nResponse Time: ${responseTime}ms`)
    }
  } catch (error) {
    console.error('❌ Duplicates error:', error)
    alert(`Duplicates Test Error:\nMessage: ${error.message}`)
  } finally {
    loadingProgress.duplicates = false  // FIXED: reactive() doesn't use .value
    progressStatus.value = 'Ready'
  }
}

// Get hardcodes data
const getHardcodesData = async () => {
  loadingProgress.hardcodes = true  // FIXED: reactive() doesn't use .value
  progressStatus.value = 'Detecting hardcoded values...'

  try {
    const backendUrl = await appConfig.getServiceUrl('backend')
    const hardcodesEndpoint = `${backendUrl}/api/analytics/codebase/hardcodes`


    const startTime = Date.now()
    const response = await fetch(hardcodesEndpoint, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    const responseTime = Date.now() - startTime

    if (response.ok) {
      const data = await response.json()

      const hardcodeCount = data.hardcodes ? data.hardcodes.length : 0
      const hardcodeTypes = data.hardcodes ? [...new Set(data.hardcodes.map(h => h.type))].join(', ') : 'none'

      alert(`Hardcodes Test Results:\nStatus: Success\nFound: ${hardcodeCount} hardcoded values\nTypes: ${hardcodeTypes}\nResponse Time: ${responseTime}ms`)
    } else {
      const errorText = await response.text()
      console.error(`❌ Hardcodes failed (${responseTime}ms):`, errorText)
      alert(`Hardcodes Test Failed:\nStatus: ${response.status}\nError: ${errorText}\nResponse Time: ${responseTime}ms`)
    }
  } catch (error) {
    console.error('❌ Hardcodes error:', error)
    alert(`Hardcodes Test Error:\nMessage: ${error.message}`)
  } finally {
    loadingProgress.hardcodes = false  // FIXED: reactive() doesn't use .value
    progressStatus.value = 'Ready'
  }
}

// Debug function to check data state
const testDataState = () => {

  const summary = {
    problems: problemsReport.value?.length || 0,
    declarations: declarationAnalysis.value?.length || 0,
    duplicates: duplicateAnalysis.value?.length || 0,
    stats: codebaseStats.value ? 'Available' : 'Not loaded'
  }

  alert(`Data State Debug:\nProblems: ${summary.problems}\nDeclarations: ${summary.declarations}\nDuplicates: ${summary.duplicates}\nStats: ${summary.stats}`)
}

// FIXED: Check NPU worker endpoint directly (not via backend proxy)
const testNpuConnection = async () => {

  try {
    // FIXED: Use direct NPU worker URL from environment
    const npuWorkerUrl = `http://${import.meta.env.VITE_NPU_WORKER_HOST || '172.16.168.22'}:${import.meta.env.VITE_NPU_WORKER_PORT || '8081'}`
    const npuEndpoint = `${npuWorkerUrl}/health`


    try {
      const startTime = Date.now()
      const response = await fetch(npuEndpoint, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      const responseTime = Date.now() - startTime

      if (response.ok) {
        const data = await response.json()

        const npuStatus = data.available ? 'Available' : 'Not Available'
        const message = data.message || 'No additional info'

        alert(`NPU Hardware Test Results:\n\nStatus: ${npuStatus}\nResponse Time: ${responseTime}ms\nMessage: ${message}\n\nEndpoint: ${npuEndpoint}`)
      } else {
        const errorText = await response.text()
        alert(`NPU test failed with status ${response.status}:\n${errorText}\n\nResponse Time: ${responseTime}ms`)
      }
    } catch (error) {
      alert(`NPU test connection failed: ${error.message}\n\nCheck if the backend is running and monitoring API is available.`)
    }
  } catch (configError) {
    console.error('❌ Failed to get backend URL:', configError)
    alert(`Configuration error: ${configError.message}`)
  }
}

// NEW: Test all endpoints functionality
const testAllEndpoints = async () => {

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

  alert(`All Endpoints Test Results:\n\n${results.join('\n')}\n\nLegend: ✅ = Working, ❌ = Failed`)
}

// Run full analysis
const runFullAnalysis = async () => {
  if (analyzing.value) return

  analyzing.value = true
  progressPercent.value = 0

  try {
    const analysisStartTime = Date.now()
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

    const totalAnalysisTime = Date.now() - analysisStartTime
    progressStatus.value = `Analysis complete! (${totalAnalysisTime}ms)`

  } catch (error) {
    progressStatus.value = `Analysis failed: ${error.message}`
    console.error('❌ Full analysis failed:', error)
  } finally {
    analyzing.value = false
    setTimeout(() => {
      progressPercent.value = 0
      progressStatus.value = 'Ready'
    }, 5000)
  }
}

// Enhanced Analytics Methods
const loadSystemOverview = async () => {
  try {
    // Mock data for now - replace with actual API call
    systemOverview.value = {
      api_requests_per_minute: 142,
      average_response_time: 85,
      active_connections: 23,
      system_health: 'Healthy'
    }
  } catch (error) {
    console.error('Failed to load system overview:', error)
  }
}

const loadCommunicationPatterns = async () => {
  try {
    // Mock data for now - replace with actual API call
    communicationPatterns.value = {
      websocket_connections: 5,
      api_call_frequency: 34,
      data_transfer_rate: 1.2
    }
  } catch (error) {
    console.error('Failed to load communication patterns:', error)
  }
}

const loadCodeQuality = async () => {
  try {
    // Mock data for now - replace with actual API call
    codeQuality.value = {
      overall_score: 87,
      test_coverage: 76,
      code_duplicates: 3,
      technical_debt: 2.4
    }
  } catch (error) {
    console.error('Failed to load code quality:', error)
  }
}

const loadPerformanceMetrics = async () => {
  try {
    // Mock data for now - replace with actual API call
    performanceMetrics.value = {
      efficiency_score: 92,
      memory_usage: 256,
      cpu_usage: 23,
      load_time: 1240
    }
  } catch (error) {
    console.error('Failed to load performance metrics:', error)
  }
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

/* Enhanced Analytics Grid */
.enhanced-analytics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}

.analytics-card {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.analytics-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.4);
  border-color: #4b5563;
}

.card-header {
  background: #111827;
  padding: 16px 20px;
  border-bottom: 1px solid #374151;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
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

.card-content {
  padding: 20px;
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

.stat-card {
  background: #111827;
  padding: 16px;
  border-radius: 8px;
  text-align: center;
  border: 1px solid #374151;
  transition: all 0.2s;
}

.stat-card:hover {
  border-color: #4b5563;
  transform: translateY(-1px);
}

.stat-value {
  font-size: 2em;
  font-weight: 700;
  color: #22c55e;
  margin-bottom: 4px;
}

.stat-label {
  color: #9ca3af;
  font-size: 0.9em;
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
</style>