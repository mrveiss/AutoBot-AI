<template>
  <div class="system-monitor-enhanced">
    <!-- Overview Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <!-- System Status Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-green-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">System Status</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ systemStatus.status }}</p>
            <p class="mt-2 text-sm text-gray-600">{{ systemStatus.message }}</p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-server text-3xl" :class="systemStatus.iconClass"></i>
          </div>
        </div>
      </div>

      <!-- Active Sessions Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-blue-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Active Sessions</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ activeSessions }}</p>
            <p class="mt-2 text-sm text-green-600">
              <i class="fas fa-arrow-up"></i>
              {{ sessionsChange }}% from last hour
            </p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-users text-3xl text-blue-500"></i>
          </div>
        </div>
      </div>

      <!-- Knowledge Base Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-purple-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Knowledge Items</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ knowledgeStats.totalItems }}</p>
            <p class="mt-2 text-sm text-gray-600">{{ knowledgeStats.categories }} categories</p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-brain text-3xl text-purple-500"></i>
          </div>
        </div>
      </div>

      <!-- Performance Score Card -->
      <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-yellow-500">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wide">Performance</h3>
            <p class="mt-2 text-3xl font-extrabold text-gray-900">{{ performanceScore }}%</p>
            <p class="mt-2 text-sm" :class="performanceChange >= 0 ? 'text-green-600' : 'text-red-600'">
              <i :class="performanceChange >= 0 ? 'fas fa-arrow-up' : 'fas fa-arrow-down'"></i>
              {{ Math.abs(performanceChange) }}% from yesterday
            </p>
          </div>
          <div class="flex-shrink-0">
            <i class="fas fa-tachometer-alt text-3xl text-yellow-500"></i>
          </div>
        </div>
      </div>
    </div>

    <!-- Multi-Machine Infrastructure Overview -->
    <div class="mb-8">
      <MultiMachineHealth />
    </div>

    <!-- Detailed System Monitor Grid -->
    <div class="monitor-grid">
      <!-- Performance Metrics -->
      <BasePanel variant="elevated" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3>System Performance</h3>
            <div class="header-status">
              <span v-if="metricsError" class="error-indicator" title="Failed to fetch metrics">!</span>
              <div class="refresh-indicator" :class="{ spinning: isRefreshing || metricsLoading }">⟳</div>
            </div>
          </div>
        </template>
        <div class="metric-content">
          <div v-if="metricsLoading && !metrics.cpu" class="loading-state">
            Loading system metrics...
          </div>
          <div v-else-if="metricsError && !metrics.cpu" class="error-state">
            {{ metricsError }}
          </div>
          <div class="metric-item">
            <div class="metric-label">CPU Usage</div>
            <div class="metric-bar">
              <div class="bar-fill cpu" :style="{ width: `${metrics.cpu}%` }"></div>
              <span class="metric-value">{{ metrics.cpu }}%</span>
            </div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Memory Usage</div>
            <div class="metric-bar">
              <div class="bar-fill memory" :style="{ width: `${metrics.memory}%` }"></div>
              <span class="metric-value">{{ metrics.memory }}%</span>
            </div>
          </div>
          <div class="metric-item">
            <div class="metric-label">GPU Usage</div>
            <div class="metric-bar">
              <div class="bar-fill gpu" :style="{ width: `${metrics.gpu}%` }"></div>
              <span class="metric-value">{{ metrics.gpu }}%</span>
            </div>
          </div>
          <div class="metric-item">
            <div class="metric-label">NPU Usage</div>
            <div class="metric-bar">
              <div class="bar-fill npu" :style="{ width: `${metrics.npu}%` }"></div>
              <span class="metric-value">{{ metrics.npu }}%</span>
            </div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Network I/O</div>
            <div class="metric-bar">
              <div class="bar-fill network" :style="{ width: `${metrics.network}%` }"></div>
              <span class="metric-value">{{ formatBytes(metrics.networkSpeed) }}/s</span>
            </div>
          </div>
        </div>
      </BasePanel>

      <!-- Service Status -->
      <BasePanel variant="elevated" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3>Service Status</h3>
            <div class="status-summary">{{ onlineServices }}/{{ totalServices }} Online</div>
          </div>
        </template>
        <div class="status-content">
          <div class="service-item" v-for="service in services" :key="service.name">
            <div class="service-info">
              <div class="service-name">{{ service.name }}</div>
              <div class="service-version">{{ service.version }}</div>
            </div>
            <div class="service-status" :class="service.status">
              <div class="status-dot"></div>
              <span>{{ service.statusText }}</span>
            </div>
          </div>
        </div>
      </BasePanel>

      <!-- Real-time Chart -->
      <BasePanel variant="elevated" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3>Performance History</h3>
            <div class="chart-controls">
              <button
                v-for="timeframe in timeframes"
                :key="timeframe.value"
                class="time-btn"
                :class="{ active: selectedTimeframe === timeframe.value }"
                @click="selectedTimeframe = timeframe.value"
                :aria-label="timeframe.label">
                {{ timeframe.label }}
              </button>
            </div>
          </div>
        </template>
        <div class="chart-content">
          <canvas ref="performanceChart" width="400" height="200"></canvas>
        </div>
      </BasePanel>

      <!-- API Health -->
      <BasePanel variant="elevated" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3>API Health</h3>
            <div class="api-stats">{{ healthyEndpoints }}/{{ totalEndpoints }} Healthy</div>
          </div>
        </template>
        <div class="api-content">
          <div class="endpoint-group" v-for="group in apiEndpoints" :key="group.name">
            <div class="group-name">{{ group.name }}</div>
            <div class="endpoint-list">
              <div
                v-for="endpoint in group.endpoints"
                :key="endpoint.path"
                class="endpoint-item"
                :class="endpoint.status">
                <span class="endpoint-path">{{ endpoint.path }}</span>
                <span class="endpoint-time">{{ endpoint.responseTime }}ms</span>
              </div>
            </div>
          </div>
        </div>
      </BasePanel>

      <!-- Quick Actions -->
      <BasePanel variant="elevated" size="medium">
        <template #header>
          <h3>Quick Actions</h3>
        </template>
        <div class="actions-content">
          <router-link to="/chat" class="action-item">
            <i class="fas fa-comments action-icon-blue"></i>
            <span>Start New Chat</span>
          </router-link>
          <router-link to="/knowledge/upload" class="action-item">
            <i class="fas fa-upload action-icon-green"></i>
            <span>Upload Document</span>
          </router-link>
          <router-link to="/tools/terminal" class="action-item">
            <i class="fas fa-terminal action-icon-default"></i>
            <span>Open Terminal</span>
          </router-link>
          <router-link to="/monitoring/logs" class="action-item">
            <i class="fas fa-file-alt action-icon-purple"></i>
            <span>View Logs</span>
          </router-link>
        </div>
      </BasePanel>

      <!-- Recent Activity -->
      <BasePanel variant="elevated" size="medium">
        <template #header>
          <h3>Recent Activity</h3>
        </template>
        <div class="activity-content">
          <div v-for="activity in recentActivity" :key="activity.id" class="activity-item">
            <div class="activity-icon">
              <i :class="activity.icon"></i>
            </div>
            <div class="activity-info">
              <div class="activity-action">{{ activity.action }}</div>
              <div class="activity-time">{{ activity.time }}</div>
            </div>
          </div>
        </div>
      </BasePanel>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { ServiceStatus, KnowledgeBaseStats } from '@/types/api'
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useServiceMonitor } from '@/composables/useServiceMonitor.js'
import MultiMachineHealth from './MultiMachineHealth.vue'
import { formatFileSize as formatBytes } from '@/utils/formatHelpers'
import BasePanel from '@/components/base/BasePanel.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SystemMonitor')

