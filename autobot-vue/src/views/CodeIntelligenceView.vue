<template>
  <div class="code-intelligence-view view-container">
    <div class="container mx-auto px-4 py-6">
      <!-- Header with action buttons -->
      <div class="flex flex-wrap items-center justify-between mb-6">
        <div>
          <h1 class="text-3xl font-bold text-blueGray-700">Code Intelligence</h1>
          <p class="text-blueGray-600 mt-2">Code analysis, security scanning, and performance insights</p>
        </div>
        <div class="flex space-x-3 mt-4 sm:mt-0">
          <button
            @click="runFullAnalysis"
            :disabled="isAnalyzing"
            class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center"
          >
            <i class="fas fa-play mr-2" :class="{ 'animate-spin': isAnalyzing }"></i>
            {{ isAnalyzing ? 'Analyzing...' : 'Run Analysis' }}
          </button>
          <button
            @click="showScanFileModal = true"
            :disabled="isAnalyzing"
            class="px-4 py-2 bg-white border border-blueGray-300 text-blueGray-700 rounded-lg hover:bg-blueGray-50 disabled:opacity-50 transition-colors flex items-center"
          >
            <i class="fas fa-file-code mr-2"></i>
            Scan File
          </button>
        </div>
      </div>

      <!-- Health Score Cards -->
      <HealthScoreCards
        :health-score="healthScore"
        :security-score="securityScore"
        :performance-score="performanceScore"
        :redis-score="redisScore"
        :loading="scoresLoading"
        @refresh="loadAllScores"
      />

      <!-- Tab Navigation -->
      <div class="mb-6 mt-8">
        <nav class="flex space-x-4 border-b border-blueGray-200">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="activeTab === tab.id
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i :class="tab.icon" class="mr-2"></i>
            {{ tab.label }}
            <span
              v-if="tab.count > 0"
              class="ml-2 px-2 py-0.5 text-xs rounded-full"
              :class="getCountBadgeClass(tab.id)"
            >
              {{ tab.count }}
            </span>
          </button>
        </nav>
      </div>

      <!-- Tab Content -->
      <div class="tab-content">
        <!-- Security Tab -->
        <SecurityFindingsPanel
          v-if="activeTab === 'security'"
          :findings="securityFindings"
          :loading="securityLoading"
          :summary="securitySummary"
          @scan-file="scanSecurityFile"
          @refresh="loadSecurityAnalysis"
        />

        <!-- Performance Tab -->
        <PerformanceIssuesPanel
          v-if="activeTab === 'performance'"
          :findings="performanceFindings"
          :loading="performanceLoading"
          :summary="performanceSummary"
          @scan-file="scanPerformanceFile"
          @refresh="loadPerformanceAnalysis"
        />

        <!-- Redis Tab -->
        <RedisOptimizationPanel
          v-if="activeTab === 'redis'"
          :optimizations="redisOptimizations"
          :loading="redisLoading"
          :summary="redisSummary"
          @scan-file="scanRedisFile"
          @refresh="loadRedisAnalysis"
        />

        <!-- Anti-Patterns Tab -->
        <AntiPatternPanel
          v-if="activeTab === 'patterns'"
          :patterns="antiPatterns"
          :loading="patternsLoading"
          :summary="patternsSummary"
          @scan-file="scanPatternFile"
          @refresh="loadPatternAnalysis"
        />
      </div>

      <!-- Scan File Modal -->
      <div
        v-if="showScanFileModal"
        class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
        @click.self="showScanFileModal = false"
      >
        <div class="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
          <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Scan Single File</h3>
          <input
            v-model="scanFilePath"
            type="text"
            placeholder="/path/to/file.py"
            class="w-full px-4 py-2 border border-blueGray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <p class="text-sm text-blueGray-500 mt-2">Enter the path to a Python file to scan.</p>
          <div class="flex justify-end space-x-3 mt-6">
            <button
              @click="showScanFileModal = false"
              class="px-4 py-2 text-blueGray-600 hover:text-blueGray-800"
            >
              Cancel
            </button>
            <button
              @click="scanSingleFile"
              :disabled="!scanFilePath"
              class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              Scan
            </button>
          </div>
        </div>
      </div>

      <!-- Error Toast -->
      <div
        v-if="errorMessage"
        class="fixed bottom-4 right-4 bg-red-500 text-white px-6 py-3 rounded-lg shadow-lg flex items-center"
      >
        <i class="fas fa-exclamation-circle mr-2"></i>
        {{ errorMessage }}
        <button @click="errorMessage = ''" class="ml-4 text-white hover:text-red-200">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'
