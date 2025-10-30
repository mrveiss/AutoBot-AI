<template>
  <div class="mcp-dashboard">
    <div class="dashboard-header">
      <h2>
        <i class="fas fa-heartbeat"></i>
        AutoBot System Health Dashboard
      </h2>
      <div class="refresh-controls">
        <button @click="refreshData" :disabled="loading" class="btn-refresh">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
        <span class="last-update">Last update: {{ lastUpdate }}</span>
      </div>
    </div>

    <div class="health-grid">
      <!-- Frontend Health -->
      <div class="health-card" :class="getHealthClass(health.frontend)">
        <div class="card-header">
          <i class="fas fa-desktop"></i>
          <h3>Frontend</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.frontend.status)"></i>
          </span>
        </div>
        <div class="card-body">
          <div class="metric">
            <span class="label">Console Errors:</span>
            <span class="value" :class="{ 'text-danger': health.frontend.errorCount > 0 }">
              {{ health.frontend.errorCount }}
            </span>
          </div>
          <div class="metric">
            <span class="label">Component Issues:</span>
            <span class="value">{{ health.frontend.componentIssues }}</span>
          </div>
          <div v-if="health.frontend.topErrors.length > 0" class="error-list">
            <div class="error-item" v-for="(error, idx) in health.frontend.topErrors" :key="idx">
              {{ error }}
            </div>
          </div>
        </div>
      </div>

      <!-- Backend Health -->
      <div class="health-card" :class="getHealthClass(health.backend)">
        <div class="card-header">
          <i class="fas fa-server"></i>
          <h3>Backend API</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.backend.status)"></i>
          </span>
        </div>
        <div class="card-body">
          <div class="metric">
            <span class="label">API Status:</span>
            <span class="value">{{ health.backend.apiStatus }}</span>
          </div>
          <div class="metric">
            <span class="label">Memory Usage:</span>
            <span class="value">{{ health.backend.memoryUsage }}%</span>
          </div>
          <div class="metric">
            <span class="label">Active Sessions:</span>
            <span class="value">{{ health.backend.activeSessions }}</span>
          </div>
        </div>
      </div>

      <!-- API Performance -->
      <div class="health-card" :class="getHealthClass(health.api)">
        <div class="card-header">
          <i class="fas fa-tachometer-alt"></i>
          <h3>API Performance</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.api.status)"></i>
          </span>
        </div>
        <div class="card-body">
          <div class="metric">
            <span class="label">Avg Response:</span>
            <span class="value">{{ health.api.avgResponseTime }}ms</span>
          </div>
          <div class="metric">
            <span class="label">Total Calls (1h):</span>
            <span class="value">{{ health.api.totalCalls }}</span>
          </div>
          <div class="metric">
            <span class="label">Error Rate:</span>
            <span class="value" :class="{ 'text-danger': health.api.errorRate > 5 }">
              {{ health.api.errorRate }}%
            </span>
          </div>
        </div>
      </div>

      <!-- WebSocket Health -->
      <div class="health-card" :class="getHealthClass(health.websocket)">
        <div class="card-header">
          <i class="fas fa-plug"></i>
          <h3>WebSocket</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.websocket.status)"></i>
          </span>
        </div>
        <div class="card-body">
          <div class="metric">
            <span class="label">Active Connections:</span>
            <span class="value">{{ health.websocket.activeConnections }}</span>
          </div>
          <div class="metric">
            <span class="label">Recent Errors:</span>
            <span class="value" :class="{ 'text-danger': health.websocket.errorCount > 0 }">
              {{ health.websocket.errorCount }}
            </span>
          </div>
          <div class="metric">
            <span class="label">Message Rate:</span>
            <span class="value">{{ health.websocket.messageRate }}/min</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Activity Log -->
    <div class="activity-section">
      <h3><i class="fas fa-history"></i> Recent Activity</h3>
      <div class="activity-log">
        <div v-for="(log, idx) in recentLogs" :key="idx" class="log-entry" :class="'log-' + log.level.toLowerCase()">
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>

    <!-- MCP Tools Status -->
    <div class="mcp-tools-section">
      <h3><i class="fas fa-tools"></i> MCP Tools Status</h3>
      <div class="tools-grid">
        <div v-for="(tool, name) in mcpTools" :key="name" class="tool-status" :class="{ 'tool-active': tool.active }">
          <i :class="tool.icon"></i>
          <span>{{ tool.label }}</span>
          <span class="tool-count">{{ tool.count }} tools</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '@/stores/app'