const appStore = useAppStore()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()

// Real-time service monitoring
const serviceMonitor = useServiceMonitor()

// Dashboard computed data based on real services
const systemStatus = computed(() => {
  const overallStatus = serviceMonitor.overallStatus.value || 'unknown'
  const healthyCount = serviceMonitor.healthyServices.value || 0
  const totalServices = serviceMonitor.services.value?.length || 0

  return {
    status: overallStatus === 'online' ? 'Healthy' :
            overallStatus === 'warning' ? 'Warning' :
            overallStatus === 'error' ? 'Error' : 'Unknown',
    message: `${healthyCount}/${totalServices} services operational`,
    iconClass: overallStatus === 'online' ? 'text-green-500' :
              overallStatus === 'warning' ? 'text-yellow-500' : 'text-red-500'
  }
})

// FIXED: Use sessionCount property instead of non-existent conversations
const activeSessions = computed(() => {
  return chatStore.sessionCount || 1
})

const sessionsChange = ref(0)

// FIXED: Use actual knowledge store properties instead of non-existent stats
const knowledgeStats = computed((): KnowledgeBaseStats => ({
  totalItems: knowledgeStore.documentCount || 0,
  categories: knowledgeStore.categoryCount || 0,
  documentCount: knowledgeStore.documentCount || 0,
  categoryCount: knowledgeStore.categoryCount || 0
}))

const performanceScore = computed(() => {
  const services = serviceMonitor.services.value || []
  if (services.length === 0) return 100

  // FIXED: Use proper type casting for service compatibility
  const avgResponseTime = services.reduce((acc: number, service: any) => {
    return acc + (service.responseTime || 0)
  }, 0) / services.length

  // Convert response time to performance score (lower is better)
  return Math.max(0, Math.min(100, Math.round(100 - (avgResponseTime / 10))))
})

