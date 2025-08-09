<template>
  <div class="system-monitor">
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

      <!-- System Status -->
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
            >
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
                class="endpoint-item"
                v-for="endpoint in group.endpoints"
                :key="endpoint.path"
                :class="endpoint.status"
              >
                <div class="endpoint-info">
                  <span class="method">{{ endpoint.method }}</span>
                  <span class="path">{{ endpoint.path }}</span>
                </div>
                <div class="endpoint-metrics">
                  <span class="response-time">{{ endpoint.responseTime }}ms</span>
                  <div class="status-indicator" :class="endpoint.status"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- System Logs -->
      <div class="logs-card glass-card">
        <div class="card-header">
          <h3>System Logs</h3>
          <div class="log-controls">
            <select v-model="selectedLogLevel" class="log-filter">
              <option value="all">All Levels</option>
              <option value="error">Errors</option>
              <option value="warning">Warnings</option>
              <option value="info">Info</option>
            </select>
            <button class="clear-logs" @click="clearLogs">Clear</button>
          </div>
        </div>
        <div class="logs-content" ref="logsContainer">
          <div
            class="log-entry"
            v-for="log in filteredLogs"
            :key="log.id"
            :class="log.level"
          >
            <span class="log-time">{{ log.timestamp }}</span>
            <span class="log-level">{{ log.level.toUpperCase() }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>

      <!-- Resource Usage -->
      <div class="resources-card glass-card">
        <div class="card-header">
          <h3>Resource Usage</h3>
        </div>
        <div class="resources-content">
          <div class="resource-item">
            <div class="resource-icon">💾</div>
            <div class="resource-info">
              <div class="resource-name">Storage</div>
              <div class="resource-usage">{{ formatBytes(storage.used) }} / {{ formatBytes(storage.total) }}</div>
              <div class="resource-bar">
                <div class="bar-fill storage" :style="{ width: `${(storage.used / storage.total) * 100}%` }"></div>
              </div>
            </div>
          </div>
          <div class="resource-item">
            <div class="resource-icon">🧠</div>
            <div class="resource-info">
              <div class="resource-name">LLM Memory</div>
              <div class="resource-usage">{{ formatBytes(llmMemory.used) }} / {{ formatBytes(llmMemory.total) }}</div>
              <div class="resource-bar">
                <div class="bar-fill llm" :style="{ width: `${(llmMemory.used / llmMemory.total) * 100}%` }"></div>
              </div>
            </div>
          </div>
          <div class="resource-item">
            <div class="resource-icon">📊</div>
            <div class="resource-info">
              <div class="resource-name">Knowledge Base</div>
              <div class="resource-usage">{{ knowledge.entries }} entries</div>
              <div class="resource-bar">
                <div class="bar-fill kb" :style="{ width: `${Math.min((knowledge.entries / 10000) * 100, 100)}%` }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue';
import apiClient from '@/utils/ApiClient.js';

export default {
  name: 'SystemMonitor',
  setup() {
    const isRefreshing = ref(false);
    const selectedTimeframe = ref('1h');
    const selectedLogLevel = ref('all');
    const performanceChart = ref(null);
    const logsContainer = ref(null);

    const metrics = ref({
      cpu: 0,
      memory: 0,
      gpu: 0,
      npu: 0,
      network: 0,
      networkSpeed: 0
    });

    const services = ref([
      { name: 'Backend API', version: 'v1.2.3', status: 'online', statusText: 'Running' },
      { name: 'LLM Service', version: 'v2.1.0', status: 'online', statusText: 'Connected' },
      { name: 'Redis Cache', version: 'v7.0', status: 'online', statusText: 'Connected' },
      { name: 'Knowledge Base', version: 'v1.0.1', status: 'online', statusText: 'Ready' },
      { name: 'Voice Interface', version: 'v1.1.0', status: 'online', statusText: 'Ready' },
      { name: 'File Manager', version: 'v1.0.0', status: 'online', statusText: 'Active' }
    ]);

    const apiEndpoints = ref([
      {
        name: 'Chat API',
        endpoints: [
          { method: 'POST', path: '/api/chat', status: 'healthy', responseTime: 245 },
          { method: 'GET', path: '/api/chat/history', status: 'healthy', responseTime: 123 },
          { method: 'POST', path: '/api/chat/reset', status: 'healthy', responseTime: 89 }
        ]
      },
      {
        name: 'Voice API',
        endpoints: [
          { method: 'POST', path: '/api/voice/listen', status: 'healthy', responseTime: 567 },
          { method: 'POST', path: '/api/voice/speak', status: 'warning', responseTime: 1234 }
        ]
      },
      {
        name: 'Knowledge API',
        endpoints: [
          { method: 'POST', path: '/api/knowledge/search', status: 'healthy', responseTime: 145 },
          { method: 'POST', path: '/api/knowledge/add_text', status: 'healthy', responseTime: 234 }
        ]
      }
    ]);

    const logs = ref([]);
    const storage = ref({ used: 15.7 * 1024 * 1024 * 1024, total: 100 * 1024 * 1024 * 1024 });
    const llmMemory = ref({ used: 2.4 * 1024 * 1024 * 1024, total: 8 * 1024 * 1024 * 1024 });
    const knowledge = ref({ entries: 3847 });

    const timeframes = [
      { label: '1H', value: '1h' },
      { label: '6H', value: '6h' },
      { label: '24H', value: '24h' },
      { label: '7D', value: '7d' }
    ];

    let performanceHistory = [];
    let chartInterval = null;
    let metricsInterval = null;

    const onlineServices = computed(() => {
      return services.value.filter(s => s.status === 'online').length;
    });

    const totalServices = computed(() => services.value.length);

    const healthyEndpoints = computed(() => {
      return apiEndpoints.value.reduce((count, group) => {
        return count + group.endpoints.filter(e => e.status === 'healthy').length;
      }, 0);
    });

    const totalEndpoints = computed(() => {
      return apiEndpoints.value.reduce((count, group) => {
        return count + group.endpoints.length;
      }, 0);
    });

    const filteredLogs = computed(() => {
      if (selectedLogLevel.value === 'all') {
        return logs.value;
      }
      return logs.value.filter(log => log.level === selectedLogLevel.value);
    });

    const formatBytes = (bytes) => {
      if (bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const generateRandomMetrics = () => {
      metrics.value.cpu = Math.floor(Math.random() * 100);
      metrics.value.memory = Math.floor(Math.random() * 100);
      metrics.value.gpu = Math.floor(Math.random() * 100);
      metrics.value.npu = Math.floor(Math.random() * 100);
      metrics.value.network = Math.floor(Math.random() * 100);
      metrics.value.networkSpeed = Math.floor(Math.random() * 1024 * 1024 * 100); // 0-100 MB/s
    };

    const updatePerformanceHistory = () => {
      const now = Date.now();
      performanceHistory.push({
        timestamp: now,
        cpu: metrics.value.cpu,
        memory: metrics.value.memory,
        gpu: metrics.value.gpu,
        npu: metrics.value.npu
      });

      // Keep only last 100 data points
      if (performanceHistory.length > 100) {
        performanceHistory = performanceHistory.slice(-100);
      }
    };

    const drawChart = () => {
      if (!performanceChart.value) return;

      const ctx = performanceChart.value.getContext('2d');
      const canvas = performanceChart.value;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (performanceHistory.length < 2) return;

      const padding = 40;
      const width = canvas.width - padding * 2;
      const height = canvas.height - padding * 2;

      // Draw grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
      ctx.lineWidth = 1;

      for (let i = 0; i <= 4; i++) {
        const y = padding + (height * i / 4);
        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(width + padding, y);
        ctx.stroke();
      }

      // Draw lines
      const drawLine = (key, color) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();

        performanceHistory.forEach((point, index) => {
          const x = padding + (width * index / (performanceHistory.length - 1));
          const y = padding + height - (height * point[key] / 100);

          if (index === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });

        ctx.stroke();
      };

      drawLine('cpu', '#ef4444');
      drawLine('memory', '#10b981');
      drawLine('gpu', '#3b82f6');
      drawLine('npu', '#f59e0b');

      // Draw labels
      ctx.fillStyle = 'var(--blue-gray-800)';
      ctx.font = '12px Inter';
      ctx.fillText('CPU', padding + 10, padding + 20);
      ctx.fillText('Memory', padding + 50, padding + 20);
      ctx.fillText('GPU', padding + 100, padding + 20);
      ctx.fillText('NPU', padding + 140, padding + 20);

      // Draw legend colors
      ctx.fillStyle = '#ef4444';
      ctx.fillRect(padding - 5, padding + 10, 10, 2);
      ctx.fillStyle = '#10b981';
      ctx.fillRect(padding + 35, padding + 10, 10, 2);
      ctx.fillStyle = '#3b82f6';
      ctx.fillRect(padding + 85, padding + 10, 10, 2);
      ctx.fillStyle = '#f59e0b';
      ctx.fillRect(padding + 125, padding + 10, 10, 2);
    };

    const addLog = (level, message) => {
      const logEntry = {
        id: Date.now() + Math.random(),
        level,
        message,
        timestamp: new Date().toLocaleTimeString()
      };

      logs.value.unshift(logEntry);

      // Keep only last 100 logs
      if (logs.value.length > 100) {
        logs.value = logs.value.slice(0, 100);
      }

      // Auto-scroll to top
      nextTick(() => {
        if (logsContainer.value) {
          logsContainer.value.scrollTop = 0;
        }
      });
    };

    const clearLogs = () => {
      logs.value = [];
    };

    const simulateSystemActivity = () => {
      const activities = [
        { level: 'info', message: 'New chat session started' },
        { level: 'info', message: 'Knowledge base updated with new entries' },
        { level: 'warning', message: 'High CPU usage detected' },
        { level: 'info', message: 'Voice command processed successfully' },
        { level: 'error', message: 'Failed to connect to external API' },
        { level: 'info', message: 'File upload completed' },
        { level: 'warning', message: 'Memory usage approaching limit' },
        { level: 'info', message: 'Background task completed' }
      ];

      // Add random log every 5-15 seconds
      const randomDelay = Math.random() * 10000 + 5000;
      setTimeout(() => {
        const activity = activities[Math.floor(Math.random() * activities.length)];
        addLog(activity.level, activity.message);
        simulateSystemActivity();
      }, randomDelay);
    };

    const updateMetrics = async () => {
      isRefreshing.value = true;

      try {
        // In a real implementation, this would fetch from the backend
        generateRandomMetrics();
        updatePerformanceHistory();
        drawChart();

        // Update service status from backend
        try {
          const healthResponse = await apiClient.get('/api/system/health');
          if (healthResponse.status === 'healthy') {
            // Update backend API status
            const backendService = services.value.find(s => s.name === 'Backend API');
            if (backendService) {
              backendService.status = 'online';
              backendService.statusText = 'Running';
            }
          }
        } catch (error) {
          console.warn('Could not fetch system health:', error);
        }

      } finally {
        setTimeout(() => {
          isRefreshing.value = false;
        }, 500);
      }
    };

    onMounted(() => {
      // Initialize with some sample data
      for (let i = 0; i < 20; i++) {
        generateRandomMetrics();
        updatePerformanceHistory();
      }

      nextTick(() => {
        drawChart();
      });

      // Start intervals
      metricsInterval = setInterval(updateMetrics, 5000); // Update every 5 seconds
      chartInterval = setInterval(drawChart, 1000); // Redraw chart every second

      // Add initial logs
      addLog('info', 'System monitor initialized');
      addLog('info', 'All services checked');

      // Start simulating system activity
      simulateSystemActivity();
    });

    onUnmounted(() => {
      if (metricsInterval) {
        clearInterval(metricsInterval);
      }
      if (chartInterval) {
        clearInterval(chartInterval);
      }
    });

    return {
      isRefreshing,
      selectedTimeframe,
      selectedLogLevel,
      performanceChart,
      logsContainer,
      metrics,
      services,
      apiEndpoints,
      logs,
      storage,
      llmMemory,
      knowledge,
      timeframes,
      onlineServices,
      totalServices,
      healthyEndpoints,
      totalEndpoints,
      filteredLogs,
      formatBytes,
      clearLogs,
      updateMetrics
    };
  }
};
</script>

<style scoped>
.system-monitor {
  height: 100%;
  color: var(--blue-gray-700);
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
  height: 100%;
  overflow-y: auto;
  padding-bottom: 24px;
}

@media (min-width: 1200px) {
  .monitor-grid {
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 24px;
  }
}

.glass-card {
  background: white;
  border: 1px solid var(--blue-gray-200);
  border-radius: 0.5rem;
  padding: 0;
  overflow: hidden;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--blue-gray-200);
  background: var(--blue-gray-50);
}

.card-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--blue-gray-800);
}

