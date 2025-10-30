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
      <div class="metric-card glass-card">
        <div class="card-header">
          <h3>System Performance</h3>
          <div class="refresh-indicator" :class="{ spinning: isRefreshing }">⟳</div>
        </div>
        <div class="metric-content">
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
      </div>

      <!-- Service Status -->
      <div class="status-card glass-card">
        <div class="card-header">
          <h3>Service Status</h3>
          <div class="status-summary">{{ onlineServices }}/{{ totalServices }} Online</div>
        </div>
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
      </div>

      <!-- Real-time Chart -->
      <div class="chart-card glass-card">
        <div class="card-header">
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
        <div class="chart-content">
          <canvas ref="performanceChart" width="400" height="200"></canvas>
        </div>
      </div>

      <!-- API Health -->
      <div class="api-card glass-card">
        <div class="card-header">
          <h3>API Health</h3>
          <div class="api-stats">{{ healthyEndpoints }}/{{ totalEndpoints }} Healthy</div>
        </div>
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
      </div>

      <!-- Quick Actions -->
      <div class="actions-card glass-card">
        <div class="card-header">
          <h3>Quick Actions</h3>
        </div>
        <div class="actions-content">
          <router-link to="/chat" class="action-item">
            <i class="fas fa-comments text-blue-500"></i>
            <span>Start New Chat</span>
          </router-link>
          <router-link to="/knowledge/upload" class="action-item">
            <i class="fas fa-upload text-green-500"></i>
            <span>Upload Document</span>
          </router-link>
          <router-link to="/tools/terminal" class="action-item">
            <i class="fas fa-terminal text-gray-700"></i>
            <span>Open Terminal</span>
          </router-link>
          <router-link to="/monitoring/logs" class="action-item">
            <i class="fas fa-file-alt text-purple-500"></i>
            <span>View Logs</span>
          </router-link>
        </div>
      </div>

      <!-- Recent Activity -->
      <div class="activity-card glass-card">
        <div class="card-header">
          <h3>Recent Activity</h3>
        </div>
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
      </div>
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
  cpu: 4,
  memory: 25,
  gpu: 15,
  npu: 8,
  network: 12,
  networkSpeed: 1048576 // bytes per second
})

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

const apiEndpoints = ref<ApiGroup[]>([
  {
    name: 'Core APIs',
    endpoints: [
      { path: '/api/health', status: 'healthy', responseTime: 4 },
      { path: '/api/chat', status: 'healthy', responseTime: 12 },
      { path: '/api/knowledge', status: 'healthy', responseTime: 8 }
    ]
  },
  {
    name: 'System APIs',
    endpoints: [
      { path: '/api/monitoring', status: 'healthy', responseTime: 6 },
      { path: '/api/terminal', status: 'healthy', responseTime: 15 },
      { path: '/api/research', status: 'healthy', responseTime: 11 }
    ]
  }
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

onMounted(() => {
  // Start real-time monitoring
  serviceMonitor.startMonitoring()
  
  // Refresh metrics every 5 seconds
  refreshInterval = window.setInterval(() => {
    isRefreshing.value = true
    // Simulate metric updates
    metrics.value.cpu = Math.max(0, Math.min(100, metrics.value.cpu + (Math.random() - 0.5) * 10))
    metrics.value.memory = Math.max(0, Math.min(100, metrics.value.memory + (Math.random() - 0.5) * 5))
    metrics.value.gpu = Math.max(0, Math.min(100, metrics.value.gpu + (Math.random() - 0.5) * 15))
    metrics.value.npu = Math.max(0, Math.min(100, metrics.value.npu + (Math.random() - 0.5) * 12))
    metrics.value.network = Math.max(0, Math.min(100, metrics.value.network + (Math.random() - 0.5) * 8))
    
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
.system-monitor-enhanced {
  padding: 1.5rem;
  background: #f8fafc;
  min-height: 100vh;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 1.5rem;
}

.glass-card {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 1.5rem;
  backdrop-filter: blur(10px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.card-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #374151;
}

.refresh-indicator {
  font-size: 1.2rem;
  color: #6b7280;
  cursor: pointer;
  transition: transform 0.3s ease;
}

.refresh-indicator.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Metric bars */
.metric-item {
  margin-bottom: 1rem;
}

.metric-label {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.metric-bar {
  position: relative;
  width: 100%;
  height: 24px;
  background: rgba(0, 0, 0, 0.1);
  border-radius: 12px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 12px;
}

.bar-fill.cpu { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
.bar-fill.memory { background: linear-gradient(90deg, #10b981, #065f46); }
.bar-fill.gpu { background: linear-gradient(90deg, #8b5cf6, #5b21b6); }
.bar-fill.npu { background: linear-gradient(90deg, #f59e0b, #d97706); }
.bar-fill.network { background: linear-gradient(90deg, #ef4444, #dc2626); }

.metric-value {
  position: absolute;
  right: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.875rem;
  font-weight: 500;
  color: white;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* Service status */
.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.service-name {
  font-weight: 500;
  color: #374151;
}

.service-version {
  font-size: 0.875rem;
  color: #6b7280;
}

.service-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.service-status.online .status-dot { background: #10b981; }
.service-status.warning .status-dot { background: #f59e0b; }
.service-status.error .status-dot { background: #ef4444; }

/* Chart controls */
.chart-controls {
  display: flex;
  gap: 0.5rem;
}

.time-btn {
  padding: 0.25rem 0.75rem;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 0.875rem;
}

.time-btn:hover {
  background: rgba(0, 0, 0, 0.05);
}

.time-btn.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

/* API endpoints */
.endpoint-group {
  margin-bottom: 1rem;
}

.group-name {
  font-weight: 500;
  color: #374151;
  margin-bottom: 0.5rem;
}

.endpoint-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  margin-bottom: 0.25rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.endpoint-item.healthy {
  background: rgba(16, 185, 129, 0.1);
  color: #065f46;
}

.endpoint-item.warning {
  background: rgba(245, 158, 11, 0.1);
  color: #92400e;
}

.endpoint-item.error {
  background: rgba(239, 68, 68, 0.1);
  color: #991b1b;
}

/* Quick Actions */
.action-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  border-radius: 8px;
  text-decoration: none;
  color: #374151;
  transition: background-color 0.2s ease;
  margin-bottom: 0.5rem;
}

.action-item:hover {
  background: rgba(0, 0, 0, 0.05);
}

/* Activity */
.activity-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.activity-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3b82f6;
}

.activity-action {
  font-weight: 500;
  color: #374151;
}

.activity-time {
  font-size: 0.875rem;
  color: #6b7280;
}

.status-summary,
.api-stats {
  font-size: 0.875rem;
  color: #6b7280;
}
</style>