const performanceChange = ref(2)

interface ActivityItem {
  id: number;
  action: string;
  time: string;
  icon: string;
}

const recentActivity = ref<ActivityItem[]>([
  {
    id: 1,
    action: 'Dashboard monitoring started',
    time: 'Just now',
    icon: 'fas fa-tachometer-alt'
  },
  {
    id: 2,
    action: 'Service health check completed',
    time: 'Just now',
    icon: 'fas fa-check-circle'
  },
  {
    id: 3,
    action: 'System resources monitored',
    time: '1 minute ago',
    icon: 'fas fa-chart-line'
  },
  {
    id: 4,
    action: 'Real-time monitoring active',
    time: '2 minutes ago',
    icon: 'fas fa-heartbeat'
  }
])

// System Monitor functionality
const isRefreshing = ref(false)

interface SystemMetrics {
  cpu: number;
  memory: number;
  gpu: number;
  npu: number;
  network: number;
  networkSpeed: number;
}

const metrics = ref<SystemMetrics>({
  cpu: 0,
  memory: 0,
  gpu: 0,
  npu: 0,
  network: 0,
  networkSpeed: 0
})

// Loading and error states
const metricsLoading = ref(true)
const metricsError = ref<string | null>(null)

// Fetch real system metrics from backend
const fetchSystemMetrics = async () => {
  try {
    const response = await fetch('/api/monitoring/dashboard/overview')
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()

    // Extract metrics from dashboard response
    const systemMetrics = data.system || {}
    const gpuMetrics = data.gpu || {}
    const npuMetrics = data.npu || {}
    const networkMetrics = data.network || {}

    metrics.value = {
      cpu: systemMetrics.cpu_percent || systemMetrics.cpu_usage || 0,
      memory: systemMetrics.memory_percent || systemMetrics.memory_usage || 0,
      gpu: gpuMetrics.utilization_percent || gpuMetrics.utilization || 0,
      npu: npuMetrics.utilization_percent || npuMetrics.utilization || 0,
      network: networkMetrics.utilization || 0,
      networkSpeed: networkMetrics.bytes_sent_per_sec || networkMetrics.bandwidth || 0
    }

    metricsError.value = null
  } catch (error) {
    logger.error('Failed to fetch system metrics:', error)
    metricsError.value = 'Failed to fetch metrics'
  } finally {
    metricsLoading.value = false
  }
}

// Fetch real API endpoint health
const fetchApiHealth = async () => {
  try {
    // Issue #552: Fixed paths to match backend endpoints
    const endpoints = [
      { path: '/api/health', group: 'Core APIs' },
      { path: '/api/chat/health', group: 'Core APIs' },
      { path: '/api/knowledge_base/health', group: 'Core APIs' },
      { path: '/api/monitoring/status', group: 'System APIs' },
      { path: '/api/agent-terminal/sessions', group: 'System APIs' },  // Issue #552: No /health endpoint, use /sessions instead
      { path: '/api/redis-service/health', group: 'System APIs' }  // Issue #552: Fixed - router is at /redis-service
    ]

    const groups: Record<string, ApiEndpoint[]> = {
      'Core APIs': [],
      'System APIs': []
    }

    await Promise.all(endpoints.map(async (ep) => {
      const startTime = performance.now()
      try {
        const response = await fetch(ep.path, {
          method: 'GET',
          signal: AbortSignal.timeout(5000)
        })
        const responseTime = Math.round(performance.now() - startTime)

        groups[ep.group].push({
          path: ep.path,
          status: response.ok ? 'healthy' : 'warning',
          responseTime
        })
      } catch {
        const responseTime = Math.round(performance.now() - startTime)
        groups[ep.group].push({
          path: ep.path,
          status: 'error',
          responseTime
        })
      }
    }))

    apiEndpoints.value = Object.entries(groups).map(([name, endpoints]) => ({
      name,
      endpoints
    }))
  } catch (error) {
    logger.error('Failed to fetch API health:', error)
  }
}

const services = computed(() => serviceMonitor.services.value || [])
const onlineServices = computed(() => serviceMonitor.healthyServices.value || 0)
const totalServices = computed(() => serviceMonitor.services.value?.length || 0)

interface Timeframe {
  label: string;
  value: string;
}

const timeframes = ref<Timeframe[]>([
  { label: '1H', value: '1h' },
  { label: '24H', value: '24h' },
  { label: '7D', value: '7d' },
  { label: '30D', value: '30d' }
])

const selectedTimeframe = ref('1h')

interface ApiEndpoint {
  path: string;
  status: 'healthy' | 'warning' | 'error';
  responseTime: number;
}