.refresh-indicator {
  font-size: 16px;
  color: var(--blue-gray-500);
  transition: transform 0.3s ease;
}

.refresh-indicator.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.metric-content, .status-content, .chart-content, .api-content, .logs-content, .resources-content {
  padding: 14px;
}

@media (max-width: 1400px) {
  .metric-content, .status-content, .chart-content, .api-content, .logs-content, .resources-content {
    padding: 12px;
  }
}

.metric-item {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.metric-label {
  min-width: 120px;
  font-size: 14px;
  color: var(--blue-gray-700);
}

.metric-bar {
  flex: 1;
  height: 8px;
  background: var(--blue-gray-200);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
  position: relative;
}

.bar-fill::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
  animation: shimmer 2s ease-in-out infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.bar-fill.cpu { background: linear-gradient(90deg, #ef4444, #dc2626); }
.bar-fill.memory { background: linear-gradient(90deg, #10b981, #059669); }
.bar-fill.gpu { background: linear-gradient(90deg, #3b82f6, #2563eb); }
.bar-fill.npu { background: linear-gradient(90deg, #f59e0b, #d97706); }
.bar-fill.network { background: linear-gradient(90deg, #8b5cf6, #7c3aed); }
.bar-fill.storage { background: linear-gradient(90deg, #06b6d4, #0891b2); }
.bar-fill.llm { background: linear-gradient(90deg, #ec4899, #db2777); }
.bar-fill.kb { background: linear-gradient(90deg, #a855f7, #9333ea); }

.metric-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--blue-gray-800);
  min-width: 60px;
  text-align: right;
}

.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--blue-gray-100);
}

.service-item:last-child {
  border-bottom: none;
}

.service-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.service-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--blue-gray-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.service-version {
  font-size: 11px;
  color: var(--blue-gray-500);
}

.service-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.service-status.online .status-dot { background: #10b981; }
.service-status.warning .status-dot { background: #f59e0b; }
.service-status.offline .status-dot { background: #ef4444; }

.service-status.online { color: #10b981; }
.service-status.warning { color: #f59e0b; }
.service-status.offline { color: #ef4444; }

.status-summary, .api-stats {
  font-size: 12px;
  color: var(--blue-gray-600);
}

.chart-controls {
  display: flex;
  gap: 8px;
}

.time-btn {
  background: var(--blue-gray-100);
  border: 1px solid var(--blue-gray-300);
  color: var(--blue-gray-600);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.time-btn:hover, .time-btn.active {
  background: var(--indigo-500);
  color: white;
  border-color: var(--indigo-500);
}

.endpoint-group {
  margin-bottom: 12px;
}

.endpoint-group:last-child {
  margin-bottom: 0;
}

.group-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--blue-gray-800);
  margin-bottom: 6px;
}

.endpoint-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  background: var(--blue-gray-50);
  border-radius: 4px;
  margin-bottom: 4px;
  border-left: 3px solid transparent;
}

.endpoint-item:last-child {
  margin-bottom: 0;
}

.endpoint-item.healthy { border-left-color: #10b981; }
.endpoint-item.warning { border-left-color: #f59e0b; }
.endpoint-item.error { border-left-color: #ef4444; }

.endpoint-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.method {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--blue-gray-200);
  color: var(--blue-gray-700);
  flex-shrink: 0;
}

.path {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: var(--blue-gray-700);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.endpoint-metrics {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.response-time {
  font-size: 10px;
  color: var(--blue-gray-500);
}

.status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-indicator.healthy { background: #10b981; }
.status-indicator.warning { background: #f59e0b; }
.status-indicator.error { background: #ef4444; }

.log-controls {
  display: flex;
  gap: 12px;
  align-items: center;
}

.log-filter {
  background: white;
  border: 1px solid var(--blue-gray-300);
  color: var(--blue-gray-700);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.log-filter option {
  background: white;
  color: var(--blue-gray-700);
  padding: 4px 8px;
}

.log-filter:focus {
  outline: none;
  border-color: var(--indigo-500);
  background: white;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.clear-logs {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--red-500);
  color: var(--red-500);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.clear-logs:hover {
  background: var(--red-500);
  color: white;
}

.logs-content {
  max-height: 300px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.log-entry {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.log-entry:last-child {
  border-bottom: none;
}

.log-time {
  color: var(--blue-gray-500);
}

.log-level {
  font-weight: 600;
  min-width: 60px;
}

.log-entry.error .log-level { color: #ef4444; }
.log-entry.warning .log-level { color: #f59e0b; }
.log-entry.info .log-level { color: #10b981; }

.log-message {
  color: var(--blue-gray-700);
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.resource-icon {
  font-size: 20px;
  width: 32px;
  text-align: center;
  flex-shrink: 0;
}

.resource-info {
  flex: 1;
  min-width: 0; /* Allow text truncation */
}

.resource-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--blue-gray-800);
  margin-bottom: 3px;
}

.resource-usage {
  font-size: 11px;
  color: var(--blue-gray-600);
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.resource-bar {
  height: 6px;
  background: var(--blue-gray-200);
  border-radius: 3px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .monitor-grid {
    grid-template-columns: 1fr;
  }

  .chart-content canvas {
    width: 100% !important;
    height: auto !important;
  }
}
</style>
