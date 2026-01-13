<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  SystemValidationDashboard.vue - Main System Validation Dashboard
  Integrates with /api/system-validation/* backend endpoints (Issue #581)
-->
<template>
  <div class="system-validation-dashboard">
    <!-- Dashboard Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h1 class="dashboard-title">
          <i class="fas fa-check-circle"></i>
          System Validation
        </h1>
        <p class="dashboard-subtitle">
          Real-time system health monitoring and validation testing
        </p>
      </div>
      <div class="header-controls">
        <div class="auto-refresh-control">
          <label class="toggle-label">
            <input type="checkbox" v-model="autoRefresh" @change="toggleAutoRefresh">
            <span class="toggle-text">Auto-refresh ({{ refreshInterval }}s)</span>
          </label>
        </div>
        <button
          class="refresh-btn"
          @click="refreshAllData"
          :disabled="loading"
          title="Refresh all data"
        >
          <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
          Refresh
        </button>
      </div>
    </div>

    <!-- Overall Health Status Bar -->
    <div class="health-status-bar" :class="overallHealthClass">
      <div class="health-indicator">
        <i :class="healthIcon"></i>
        <span class="health-text">{{ healthStatusText }}</span>
        <span class="health-score" v-if="quickValidation.overall_score !== undefined">
          Score: {{ quickValidation.overall_score.toFixed(1) }}%
        </span>
      </div>
      <div class="health-timestamp" v-if="quickValidation.timestamp">
        Last check: {{ formatTimestamp(quickValidation.timestamp) }}
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="dashboard-grid">
      <!-- Left Column: Health Grid & Timeline -->
      <div class="left-column">
        <!-- VM Health Grid -->
        <SystemHealthGrid
          :vms="vmHealthData"
          :loading="loadingHealth"
          @refresh-vm="refreshVmHealth"
        />

        <!-- Health Timeline -->
        <HealthTimeline
          :history="healthHistory"
          :loading="loadingHistory"
        />
      </div>

      <!-- Right Column: Test Runner & Emergency Controls -->
      <div class="right-column">
        <!-- Validation Test Runner -->
        <ValidationTestRunner
          :components="availableComponents"
          :lastResults="lastValidationResults"
          :running="runningValidation"
          @run-quick="runQuickValidation"
          @run-comprehensive="runComprehensiveValidation"
          @run-component="runComponentValidation"
        />

        <!-- Emergency Controls -->
        <EmergencyControls
          :systemStatus="systemStatus"
          @emergency-stop="handleEmergencyStop"
        />

        <!-- Recommendations Panel -->
        <BasePanel variant="bordered" size="medium" v-if="recommendations.length > 0">
          <template #header>
            <h2><i class="fas fa-lightbulb"></i> Recommendations</h2>
          </template>
          <div class="recommendations-list">
            <div
              v-for="(rec, index) in recommendations"
              :key="index"
              class="recommendation-item"
            >
              <span class="rec-component">{{ rec.component }}</span>
              <span class="rec-text">{{ rec.recommendation }}</span>
            </div>
          </div>
        </BasePanel>
      </div>
    </div>

    <!-- Component Status Cards -->
    <div class="components-section">
      <BasePanel variant="bordered" size="medium">
        <template #header>
          <div class="panel-header-content">
            <h2><i class="fas fa-cubes"></i> Component Status</h2>
            <span class="component-count">{{ Object.keys(componentStatus).length }} components</span>
          </div>
        </template>
        <div class="components-grid">
          <ComponentStatusCard
            v-for="(status, name) in componentStatus"
            :key="name"
            :name="String(name)"
            :status="status"
            @validate="runComponentValidation(String(name))"
          />
        </div>
      </BasePanel>
    </div>

    <!-- Footer -->
    <div class="dashboard-footer">
      Last updated: {{ lastUpdated }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import SystemHealthGrid from './SystemHealthGrid.vue'
import ValidationTestRunner from './ValidationTestRunner.vue'
import EmergencyControls from './EmergencyControls.vue'
import HealthTimeline from './HealthTimeline.vue'
import ComponentStatusCard from './ComponentStatusCard.vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getConfig } from '@/config/ssot-config'

const config = getConfig()

const logger = createLogger('SystemValidationDashboard')

// =============================================================================
// State
// =============================================================================

const loading = ref(false)
const loadingHealth = ref(false)
const loadingHistory = ref(false)
const runningValidation = ref(false)
const autoRefresh = ref(true)
const refreshInterval = ref(30)
let refreshTimer: ReturnType<typeof setInterval> | null = null

// Data state
const quickValidation = ref<{
  status: string
  overall_score: number
  components: Record<string, ComponentQuickStatus>
  timestamp: string
}>({
  status: 'unknown',
  overall_score: 0,
  components: {},
  timestamp: ''
})

const systemStatus = ref<{
  validation_system: string
  available_validations: string[]
  last_validation: string | null
  system_health: string
  timestamp: string
}>({
  validation_system: 'unknown',
  available_validations: [],
  last_validation: null,
  system_health: 'unknown',
  timestamp: ''
})

const vmHealthData = ref<VMHealth[]>([])
const healthHistory = ref<HealthHistoryEntry[]>([])
const recommendations = ref<Recommendation[]>([])
const componentStatus = ref<Record<string, ComponentStatus>>({})
const lastValidationResults = ref<ValidationResult | null>(null)
const lastUpdated = ref('')

// =============================================================================
// Types
// =============================================================================

interface ComponentQuickStatus {
  status: string
  score: number
  message: string
}

interface VMHealth {
  name: string
  ip: string
  port: number
  status: 'healthy' | 'degraded' | 'critical' | 'offline'
  responseTime: number
  healthScore: number
  lastCheck: string
  services: string[]
}

interface HealthHistoryEntry {
  timestamp: string
  score: number
  status: string
  componentScores: Record<string, number>
}

interface Recommendation {
  component: string
  recommendation: string
}

interface ComponentStatus {
  status: string
  score: number
  message: string
  lastValidated?: string
  details?: Record<string, unknown>
}

interface ValidationResult {
  validation_id: string
  status: string
  overall_score: number
  component_scores: Record<string, number>
  recommendations: string[]
  test_results: Record<string, unknown>
  execution_time: number
  timestamp: string
}

// API Response types
interface QuickValidationResponse {
  status: string
  overall_score: number
  components: Record<string, ComponentQuickStatus>
  timestamp: string
}

interface SystemStatusResponse {
  validation_system: string
  available_validations: string[]
  last_validation: string | null
  system_health: string
  timestamp: string
}

interface RecommendationsResponse {
  total_recommendations: number
  recommendations: Recommendation[]
  timestamp: string
}

interface HealthDetailedResponse {
  status: string
  components: Record<string, string>
  timestamp: string
}

interface ComponentValidationResponse {
  component: string
  status: string
  score: number
  details: Record<string, unknown>
  timestamp: string
}

// =============================================================================
// Computed
// =============================================================================

const availableComponents = computed(() => systemStatus.value.available_validations || [])

const overallHealthClass = computed(() => {
  const score = quickValidation.value.overall_score
  if (score >= 90) return 'health-excellent'
  if (score >= 80) return 'health-healthy'
  if (score >= 60) return 'health-warning'
  if (score >= 40) return 'health-degraded'
  return 'health-critical'
})

const healthStatusText = computed(() => {
  const score = quickValidation.value.overall_score
  if (score >= 90) return 'Excellent'
  if (score >= 80) return 'Healthy'
  if (score >= 60) return 'Warning'
  if (score >= 40) return 'Degraded'
  return 'Critical'
})

const healthIcon = computed(() => {
  const score = quickValidation.value.overall_score
  if (score >= 90) return 'fas fa-heart text-green-500'
  if (score >= 80) return 'fas fa-heartbeat text-green-400'
  if (score >= 60) return 'fas fa-heart-crack text-yellow-500'
  if (score >= 40) return 'fas fa-heart-pulse text-orange-500'
  return 'fas fa-skull text-red-500'
})

// =============================================================================
// API Methods
// =============================================================================

const fetchQuickValidation = async () => {
  try {
    const response = await apiClient.get('/api/system-validation/validate/quick') as unknown as QuickValidationResponse
    if (response) {
      quickValidation.value = {
        status: response.status || 'unknown',
        overall_score: response.overall_score || 0,
        components: response.components || {},
        timestamp: response.timestamp || ''
      }

      // Update component status from quick validation
      componentStatus.value = response.components || {}
    }
  } catch (error) {
    logger.error('Failed to fetch quick validation:', error)
  }
}

const fetchSystemStatus = async () => {
  try {
    const response = await apiClient.get('/api/system-validation/validate/status') as unknown as SystemStatusResponse
    if (response) {
      systemStatus.value = {
        validation_system: response.validation_system || 'unknown',
        available_validations: response.available_validations || [],
        last_validation: response.last_validation,
        system_health: response.system_health || 'unknown',
        timestamp: response.timestamp || ''
      }
    }
  } catch (error) {
    logger.error('Failed to fetch system status:', error)
  }
}

const fetchRecommendations = async () => {
  try {
    const response = await apiClient.get('/api/system-validation/validate/recommendations') as unknown as RecommendationsResponse
    if (response && response.recommendations) {
      recommendations.value = response.recommendations
    }
  } catch (error) {
    logger.error('Failed to fetch recommendations:', error)
  }
}

const fetchVmHealth = async () => {
  loadingHealth.value = true
  try {
    // Get health from each VM using the detailed health endpoint
    const response = await apiClient.get('/api/system/health/detailed') as unknown as HealthDetailedResponse
    if (response && response.components) {
      // Build VM health data from infrastructure config
      vmHealthData.value = buildVmHealthFromConfig(response.components)
    }
  } catch (error) {
    logger.error('Failed to fetch VM health:', error)
    // Fallback to config-based data
    vmHealthData.value = buildVmHealthFromConfig({})
  } finally {
    loadingHealth.value = false
  }
}

const buildVmHealthFromConfig = (healthData: Record<string, string>): VMHealth[] => {
  const vms: VMHealth[] = [
    {
      name: 'Main (WSL)',
      ip: config.vm.main,
      port: config.port.backend,
      status: determineStatus(healthData.backend),
      responseTime: 0,
      healthScore: healthData.backend === 'healthy' ? 100 : 50,
      lastCheck: new Date().toISOString(),
      services: ['Backend API', 'VNC Desktop']
    },
    {
      name: 'Frontend (VM1)',
      ip: config.vm.frontend,
      port: config.port.frontend,
      status: 'healthy', // Assume healthy if we can load this page
      responseTime: 0,
      healthScore: 100,
      lastCheck: new Date().toISOString(),
      services: ['Web Interface']
    },
    {
      name: 'NPU Worker (VM2)',
      ip: config.vm.npu,
      port: config.port.npu,
      status: determineStatus(healthData.npu),
      responseTime: 0,
      healthScore: healthData.npu === 'healthy' ? 100 : 0,
      lastCheck: new Date().toISOString(),
      services: ['NPU Acceleration', 'OpenVINO']
    },
    {
      name: 'Redis (VM3)',
      ip: config.vm.redis,
      port: config.port.redis,
      status: determineStatus(healthData.redis),
      responseTime: 0,
      healthScore: healthData.redis === 'healthy' ? 100 : 0,
      lastCheck: new Date().toISOString(),
      services: ['Redis Stack', 'Data Layer']
    },
    {
      name: 'AI Stack (VM4)',
      ip: config.vm.aistack,
      port: config.port.aistack,
      status: determineStatus(healthData.ai_stack),
      responseTime: 0,
      healthScore: healthData.ai_stack === 'healthy' ? 100 : 0,
      lastCheck: new Date().toISOString(),
      services: ['AI Processing', 'ChromaDB']
    },
    {
      name: 'Browser (VM5)',
      ip: config.vm.browser,
      port: config.port.browser,
      status: determineStatus(healthData.browser),
      responseTime: 0,
      healthScore: healthData.browser === 'healthy' ? 100 : 0,
      lastCheck: new Date().toISOString(),
      services: ['Playwright', 'Automation']
    }
  ]
  return vms
}

const determineStatus = (status: string | undefined): 'healthy' | 'degraded' | 'critical' | 'offline' => {
  if (!status) return 'offline'
  const s = status.toLowerCase()
  if (s === 'healthy' || s === 'available') return 'healthy'
  if (s === 'degraded' || s === 'warning') return 'degraded'
  if (s === 'unavailable' || s === 'error') return 'critical'
  return 'offline'
}

const runQuickValidation = async () => {
  runningValidation.value = true
  try {
    await fetchQuickValidation()
    await fetchRecommendations()
    addToHistory()
  } finally {
    runningValidation.value = false
  }
}

const runComprehensiveValidation = async () => {
  runningValidation.value = true
  try {
    const response = await apiClient.post('/api/system-validation/validate/comprehensive', {
      validation_type: 'comprehensive',
      include_performance_tests: true,
      include_stress_tests: false,
      timeout_seconds: 300
    }) as unknown as ValidationResult
    if (response) {
      lastValidationResults.value = response
      await refreshAllData()
    }
  } catch (error) {
    logger.error('Comprehensive validation failed:', error)
  } finally {
    runningValidation.value = false
  }
}

const runComponentValidation = async (componentName: string) => {
  runningValidation.value = true
  try {
    const response = await apiClient.get(`/api/system-validation/validate/component/${componentName}`) as unknown as ComponentValidationResponse
    if (response) {
      // Update component status
      componentStatus.value[componentName] = {
        status: response.status || 'unknown',
        score: response.score || 0,
        message: (response.details?.message as string) || '',
        lastValidated: response.timestamp,
        details: response.details
      }
    }
  } catch (error) {
    logger.error(`Component validation failed for ${componentName}:`, error)
  } finally {
    runningValidation.value = false
  }
}

const refreshVmHealth = async (vmName: string) => {
  logger.debug(`Refreshing health for VM: ${vmName}`)
  await fetchVmHealth()
}

const handleEmergencyStop = async () => {
  try {
    await apiClient.post('/api/system/emergency-stop', {})
    logger.warn('Emergency stop triggered!')
    await refreshAllData()
  } catch (error) {
    logger.error('Emergency stop failed:', error)
  }
}

const addToHistory = () => {
  const entry: HealthHistoryEntry = {
    timestamp: new Date().toISOString(),
    score: quickValidation.value.overall_score,
    status: quickValidation.value.status,
    componentScores: Object.fromEntries(
      Object.entries(quickValidation.value.components).map(([k, v]) => [k, v.score])
    )
  }
  healthHistory.value.unshift(entry)
  // Keep last 20 entries
  if (healthHistory.value.length > 20) {
    healthHistory.value = healthHistory.value.slice(0, 20)
  }
}

// =============================================================================
// Refresh & Lifecycle
// =============================================================================

const refreshAllData = async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchQuickValidation(),
      fetchSystemStatus(),
      fetchRecommendations(),
      fetchVmHealth()
    ])
    lastUpdated.value = new Date().toLocaleTimeString()
  } catch (error) {
    logger.error('Failed to refresh data:', error)
  } finally {
    loading.value = false
  }
}

const toggleAutoRefresh = () => {
  if (autoRefresh.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  refreshTimer = setInterval(() => {
    refreshAllData()
  }, refreshInterval.value * 1000)
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'N/A'
  try {
    return new Date(timestamp).toLocaleTimeString()
  } catch {
    return timestamp
  }
}

onMounted(() => {
  refreshAllData()
  if (autoRefresh.value) {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.system-validation-dashboard {
  max-width: 1600px;
  margin: 0 auto;
  padding: var(--spacing-5);
}

/* Header */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-6);
  padding: var(--spacing-5);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
  border-radius: var(--radius-lg);
  color: white;
}

