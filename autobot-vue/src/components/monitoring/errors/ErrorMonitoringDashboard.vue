<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ErrorMonitoringDashboard.vue - Main Error Monitoring Dashboard
  Integrates with /api/errors/* backend endpoints (Issue #579)
-->
<template>
  <div class="error-monitoring-dashboard">
    <!-- Dashboard Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h1 class="dashboard-title">
          <i class="fas fa-bug"></i>
          Error Monitoring
        </h1>
        <p class="dashboard-subtitle">
          Real-time error tracking and system health monitoring
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
        <button
          class="clear-btn"
          @click="showClearConfirm = true"
          title="Clear error history"
        >
          <i class="fas fa-trash-alt"></i>
          Clear History
        </button>
        <button
          class="test-btn"
          @click="triggerTestError"
          :disabled="testingError"
          title="Test error system (dev only)"
        >
          <i :class="testingError ? 'fas fa-spinner fa-spin' : 'fas fa-flask'"></i>
          Test
        </button>
      </div>
    </div>

    <!-- Health Status Bar -->
    <div class="health-status-bar" :class="healthStatusClass">
      <div class="health-indicator">
        <i :class="healthIcon"></i>
        <span class="health-text">{{ healthStatusText }}</span>
      </div>
      <div class="health-recommendations" v-if="recommendations.length > 0">
        <span class="rec-icon"><i class="fas fa-lightbulb"></i></span>
        <span class="rec-text">{{ recommendations[0] }}</span>
        <span v-if="recommendations.length > 1" class="rec-more">
          +{{ recommendations.length - 1 }} more
        </span>
      </div>
    </div>

    <!-- Statistics Section -->
    <ErrorStatistics :statistics="statistics" />

    <!-- Main Content Grid -->
    <div class="dashboard-grid">
      <!-- Error Feed Panel -->
      <BasePanel variant="bordered" size="medium" class="feed-panel">
        <template #header>
          <div class="panel-header-content">
            <h2><i class="fas fa-stream"></i> Recent Errors</h2>
            <span class="error-total" v-if="recentErrors.length">
              {{ recentErrors.length }} errors
            </span>
          </div>
        </template>
        <ErrorFeed
          :errors="recentErrors"
          @select-error="openErrorDetail"
        />
      </BasePanel>

      <!-- Charts Sidebar -->
      <div class="charts-sidebar">
        <!-- Category Chart -->
        <BasePanel variant="bordered" size="medium">
          <template #header>
            <h2><i class="fas fa-chart-pie"></i> Error Categories</h2>
          </template>
          <ErrorCategoryChart :categories="categories" :height="280" />
        </BasePanel>

        <!-- Component Heatmap -->
        <BasePanel variant="bordered" size="medium">
          <template #header>
            <h2><i class="fas fa-sitemap"></i> Component Errors</h2>
          </template>
          <ErrorComponentMap :data="componentData" :height="250" />
        </BasePanel>
      </div>
    </div>

    <!-- Metrics Summary Panel -->
    <BasePanel variant="bordered" size="medium" class="metrics-panel">
      <template #header>
        <h2><i class="fas fa-chart-line"></i> Error Metrics Summary</h2>
      </template>
      <div class="metrics-grid" v-if="metricsSummary">
        <div class="metric-item">
          <span class="metric-label">Total Tracked</span>
          <span class="metric-value">{{ metricsSummary.total_errors || 0 }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Resolved</span>
          <span class="metric-value success">{{ metricsSummary.resolved_count || 0 }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Retry Rate</span>
          <span class="metric-value">{{ formatPercentage(metricsSummary.retry_rate) }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Avg Resolution Time</span>
          <span class="metric-value">{{ formatDuration(metricsSummary.avg_resolution_time) }}</span>
        </div>
      </div>
      <EmptyState
        v-else
        icon="fas fa-chart-bar"
        message="No metrics data available"
        variant="info"
      />
    </BasePanel>

    <!-- Error Detail Modal -->
    <ErrorDetailModal
      v-model="showErrorDetail"
      :error="selectedError"
      @close="selectedError = null"
      @resolve="markErrorResolved"
    />

    <!-- Clear Confirmation Dialog -->
    <BaseModal
      v-model="showClearConfirm"
      title="Clear Error History"
      size="small"
    >
      <div class="confirm-content">
        <i class="fas fa-exclamation-triangle warning-icon"></i>
        <p>Are you sure you want to clear all error history?</p>
        <p class="confirm-note">This action cannot be undone.</p>
      </div>
      <template #actions>
        <button class="btn btn-secondary" @click="showClearConfirm = false">
          Cancel
        </button>
        <button
          class="btn btn-danger"
          @click="clearErrorHistory"
          :disabled="clearing"
        >
          <i v-if="clearing" class="fas fa-spinner fa-spin"></i>
          Clear History
        </button>
      </template>
    </BaseModal>

    <!-- Footer -->
    <div class="dashboard-footer">
      Last updated: {{ lastUpdated }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorStatistics from './ErrorStatistics.vue'
import ErrorFeed from './ErrorFeed.vue'
import ErrorCategoryChart from './ErrorCategoryChart.vue'
import ErrorComponentMap from './ErrorComponentMap.vue'
import ErrorDetailModal from './ErrorDetailModal.vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { useUserStore } from '@/stores/useUserStore'

const logger = createLogger('ErrorMonitoringDashboard')
const userStore = useUserStore()

// State
const loading = ref(false)
const autoRefresh = ref(true)
const refreshInterval = ref(30)
let refreshTimer: ReturnType<typeof setInterval> | null = null

// Data state
const healthData = ref<{
  health_status: string
  health_score: number
  total_errors: number
  critical_errors: number
  high_errors: number
  recommendations: string[]
}>({
  health_status: 'unknown',
  health_score: 100,
  total_errors: 0,
  critical_errors: 0,
  high_errors: 0,
  recommendations: []
})

// Error report type (shared across components)
interface ErrorReport {
  trace_id?: string
  timestamp: string | number
  error_type?: string
  category?: string
  component?: string
  message: string
  severity?: string
  error_code?: string
  operation?: string
  stack_trace?: string
  context?: Record<string, unknown>
  user_id?: string
  recommendations?: string[]
}

// Metrics summary type
interface MetricsSummary {
  total_errors?: number
  resolved_count?: number
  retry_rate?: number
  avg_resolution_time?: number
}

const recentErrors = ref<ErrorReport[]>([])
const categories = ref<Record<string, { count: number; percentage: number }>>({})
const componentData = ref<{ components: Record<string, number>; most_problematic: Array<[string, number]> }>({
  components: {},
  most_problematic: []
})
const metricsSummary = ref<MetricsSummary | null>(null)
const lastUpdated = ref('')

// Modal state
const showErrorDetail = ref(false)
const selectedError = ref<ErrorReport | null>(null)
const showClearConfirm = ref(false)
const clearing = ref(false)
const testingError = ref(false)

// Computed
const statistics = computed(() => ({
  totalErrors: healthData.value.total_errors,
  criticalErrors: healthData.value.critical_errors,
  highErrors: healthData.value.high_errors,
  healthScore: healthData.value.health_score,
  healthStatus: healthData.value.health_status
}))

const recommendations = computed(() => healthData.value.recommendations || [])

const healthStatusClass = computed(() => {
  const status = healthData.value.health_status.toLowerCase()
  return `health-${status.replace(/_/g, '-')}`
})

const healthStatusText = computed(() => {
  const status = healthData.value.health_status
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
})

const healthIcon = computed(() => {
  const status = healthData.value.health_status.toLowerCase()
  switch (status) {
    case 'excellent':
      return 'fas fa-heart text-green-500'
    case 'healthy':
      return 'fas fa-heartbeat text-green-400'
    case 'warning':
      return 'fas fa-heart-crack text-yellow-500'
    case 'degraded':
      return 'fas fa-heart-pulse text-orange-500'
    case 'critical':
      return 'fas fa-skull text-red-500'
    default:
      return 'fas fa-question-circle text-gray-400'
  }
})

// API Response types for error monitoring endpoints
interface ErrorApiResponse<T = unknown> {
  status: string
  data?: T
  message?: string
}

interface HealthResponseData {
  health_status: string
  health_score: number
  total_errors: number
  critical_errors: number
  high_errors: number
  recommendations: string[]
}

interface RecentErrorsResponseData {
  errors: any[]
  total_count: number
}

interface CategoriesResponseData {
  categories: Record<string, { count: number; percentage: number }>
  total_errors: number
}

interface ComponentsResponseData {
  components: Record<string, number>
  most_problematic: Array<[string, number]>
}

// Methods
const fetchHealthData = async () => {
  try {
    const response = await apiClient.get('/api/errors/health') as unknown as ErrorApiResponse<HealthResponseData>
    if (response.status === 'success' && response.data) {
      healthData.value = {
        health_status: response.data.health_status || 'unknown',
        health_score: response.data.health_score || 100,
        total_errors: response.data.total_errors || 0,
        critical_errors: response.data.critical_errors || 0,
        high_errors: response.data.high_errors || 0,
        recommendations: response.data.recommendations || []
      }
    }
  } catch (error) {
    logger.error('Failed to fetch health data:', error)
  }
}

const fetchRecentErrors = async () => {
  try {
    const response = await apiClient.get('/api/errors/recent?limit=50') as unknown as ErrorApiResponse<RecentErrorsResponseData>
    if (response.status === 'success' && response.data) {
      recentErrors.value = response.data.errors || []
    }
  } catch (error) {
    logger.error('Failed to fetch recent errors:', error)
  }
}

const fetchCategories = async () => {
  try {
    const response = await apiClient.get('/api/errors/categories') as unknown as ErrorApiResponse<CategoriesResponseData>
    if (response.status === 'success' && response.data) {
      categories.value = response.data.categories || {}
    }
  } catch (error) {
    logger.error('Failed to fetch categories:', error)
  }
}

const fetchComponents = async () => {
  try {
    const response = await apiClient.get('/api/errors/components') as unknown as ErrorApiResponse<ComponentsResponseData>
    if (response.status === 'success' && response.data) {
      componentData.value = {
        components: response.data.components || {},
        most_problematic: response.data.most_problematic || []
      }
    }
  } catch (error) {
    logger.error('Failed to fetch components:', error)
  }
}

const fetchMetricsSummary = async () => {
  try {
    const response = await apiClient.get('/api/errors/metrics/summary') as unknown as ErrorApiResponse<unknown>
    if (response.status === 'success' && response.data) {
      metricsSummary.value = response.data
    }
  } catch (error) {
    logger.error('Failed to fetch metrics summary:', error)
  }
}

const refreshAllData = async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchHealthData(),
      fetchRecentErrors(),
      fetchCategories(),
      fetchComponents(),
      fetchMetricsSummary()
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

const openErrorDetail = (error: ErrorReport) => {
  selectedError.value = error
  showErrorDetail.value = true
}

const markErrorResolved = async (traceId: string) => {
  try {
    await apiClient.post(`/api/errors/metrics/resolve/${traceId}`, {})
    // Refresh data after marking resolved
    await refreshAllData()
    showErrorDetail.value = false
    selectedError.value = null
  } catch (error) {
    logger.error('Failed to mark error resolved:', error)
  }
}

const clearErrorHistory = async () => {
  clearing.value = true
  try {
    // This endpoint requires admin auth - use token from user store if available
    const authToken = userStore.authState.token || 'Bearer admin_token'
    await apiClient.post('/api/errors/clear', {}, {
      headers: { Authorization: authToken.startsWith('Bearer ') ? authToken : `Bearer ${authToken}` }
    })
    await refreshAllData()
    showClearConfirm.value = false
  } catch (error) {
    logger.error('Failed to clear error history:', error)
  } finally {
    clearing.value = false
  }
}

const triggerTestError = async () => {
  testingError.value = true
  try {
    await apiClient.post('/api/errors/test-error', {
      error_type: 'ValueError',
      message: 'Test error triggered from Error Monitoring Dashboard'
    })
    // Refresh after triggering test error
    setTimeout(() => refreshAllData(), 1000)
  } catch (error) {
    logger.error('Failed to trigger test error:', error)
  } finally {
    testingError.value = false
  }
}

const formatPercentage = (value?: number): string => {
  if (value === undefined || value === null) return 'N/A'
  return `${(value * 100).toFixed(1)}%`
}

const formatDuration = (seconds?: number): string => {
  if (seconds === undefined || seconds === null) return 'N/A'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

// Lifecycle
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
.error-monitoring-dashboard {
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
  background: linear-gradient(135deg, var(--color-error) 0%, var(--chart-orange) 100%);
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

.refresh-btn,
.clear-btn,
.test-btn {
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

.refresh-btn:hover:not(:disabled),
.clear-btn:hover,
.test-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.25);
}

.refresh-btn:disabled,
.test-btn:disabled {
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
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
}

.health-indicator i {
  font-size: var(--text-xl);
}

.health-text {
  font-size: var(--text-sm);
}

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

.health-recommendations {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.rec-icon {
  color: var(--color-warning);
}

.rec-more {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

/* Dashboard Grid */
.dashboard-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-6);
  margin: var(--spacing-6) 0;
}