import { formatTime } from '@/utils/formatHelpers'

// Store
const appStore = useAppStore()
const { settings } = storeToRefs(appStore)

// State
const loading = ref(false)
const lastUpdate = ref('Never')
const refreshInterval = ref(null)

const health = ref({
  frontend: {
    status: 'unknown',
    errorCount: 0,
    componentIssues: 0,
    topErrors: []
  },
  backend: {
    status: 'unknown',
    apiStatus: 'Unknown',
    memoryUsage: 0,
    activeSessions: 0
  },
  api: {
    status: 'unknown',
    avgResponseTime: 0,
    totalCalls: 0,
    errorRate: 0
  },
  websocket: {
    status: 'unknown',
    activeConnections: 0,
    errorCount: 0,
    messageRate: 0
  }
})

const recentLogs = ref([])

const mcpTools = ref({
  filesystem: { label: 'Filesystem', icon: 'fas fa-folder-open', count: 14, active: true },
  autobot: { label: 'AutoBot Debug', icon: 'fas fa-bug', count: 11, active: true },
  puppeteer: { label: 'Puppeteer', icon: 'fas fa-robot', count: 7, active: true },
  sqlite: { label: 'SQLite', icon: 'fas fa-database', count: 8, active: true },
  github: { label: 'GitHub', icon: 'fab fa-github', count: 30, active: false },
  sequential: { label: 'Sequential', icon: 'fas fa-brain', count: 1, active: true }
})

// Methods
const getHealthClass = (section) => {
  return {
    'health-good': section.status === 'healthy',
    'health-warning': section.status === 'warning',
    'health-error': section.status === 'error',
    'health-unknown': section.status === 'unknown'
  }
}

const getStatusIcon = (status) => {
  switch (status) {
    case 'healthy': return 'fas fa-check-circle text-success'
    case 'warning': return 'fas fa-exclamation-triangle text-warning'
    case 'error': return 'fas fa-times-circle text-danger'
    default: return 'fas fa-question-circle text-muted'
  }
}


const refreshData = async () => {
  loading.value = true
  
  try {
    // In a real implementation, this would call the MCP servers
    // For now, we'll simulate the data
    
    // Simulate API call delay
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    // Update health data
    health.value = {
      frontend: {
        status: Math.random() > 0.8 ? 'warning' : 'healthy',
        errorCount: Math.floor(Math.random() * 5),
        componentIssues: 0,
        topErrors: Math.random() > 0.7 ? ['TypeError in ChatInterface.vue:342'] : []
      },
      backend: {
        status: 'healthy',
        apiStatus: 'Online',
        memoryUsage: Math.floor(Math.random() * 30 + 40),
        activeSessions: Math.floor(Math.random() * 10 + 5)
      },
      api: {
        status: Math.random() > 0.9 ? 'warning' : 'healthy',
        avgResponseTime: Math.floor(Math.random() * 200 + 100),
        totalCalls: Math.floor(Math.random() * 1000 + 500),
        errorRate: Math.random() * 5
      },
      websocket: {
        status: 'healthy',
        activeConnections: Math.floor(Math.random() * 5 + 1),
        errorCount: Math.floor(Math.random() * 2),
        messageRate: Math.floor(Math.random() * 50 + 10)
      }
    }
    
    // Add a log entry
    recentLogs.value.unshift({
      timestamp: new Date(),
      level: 'INFO',
      message: 'Health check completed successfully'
    })
    
    // Keep only last 10 logs
    if (recentLogs.value.length > 10) {
      recentLogs.value = recentLogs.value.slice(0, 10)
    }
    
    lastUpdate.value = new Date().toLocaleTimeString()
  } catch (error) {
    console.error('Failed to refresh health data:', error)
    recentLogs.value.unshift({
      timestamp: new Date(),
      level: 'ERROR',
      message: 'Failed to fetch health data'
    })
  } finally {
    loading.value = false
  }
}

