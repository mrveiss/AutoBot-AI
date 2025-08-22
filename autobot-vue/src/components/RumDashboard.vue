<template>
  <div class="rum-dashboard" v-if="isVisible">
    <div class="rum-header">
      <h3>🔍 RUM Dashboard (Dev Mode)</h3>
      <div class="rum-controls">
        <button @click="refreshData" class="btn-sm">Refresh</button>
        <button @click="exportData" class="btn-sm">Export</button>
        <button @click="clearData" class="btn-sm btn-warning">Clear</button>
        <button @click="toggleVisibility" class="btn-sm">Hide</button>
      </div>
    </div>

    <div class="rum-tabs">
      <button
        v-for="tab in tabs"
        :key="tab"
        @click="activeTab = tab"
        :class="{ active: activeTab === tab }"
        class="rum-tab"
      >
        {{ tab }}
      </button>
    </div>

    <div class="rum-content">
      <!-- Overview Tab -->
      <div v-if="activeTab === 'Overview'" class="rum-section">
        <div class="rum-stats">
          <div class="stat-card">
            <h4>Session</h4>
            <p>{{ formatDuration(sessionDuration) }}</p>
          </div>
          <div class="stat-card">
            <h4>API Calls</h4>
            <p>{{ metrics.apiCalls.length }}</p>
          </div>
          <div class="stat-card error" v-if="slowApiCalls > 0">
            <h4>Slow API</h4>
            <p>{{ slowApiCalls }}</p>
          </div>
          <div class="stat-card critical" v-if="timeoutApiCalls > 0">
            <h4>Timeouts</h4>
            <p>{{ timeoutApiCalls }}</p>
          </div>
          <div class="stat-card error" v-if="metrics.errors.length > 0">
            <h4>Errors</h4>
            <p>{{ metrics.errors.length }}</p>
          </div>
        </div>
      </div>

      <!-- API Calls Tab -->
      <div v-if="activeTab === 'API Calls'" class="rum-section">
        <div class="rum-table">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Method</th>
                <th>Endpoint</th>
                <th>Duration</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="call in recentApiCalls"
                :key="call.timestamp"
                :class="{
                  slow: call.isSlow,
                  timeout: call.isTimeout,
                  error: call.status === 'error'
                }"
              >
                <td>{{ formatTime(call.timestamp) }}</td>
                <td>{{ call.method }}</td>
                <td>{{ call.url }}</td>
                <td>{{ call.duration.toFixed(0) }}ms</td>
                <td>{{ call.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Errors Tab -->
      <div v-if="activeTab === 'Errors'" class="rum-section">
        <div class="error-list">
          <div
            v-for="error in recentErrors"
            :key="error.timestamp"
            class="error-item"
          >
            <div class="error-header">
              <span class="error-type">{{ error.type }}</span>
              <span class="error-time">{{ formatTime(error.timestamp) }}</span>
            </div>
            <div class="error-message">{{ error.message || error.reason }}</div>
            <div class="error-details" v-if="error.stack">
              <pre>{{ error.stack }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- WebSocket Tab -->
      <div v-if="activeTab === 'WebSocket'" class="rum-section">
        <div class="websocket-status">
          <div class="ws-indicator" :class="wsStatus">
            {{ wsStatusText }}
          </div>
          <button @click="testWebSocketConnection" class="test-ws-btn">
            🔌 Test WebSocket Connection
          </button>
        </div>
        <div class="rum-table">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Event</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="event in recentWsEvents" :key="event.timestamp">
                <td>{{ formatTime(event.timestamp) }}</td>
                <td>{{ event.event }}</td>
                <td>{{ JSON.stringify(event.data) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Critical Issues Tab -->
      <div v-if="activeTab === 'Critical'" class="rum-section">
        <div class="critical-issues">
          <div
            v-for="issue in criticalIssues"
            :key="issue.timestamp"
            class="critical-item"
          >
            <div class="critical-header">
              <span class="critical-type">🚨 {{ issue.type }}</span>
              <span class="critical-time">{{ formatTime(issue.timestamp) }}</span>
            </div>
            <div class="critical-data">
              <pre>{{ JSON.stringify(issue.data, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Floating Toggle Button -->
  <button
    v-if="!isVisible && isDev"
    @click="toggleVisibility"
    class="rum-toggle"
    title="Show RUM Dashboard"
  >
    🔍
  </button>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useGlobalWebSocket } from '@/composables/useGlobalWebSocket.js'

export default {
  name: 'RumDashboard',
  setup() {
    // Global WebSocket Service
    const { isConnected: globalWsConnected, connectionState: globalWsState, testConnection } = useGlobalWebSocket();

    const isVisible = ref(false)
    const activeTab = ref('Overview')
    const metrics = ref({
      apiCalls: [],
      errors: [],
      webSocketEvents: [],
      sessionDuration: 0
    })
    const criticalIssues = ref([])

    const tabs = ['Overview', 'API Calls', 'Errors', 'WebSocket', 'Critical']
    const isDev = import.meta.env.DEV

    let refreshInterval = null

    // Computed properties
    const slowApiCalls = computed(() =>
      metrics.value.apiCalls.filter(call => call.isSlow).length
    )

    const timeoutApiCalls = computed(() =>
      metrics.value.apiCalls.filter(call => call.isTimeout).length
    )

    const recentApiCalls = computed(() =>
      metrics.value.apiCalls.slice(-20).reverse()
    )

    const recentErrors = computed(() =>
      metrics.value.errors.slice(-10).reverse()
    )

    const recentWsEvents = computed(() =>
      metrics.value.webSocketEvents.slice(-20).reverse()
    )

    const sessionDuration = computed(() => metrics.value.sessionDuration || 0)

    const wsStatus = computed(() => {
      // Use the real-time global WebSocket service status
      if (globalWsConnected.value) return 'connected'
      if (globalWsState.value === 'error') return 'error'
      return 'disconnected'
    })

    const wsStatusText = computed(() => {
      const status = wsStatus.value
      return status === 'connected' ? '🟢 Connected' :
             status === 'error' ? '🔴 Error' : '🟡 Disconnected'
    })

    // Methods
    const refreshData = () => {
      if (window.rum) {
        metrics.value = window.rum.getMetrics()
        criticalIssues.value = JSON.parse(localStorage.getItem('rum_critical_issues') || '[]')
      }
    }

    const exportData = () => {
      if (window.rum) {
        window.rum.exportData()
      }
    }

    const clearData = () => {
      if (window.rum) {
        window.rum.clear()
        refreshData()
      }
    }

    const testWebSocketConnection = () => {
      console.log('🔌 Testing global WebSocket connection, current state:', globalWsState.value)
      testConnection()
      refreshData()
    }

    const toggleVisibility = () => {
      isVisible.value = !isVisible.value
      if (isVisible.value) {
        refreshData()
      }
    }

    const formatTime = (timestamp) => {
      return new Date(timestamp).toLocaleTimeString()
    }

    const formatDuration = (ms) => {
      const seconds = Math.floor(ms / 1000)
      const minutes = Math.floor(seconds / 60)
      if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s`
      }
      return `${seconds}s`
    }

    // Lifecycle
    onMounted(() => {
      if (isDev) {
        refreshData()
        refreshInterval = setInterval(refreshData, 5000) // Refresh every 5 seconds

        // Show dashboard if there are critical issues
        const issues = JSON.parse(localStorage.getItem('rum_critical_issues') || '[]')
        if (issues.length > 0) {
          isVisible.value = true
        }
      }
    })

    onUnmounted(() => {
      if (refreshInterval) {
        clearInterval(refreshInterval)
      }
    })

    return {
      isVisible,
      activeTab,
      metrics,
      criticalIssues,
      tabs,
      isDev,
      slowApiCalls,
      timeoutApiCalls,
      recentApiCalls,
      recentErrors,
      recentWsEvents,
      sessionDuration,
      wsStatus,
      wsStatusText,
      refreshData,
      exportData,
      clearData,
      testWebSocketConnection,
      toggleVisibility,
      formatTime,
      formatDuration
    }
  }
}
</script>

<style scoped>
.rum-dashboard {
  position: fixed;
  top: 20px;
  right: 20px;
  width: 600px;
  max-height: 80vh;
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
  z-index: 10000;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 12px;
  overflow: hidden;
}

.rum-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f3f4f6;
  border-bottom: 1px solid #e5e7eb;
}

.rum-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: bold;
}

.rum-controls {
  display: flex;
  gap: 8px;
}

.btn-sm {
  padding: 4px 8px;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}

.btn-sm:hover {
  background: #f9fafb;
}

.btn-warning {
  color: #dc2626;
  border-color: #dc2626;
}

.rum-tabs {
  display: flex;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.rum-tab {
  padding: 8px 12px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 11px;
  border-bottom: 2px solid transparent;
}

.rum-tab.active {
  background: white;
  border-bottom-color: #3b82f6;
  font-weight: bold;
}

.rum-content {
  max-height: 60vh;
  overflow-y: auto;
  padding: 16px;
}

.rum-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  padding: 12px;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  text-align: center;
}

.stat-card.error {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}

.stat-card.critical {
  background: #fef2f2;
  border-color: #dc2626;
  color: #dc2626;
  font-weight: bold;
}

.stat-card h4 {
  margin: 0 0 4px 0;
  font-size: 10px;
  text-transform: uppercase;
  opacity: 0.7;
}

.stat-card p {
  margin: 0;
  font-size: 14px;
  font-weight: bold;
}

.rum-table {
  overflow-x: auto;
}

.rum-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.rum-table th,
.rum-table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.rum-table th {
  background: #f9fafb;
  font-weight: bold;
}

.rum-table tr.slow {
  background: #fef3c7;
}

.rum-table tr.timeout {
  background: #fecaca;
  color: #dc2626;
}

.rum-table tr.error {
  background: #fef2f2;
  color: #dc2626;
}

.error-list,
.critical-issues {
  space: 12px;
}

.error-item,
.critical-item {
  padding: 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  margin-bottom: 8px;
}

.error-header,
.critical-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: bold;
}

.error-type,
.critical-type {
  color: #dc2626;
}

.error-time,
.critical-time {
  color: #6b7280;
  font-size: 10px;
}

.error-details pre,
.critical-data pre {
  background: #f9fafb;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 10px;
  margin: 8px 0 0 0;
}

.websocket-status {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.test-ws-btn {
  background: #3b82f6;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.test-ws-btn:hover {
  background: #2563eb;
}

.test-ws-btn:active {
  background: #1d4ed8;
}

.ws-indicator {
  padding: 8px 12px;
  border-radius: 6px;
  font-weight: bold;
  text-align: center;
}

.ws-indicator.connected {
  background: #d1fae5;
  color: #065f46;
}

.ws-indicator.error {
  background: #fef2f2;
  color: #dc2626;
}

.ws-indicator.disconnected {
  background: #fef3c7;
  color: #92400e;
}

.rum-toggle {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 50px;
  height: 50px;
  border-radius: 50%;
  border: 2px solid #3b82f6;
  background: white;
  color: #3b82f6;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rum-toggle:hover {
  background: #3b82f6;
  color: white;
}
</style>