.feed-panel {
  min-height: 500px;
}

.feed-panel :deep(.panel-content) {
  padding: 0;
  height: 450px;
  overflow: hidden;
}

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

.error-total {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-normal);
}

.charts-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.charts-sidebar h2 {
  margin: 0;
  font-size: var(--text-base);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.charts-sidebar h2 i {
  color: var(--color-primary);
}

/* Metrics Panel */
.metrics-panel {
  margin-top: var(--spacing-6);
}

.metrics-panel h2 {
  margin: 0;
  font-size: var(--text-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.metrics-panel h2 i {
  color: var(--color-primary);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-4);
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  text-align: center;
}

.metric-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.metric-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.metric-value.success {
  color: var(--color-success);
}

/* Confirmation Dialog */
.confirm-content {
  text-align: center;
  padding: var(--spacing-4);
}

.warning-icon {
  font-size: var(--text-4xl);
  color: var(--color-warning);
  margin-bottom: var(--spacing-4);
}

.confirm-note {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* Button styles */
.btn {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: all var(--duration-150) var(--ease-in-out);
  border: none;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-danger {
  background: var(--color-error);
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: var(--color-error-dark);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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
@media (max-width: 1024px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .charts-sidebar {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .charts-sidebar > * {
    flex: 1;
    min-width: 300px;
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

  .charts-sidebar {
    flex-direction: column;
  }

  .charts-sidebar > * {
    min-width: auto;
  }

  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