import { createLogger } from '@/utils/debugUtils'
import HealthScoreCards from '@/components/code-intelligence/HealthScoreCards.vue'
import SecurityFindingsPanel from '@/components/code-intelligence/SecurityFindingsPanel.vue'
import PerformanceIssuesPanel from '@/components/code-intelligence/PerformanceIssuesPanel.vue'
import RedisOptimizationPanel from '@/components/code-intelligence/RedisOptimizationPanel.vue'
import AntiPatternPanel from '@/components/code-intelligence/AntiPatternPanel.vue'

const logger = createLogger('CodeIntelligenceView')
const { get, post } = useApi()

// Default analysis path
const DEFAULT_PATH = '/home/kali/Desktop/AutoBot'

// Tab state
const activeTab = ref('security')
const tabs = computed(() => [
  { id: 'security', label: 'Security', icon: 'fas fa-shield-alt', count: securityFindings.value.length },
  { id: 'performance', label: 'Performance', icon: 'fas fa-tachometer-alt', count: performanceFindings.value.length },
  { id: 'redis', label: 'Redis', icon: 'fas fa-database', count: redisOptimizations.value.length },
  { id: 'patterns', label: 'Patterns', icon: 'fas fa-code', count: antiPatterns.value.length }
])

// Score state
const healthScore = ref({ score: 0, grade: '-', total_issues: 0 })
const securityScore = ref({ score: 0, grade: '-', risk_level: 'unknown' })
const performanceScore = ref({ score: 0, grade: '-', total_issues: 0 })
const redisScore = ref({ score: 0, grade: '-', total_optimizations: 0 })
const scoresLoading = ref(false)

// Analysis state
const isAnalyzing = ref(false)
const securityFindings = ref<any[]>([])
const securityLoading = ref(false)
const securitySummary = ref<any>(null)

const performanceFindings = ref<any[]>([])
const performanceLoading = ref(false)
const performanceSummary = ref<any>(null)

const redisOptimizations = ref<any[]>([])
const redisLoading = ref(false)
const redisSummary = ref<any>(null)

const antiPatterns = ref<any[]>([])
const patternsLoading = ref(false)
const patternsSummary = ref<any>(null)

// Modal state
const showScanFileModal = ref(false)
const scanFilePath = ref('')

// Error handling
const errorMessage = ref('')

// Badge colors based on severity
function getCountBadgeClass(tabId: string): string {
  const counts: Record<string, any[]> = {
    security: securityFindings.value,
    performance: performanceFindings.value,
    redis: redisOptimizations.value,
    patterns: antiPatterns.value
  }

  const items = counts[tabId] || []
  const hasCritical = items.some((i: any) => i.severity === 'critical')
  const hasHigh = items.some((i: any) => i.severity === 'high')

  if (hasCritical) return 'bg-red-100 text-red-700'
  if (hasHigh) return 'bg-orange-100 text-orange-700'
  if (items.length > 0) return 'bg-yellow-100 text-yellow-700'
  return 'bg-green-100 text-green-700'
}

// Load all health scores
async function loadAllScores(): Promise<void> {
  scoresLoading.value = true
  try {
    const [health, security, performance, redis] = await Promise.allSettled([
      get(`/api/code-intelligence/health-score?path=${encodeURIComponent(DEFAULT_PATH)}`),
      get(`/api/code-intelligence/security/score?path=${encodeURIComponent(DEFAULT_PATH)}`),
      get(`/api/code-intelligence/performance/score?path=${encodeURIComponent(DEFAULT_PATH)}`),
      get(`/api/code-intelligence/redis/health-score?path=${encodeURIComponent(DEFAULT_PATH)}`)
    ])

    if (health.status === 'fulfilled' && health.value?.data) {
      healthScore.value = health.value.data
    }
    if (security.status === 'fulfilled' && security.value?.data) {
      securityScore.value = security.value.data
    }
    if (performance.status === 'fulfilled' && performance.value?.data) {
      performanceScore.value = performance.value.data
    }
    if (redis.status === 'fulfilled' && redis.value?.data) {
      redisScore.value = redis.value.data
    }
  } catch (error) {
    logger.error('Failed to load scores:', error)
    errorMessage.value = 'Failed to load health scores'
  } finally {
    scoresLoading.value = false
  }
}

// Load security analysis
async function loadSecurityAnalysis(): Promise<void> {
  securityLoading.value = true
  try {
    const response = await post('/api/code-intelligence/security/analyze', {
      path: DEFAULT_PATH
    })
    if (response?.data) {
      securityFindings.value = response.data.findings || []
      securitySummary.value = response.data.summary || null
    }
  } catch (error) {
    logger.error('Security analysis failed:', error)
    errorMessage.value = 'Security analysis failed'
  } finally {
    securityLoading.value = false
  }
}