// Lifecycle
onMounted(() => {
  refreshData()
  
  // Auto-refresh every 30 seconds
  refreshInterval.value = setInterval(refreshData, 30000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<style scoped>
.mcp-dashboard {
  padding: 20px;
  background: #f5f5f5;
  min-height: 100vh;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.dashboard-header h2 {
  margin: 0;
  color: #333;
  display: flex;
  align-items: center;
  gap: 10px;
}

.refresh-controls {
  display: flex;
  align-items: center;
  gap: 20px;
}

.btn-refresh {
  padding: 8px 16px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.3s;
}

.btn-refresh:hover:not(:disabled) {
  background: #0056b3;
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.last-update {
  color: #666;
  font-size: 14px;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.health-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  padding: 0;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}

.health-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.health-card.health-good {
  border-top: 4px solid #28a745;
}

.health-card.health-warning {
  border-top: 4px solid #ffc107;
}

.health-card.health-error {
  border-top: 4px solid #dc3545;
}

.health-card.health-unknown {
  border-top: 4px solid #6c757d;
}

.card-header {
  padding: 15px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
  flex: 1;
}

.status-icon {
  font-size: 20px;
}

.card-body {
  padding: 20px;
}

.metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.metric:last-child {
  margin-bottom: 0;
}

.label {
  color: #666;
  font-size: 14px;
}

.value {
  font-weight: bold;
  font-size: 16px;
  color: #333;
}

.text-danger {
  color: #dc3545 !important;
}

.text-success {
  color: #28a745;
}

.text-warning {
  color: #ffc107;
}

.error-list {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #e9ecef;
}

.error-item {
  font-size: 13px;
  color: #dc3545;
  margin-bottom: 5px;
  padding: 5px;
  background: #fef2f2;
  border-radius: 4px;
}

.activity-section,
.mcp-tools-section {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  padding: 20px;
  margin-bottom: 20px;
}

.activity-section h3,
.mcp-tools-section h3 {
  margin: 0 0 20px 0;
  color: #333;
  display: flex;
  align-items: center;
  gap: 10px;
}

.activity-log {
  max-height: 300px;
  overflow-y: auto;
}

.log-entry {
  display: flex;
  gap: 15px;
  padding: 8px 12px;
  margin-bottom: 5px;
  border-radius: 4px;
  font-size: 14px;
  background: #f8f9fa;
}

.log-entry.log-error {
  background: #fef2f2;
}

.log-entry.log-warning {
  background: #fffbeb;
}

.log-entry.log-success {
  background: #f0fdf4;
}

.log-time {
  color: #666;
  font-family: monospace;
  font-size: 13px;
}

.log-level {
  font-weight: bold;
  width: 80px;
}

.log-message {
  flex: 1;
  color: #333;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 15px;
}

.tool-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 15px;
  border: 2px solid #e9ecef;
  border-radius: 8px;
  text-align: center;
  transition: all 0.3s;
}

.tool-status.tool-active {
  border-color: #28a745;
  background: #f8fff9;
}

.tool-status i {
  font-size: 24px;
  margin-bottom: 8px;
  color: #666;
}

.tool-status.tool-active i {
  color: #28a745;
}

.tool-status span {
  display: block;
  font-size: 14px;
  color: #333;
}

.tool-count {
  font-size: 12px !important;
  color: #666 !important;
  margin-top: 4px;
}
</style>