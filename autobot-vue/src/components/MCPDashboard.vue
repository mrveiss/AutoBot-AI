<template>
  <div class="mcp-dashboard">
    <div class="dashboard-header">
      <h2>
        <i class="fas fa-heartbeat"></i>
        AutoBot System Health Dashboard
      </h2>
      <div class="refresh-controls">
        <BaseButton
          @click="refreshData"
          :disabled="loading"
          variant="primary"
          :loading="loading"
          icon="fas fa-sync-alt"
        >
          Refresh
        </BaseButton>
        <span class="last-update">Last update: {{ lastUpdate }}</span>
      </div>
    </div>

    <div class="health-grid">
      <!-- Frontend Health -->
      <BasePanel variant="elevated" size="medium" :class="getHealthClass(health.frontend)">
        <template #header>
          <i class="fas fa-desktop"></i>
          <h3>Frontend</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.frontend.status)"></i>
          </span>
        </template>
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
      </BasePanel>

      <!-- Backend Health -->
      <BasePanel variant="elevated" size="medium" :class="getHealthClass(health.backend)">
        <template #header>
          <i class="fas fa-server"></i>
          <h3>Backend API</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.backend.status)"></i>
          </span>
        </template>
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
      </BasePanel>

      <!-- API Performance -->
      <BasePanel variant="elevated" size="medium" :class="getHealthClass(health.api)">
        <template #header>
          <i class="fas fa-tachometer-alt"></i>
          <h3>API Performance</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.api.status)"></i>
          </span>
        </template>
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
      </BasePanel>

      <!-- WebSocket Health -->
      <BasePanel variant="elevated" size="medium" :class="getHealthClass(health.websocket)">
        <template #header>
          <i class="fas fa-plug"></i>
          <h3>WebSocket</h3>
          <span class="status-icon">
            <i :class="getStatusIcon(health.websocket.status)"></i>
          </span>
        </template>
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
      </BasePanel>
    </div>

    <!-- Activity Log -->
    <BasePanel variant="bordered" size="medium">
      <template #header>
        <h3><i class="fas fa-history"></i> Recent Activity</h3>
      </template>
      <div class="activity-log">
        <div v-for="(log, idx) in recentLogs" :key="idx" class="log-entry" :class="'log-' + log.level.toLowerCase()">
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </BasePanel>

    <!-- MCP Tools Status -->
    <BasePanel variant="bordered" size="medium">
      <template #header>
        <h3><i class="fas fa-tools"></i> MCP Tools Status</h3>
      </template>
      <div class="tools-grid">
        <div v-for="(tool, name) in mcpTools" :key="name" class="tool-status" :class="{ 'tool-active': tool.active }">
          <i :class="tool.icon"></i>
          <span>{{ tool.label }}</span>
          <span class="tool-count">{{ tool.count }} tools</span>
        </div>
      </div>
    </BasePanel>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '@/stores/app'
import { formatTime } from '@/utils/formatHelpers'
import { getStatusIcon as getStatusIconUtil } from '@/utils/iconMappings'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'

// Store
const appStore = useAppStore()
const { settings } = storeToRefs(appStore)

// Use composable for async operations
const { execute: refreshData, loading } = useAsyncOperation()

// State
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

// Icon mapping centralized in @/utils/iconMappings
// Custom color classes kept for component-specific styling
const getStatusIcon = (status) => {
  const icon = getStatusIconUtil(status)

  // Map status to custom color classes (defined in <style> section)
  const colorClassMap = {
    'healthy': 'text-success',
    'success': 'text-success',
    'warning': 'text-warning',
    'error': 'text-danger',
    'failed': 'text-danger',
    'unknown': 'text-muted'
  }

  const colorClass = colorClassMap[status] || 'text-muted'
  return `${icon} ${colorClass}`
}


const refreshDataFn = async () => {
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
}

// Lifecycle
onMounted(() => {
  refreshData(refreshDataFn)

  // Auto-refresh every 30 seconds
  refreshInterval.value = setInterval(() => refreshData(refreshDataFn), 30000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<style scoped>
/**
 * MCPDashboard.vue - Design Token Migration
 * Issue #704: CSS Design System - Centralized Theming
 *
 * All hardcoded colors have been replaced with CSS variables
 * from design-tokens.css for consistent theming support.
 */

.mcp-dashboard {
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  min-height: 100vh;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-8);
  padding: var(--spacing-5);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.dashboard-header h2 {
  margin: 0;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.refresh-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-5);
}

.last-update {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-8);
}

/* Health card conditional border styles - applied to BasePanel */
.health-good {
  border-top: 4px solid var(--color-success);
}

.health-warning {
  border-top: 4px solid var(--color-warning);
}

.health-error {
  border-top: 4px solid var(--color-error);
}

.health-unknown {
  border-top: 4px solid var(--text-muted);
}

/* Card header content styles - BasePanel handles structure */
.status-icon {
  font-size: var(--text-xl);
  margin-left: auto;
}

.card-body {
  padding: var(--spacing-5);
}

.metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.metric:last-child {
  margin-bottom: 0;
}

.label {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.value {
  font-weight: var(--font-bold);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.text-danger {
  color: var(--color-error) !important;
}

.text-success {
  color: var(--color-success);
}

.text-warning {
  color: var(--color-warning);
}

.text-muted {
  color: var(--text-muted);
}

.error-list {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-subtle);
}

.error-item {
  font-size: var(--text-sm);
  color: var(--color-error);
  margin-bottom: var(--spacing-1);
  padding: var(--spacing-1);
  background: var(--color-error-bg);
  border-radius: var(--radius-default);
}

/* Header styles - BasePanel handles section structure */
h3 {
  margin: 0;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.activity-log {
  max-height: 300px;
  overflow-y: auto;
}

.log-entry {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-3);
  margin-bottom: var(--spacing-1);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  background: var(--bg-tertiary);
}

.log-entry.log-error {
  background: var(--color-error-bg);
}

.log-entry.log-warning {
  background: var(--color-warning-bg);
}

.log-entry.log-success {
  background: var(--color-success-bg);
}

.log-entry.log-info {
  background: var(--color-info-bg);
}

.log-time {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.log-level {
  font-weight: var(--font-bold);
  width: 80px;
}

.log-message {
  flex: 1;
  color: var(--text-primary);
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.tool-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-4);
  border: 2px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  text-align: center;
  transition: var(--transition-all);
}

.tool-status.tool-active {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.tool-status i {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-2);
  color: var(--text-secondary);
}

.tool-status.tool-active i {
  color: var(--color-success);
}

.tool-status span {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.tool-count {
  font-size: var(--text-xs) !important;
  color: var(--text-secondary) !important;
  margin-top: var(--spacing-1);
}
</style>