// Load performance analysis
async function loadPerformanceAnalysis(): Promise<void> {
  performanceLoading.value = true
  try {
    const response = await post('/api/code-intelligence/performance/analyze', {
      path: DEFAULT_PATH
    })
    if (response?.data) {
      performanceFindings.value = response.data.findings || []
      performanceSummary.value = response.data.summary || null
    }
  } catch (error) {
    logger.error('Performance analysis failed:', error)
    errorMessage.value = 'Performance analysis failed'
  } finally {
    performanceLoading.value = false
  }
}

// Load Redis analysis
async function loadRedisAnalysis(): Promise<void> {
  redisLoading.value = true
  try {
    const response = await post('/api/code-intelligence/redis/analyze', {
      path: DEFAULT_PATH
    })
    if (response?.data) {
      redisOptimizations.value = response.data.optimizations || []
      redisSummary.value = response.data.summary || null
    }
  } catch (error) {
    logger.error('Redis analysis failed:', error)
    errorMessage.value = 'Redis analysis failed'
  } finally {
    redisLoading.value = false
  }
}

// Load anti-pattern analysis
async function loadPatternAnalysis(): Promise<void> {
  patternsLoading.value = true
  try {
    const response = await post('/api/code-intelligence/analyze', {
      path: DEFAULT_PATH
    })
    if (response?.data?.report) {
      antiPatterns.value = response.data.report.anti_patterns || []
      patternsSummary.value = response.data.report || null
    }
  } catch (error) {
    logger.error('Pattern analysis failed:', error)
    errorMessage.value = 'Anti-pattern analysis failed'
  } finally {
    patternsLoading.value = false
  }
}

// Run full analysis
async function runFullAnalysis(): Promise<void> {
  isAnalyzing.value = true
  errorMessage.value = ''

  try {
    await Promise.all([
      loadAllScores(),
      loadSecurityAnalysis(),
      loadPerformanceAnalysis(),
      loadRedisAnalysis(),
      loadPatternAnalysis()
    ])
    logger.info('Full analysis completed')
  } catch (error) {
    logger.error('Full analysis failed:', error)
    errorMessage.value = 'Analysis failed. Check console for details.'
  } finally {
    isAnalyzing.value = false
  }
}

// Scan single file based on active tab
async function scanSingleFile(): Promise<void> {
  if (!scanFilePath.value) return

  showScanFileModal.value = false
  const path = scanFilePath.value

  switch (activeTab.value) {
    case 'security':
      await scanSecurityFile(path)
      break
    case 'performance':
      await scanPerformanceFile(path)
      break
    case 'redis':
      await scanRedisFile(path)
      break
    case 'patterns':
      await scanPatternFile(path)
      break
  }

  scanFilePath.value = ''
}

// Scan file for security issues
async function scanSecurityFile(filePath: string): Promise<void> {
  securityLoading.value = true
  try {
    const response = await post('/api/code-intelligence/security/scan-file', {
      file_path: filePath
    })
    if (response?.data) {
      securityFindings.value = response.data.findings || []
    }
  } catch (error) {
    logger.error('Security file scan failed:', error)
    errorMessage.value = `Failed to scan ${filePath}`
  } finally {
    securityLoading.value = false
  }
}

// Scan file for performance issues
async function scanPerformanceFile(filePath: string): Promise<void> {
  performanceLoading.value = true
  try {
    const response = await post('/api/code-intelligence/performance/scan-file', {
      file_path: filePath
    })
    if (response?.data) {
      performanceFindings.value = response.data.findings || []
    }
  } catch (error) {
    logger.error('Performance file scan failed:', error)
    errorMessage.value = `Failed to scan ${filePath}`
  } finally {
    performanceLoading.value = false
  }
}

// Scan file for Redis optimizations
async function scanRedisFile(filePath: string): Promise<void> {
  redisLoading.value = true
  try {
    const response = await post('/api/code-intelligence/redis/scan-file', {
      file_path: filePath
    })
    if (response?.data) {
      redisOptimizations.value = response.data.optimizations || []
    }
  } catch (error) {
    logger.error('Redis file scan failed:', error)
    errorMessage.value = `Failed to scan ${filePath}`
  } finally {
    redisLoading.value = false
  }
}

// Scan file for anti-patterns
async function scanPatternFile(filePath: string): Promise<void> {
  patternsLoading.value = true
  try {
    const response = await post('/api/code-intelligence/scan-file', {
      file_path: filePath
    })
    if (response?.data) {
      antiPatterns.value = response.data.patterns || []
    }
  } catch (error) {
    logger.error('Pattern file scan failed:', error)
    errorMessage.value = `Failed to scan ${filePath}`
  } finally {
    patternsLoading.value = false
  }
}

// Load initial data
onMounted(() => {
  loadAllScores()
})
</script>

<style scoped>
.code-intelligence-view {
  min-height: 100vh;
  background-color: #f8fafc;
}

.tab-content {
  min-height: 400px;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>