.dashboard-title {
  margin: 0;
  font-size: var(--text-2xl);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.dashboard-subtitle {
  margin: var(--spacing-2) 0 0;
  opacity: 0.9;
  font-size: var(--text-sm);
}

.header-controls {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
  flex-wrap: wrap;
}

.auto-refresh-control {
  display: flex;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  font-size: var(--text-sm);
}

.toggle-label input {
  accent-color: white;
}

.refresh-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.15);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  transition: all var(--duration-150) var(--ease-in-out);
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.25);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Health Status Bar */
.health-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  margin-bottom: var(--spacing-6);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  font-weight: var(--font-semibold);
}

.health-indicator i {
  font-size: var(--text-xl);
}

.health-text {
  font-size: var(--text-base);
}

.health-score {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding-left: var(--spacing-3);
  border-left: 1px solid var(--border-default);
}

.health-timestamp {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Health status bar variants */
.health-status-bar.health-excellent {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.health-status-bar.health-excellent .health-text {
  color: var(--color-success);
}

.health-status-bar.health-healthy {
  border-color: var(--color-success-light);
  background: var(--color-success-bg);
}

.health-status-bar.health-healthy .health-text {
  color: var(--color-success-light);
}

.health-status-bar.health-warning {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.health-status-bar.health-warning .health-text {
  color: var(--color-warning);
}

.health-status-bar.health-degraded {
  border-color: var(--chart-orange);
  background: rgba(249, 115, 22, 0.1);
}

.health-status-bar.health-degraded .health-text {
  color: var(--chart-orange);
}

.health-status-bar.health-critical {
  border-color: var(--color-error);
  background: var(--color-error-bg);
  animation: pulse-critical 2s ease-in-out infinite;
}

.health-status-bar.health-critical .health-text {
  color: var(--color-error);
}

@keyframes pulse-critical {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.2);
  }
}

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-6);
}

.left-column,
.right-column {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* Panel headers */
.panel-header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  width: 100%;
}

.panel-header-content h2 {
  margin: 0;
  font-size: var(--text-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header-content h2 i {
  color: var(--color-primary);
}

.component-count {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-normal);
}

/* Recommendations */
.recommendations-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.recommendation-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-warning);
}

.rec-component {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-warning);
  text-transform: uppercase;
}

.rec-text {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

/* Components Section */
.components-section {
  margin-top: var(--spacing-6);
}

.components-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: var(--spacing-4);
}

/* Footer */
.dashboard-footer {
  text-align: center;
  padding: var(--spacing-4);
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-6);
}

/* Responsive */
@media (max-width: 1200px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .header-controls {
    width: 100%;
    justify-content: center;
  }

  .health-status-bar {
    flex-direction: column;
    gap: var(--spacing-2);
    text-align: center;
  }

  .health-score {
    padding-left: 0;
    border-left: none;
    padding-top: var(--spacing-1);
    border-top: 1px solid var(--border-default);
  }

  .components-grid {
    grid-template-columns: 1fr;
  }
}
</style>