interface ApiGroup {
  name: string;
  endpoints: ApiEndpoint[];
}

// Initialize with empty groups - will be populated by fetchApiHealth()
const apiEndpoints = ref<ApiGroup[]>([
  { name: 'Core APIs', endpoints: [] },
  { name: 'System APIs', endpoints: [] }
])

const healthyEndpoints = computed(() => {
  return apiEndpoints.value.reduce((acc, group) => {
    return acc + group.endpoints.filter(ep => ep.status === 'healthy').length
  }, 0)
})

const totalEndpoints = computed(() => {
  return apiEndpoints.value.reduce((acc, group) => {
    return acc + group.endpoints.length
  }, 0)
})


const performanceChart = ref<HTMLCanvasElement | null>(null)

let refreshInterval: number | null = null

onMounted(async () => {
  // Start real-time monitoring
  serviceMonitor.startMonitoring()

  // Initial fetch of real data
  await Promise.all([
    fetchSystemMetrics(),
    fetchApiHealth()
  ])

  // Refresh metrics every 5 seconds with real backend data
  refreshInterval = window.setInterval(async () => {
    isRefreshing.value = true

    await Promise.all([
      fetchSystemMetrics(),
      fetchApiHealth()
    ])

    setTimeout(() => {
      isRefreshing.value = false
    }, 500)
  }, 5000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  serviceMonitor.stopMonitoring()
})
</script>

<style scoped>
/* ===========================================
 * SystemMonitor.vue - Design Token Migration
 * Issue #704: Migrated to centralized design tokens
 * =========================================== */

.system-monitor-enhanced {
  padding: var(--spacing-6);
  background: var(--bg-surface);
  min-height: 100vh;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-6);
}

.card-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-header-content h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.refresh-indicator {
  font-size: var(--text-xl);
  color: var(--text-secondary);
  cursor: pointer;
  transition: transform var(--duration-300) var(--ease-in-out);
}

.refresh-indicator.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.header-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.error-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  background: var(--color-error);
  color: var(--text-on-error);
  font-weight: var(--font-bold);
  font-size: var(--text-xs);
  border-radius: var(--radius-full);
}

.loading-state,
.error-state {
  padding: var(--spacing-4);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.error-state {
  color: var(--color-error);
}

/* Metric bars */
.metric-item {
  margin-bottom: var(--spacing-4);
}

.metric-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.metric-bar {
  position: relative;
  width: 100%;
  height: 24px;
  background: var(--bg-hover);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-in-out);
  border-radius: var(--radius-xl);
}

.bar-fill.cpu {
  background: linear-gradient(90deg, var(--color-info), var(--color-info-dark));
}

.bar-fill.memory {
  background: linear-gradient(90deg, var(--color-success), var(--color-success-dark));
}

.bar-fill.gpu {
  background: linear-gradient(90deg, var(--chart-purple), var(--chart-purple-light));
}

.bar-fill.npu {
  background: linear-gradient(90deg, var(--color-warning), var(--color-warning-hover));
}

.bar-fill.network {
  background: linear-gradient(90deg, var(--color-error), var(--color-error-hover));
}

.metric-value {
  position: absolute;
  right: var(--spacing-3);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-on-primary);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* Service status */
.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.service-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.service-version {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.service-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
}

.service-status.online .status-dot {
  background: var(--color-success);
}

.service-status.warning .status-dot {
  background: var(--color-warning);
}

.service-status.error .status-dot {
  background: var(--color-error);
}

/* Chart controls */
.chart-controls {
  display: flex;
  gap: var(--spacing-2);
}

.time-btn {
  padding: var(--spacing-1) var(--spacing-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  font-size: var(--text-sm);
}

.time-btn:hover {
  background: var(--bg-hover);
}

.time-btn.active {
  background: var(--color-info);
  color: var(--text-on-primary);
  border-color: var(--color-info);
}

/* API endpoints */
.endpoint-group {
  margin-bottom: var(--spacing-4);
}

.group-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.endpoint-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2);
  margin-bottom: var(--spacing-1);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.endpoint-item.healthy {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.endpoint-item.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.endpoint-item.error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

/* Quick Actions */
.action-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  text-decoration: none;
  color: var(--text-primary);
  transition: background-color var(--duration-200) var(--ease-in-out);
  margin-bottom: var(--spacing-2);
}

.action-item:hover {
  background: var(--bg-hover);
}

/* Action icon colors using design tokens */
.action-icon-blue {
  color: var(--color-info);
}

.action-icon-green {
  color: var(--color-success);
}

.action-icon-default {
  color: var(--text-secondary);
}

.action-icon-purple {
  color: var(--chart-purple);
}

/* Activity */
.activity-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.activity-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--color-info-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-info);
}

.activity-action {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.activity-time {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.status-summary,
.api-stats {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
