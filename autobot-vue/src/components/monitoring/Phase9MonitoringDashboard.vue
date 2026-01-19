<template>
  <div class="phase9-monitoring-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-title">
        <h1>
          <i class="fas fa-tachometer-alt"></i>
          Phase 9 Performance Monitoring
        </h1>
        <p class="subtitle">Real-time GPU/NPU utilization & Multi-modal AI performance</p>
      </div>
      
      <div class="monitoring-controls">
        <button 
          @click="toggleMonitoring" 
          :class="['btn', monitoringActive ? 'btn-danger' : 'btn-success']"
          :disabled="loading"
        >
          <i :class="monitoringActive ? 'fas fa-stop' : 'fas fa-play'"></i>
          {{ monitoringActive ? 'Stop' : 'Start' }} Monitoring
        </button>
        
        <button @click="refreshDashboard" class="btn btn-secondary" :disabled="loading">
          <i class="fas fa-sync" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
        
        <div class="status-indicator">
          <span :class="['status-dot', connectionStatus]"></span>
          {{ connectionStatusText }}
        </div>
      </div>
    </div>

    <!-- Alert Banner -->
    <div v-if="criticalAlerts.length > 0" class="alert-banner critical">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ criticalAlerts.length }} critical performance alert(s) detected</span>
      <button @click="showAlertsModal = true" class="btn btn-sm btn-outline-light">
        View Details
      </button>
    </div>

    <!-- Performance Overview Cards -->
    <div class="performance-overview">
      <div class="row">
        <!-- Overall Health Card -->
        <div class="col-md-3">
          <div class="metric-card overall-health">
            <div class="card-header">
              <h5>
                <i class="fas fa-heartbeat"></i>
                Overall Health
              </h5>
            </div>
            <div class="card-body">
              <div :class="['health-score', overallHealth]">
                {{ overallHealthText }}
              </div>
              <div class="performance-score">
                Score: {{ performanceScore }}/100
              </div>
            </div>
          </div>
        </div>

        <!-- GPU Card -->
        <div class="col-md-3">
          <div class="metric-card gpu-metrics">
            <div class="card-header">
              <h5>
                <i class="fas fa-microchip"></i>
                NVIDIA RTX 4070
              </h5>
            </div>
            <div class="card-body">
              <div v-if="gpuMetrics">
                <div class="metric-row">
                  <span>Utilization</span>
                  <span class="metric-value">{{ gpuMetrics.utilization_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Memory</span>
                  <span class="metric-value">{{ gpuMetrics.memory_utilization_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Temperature</span>
                  <span class="metric-value">{{ gpuMetrics.temperature_celsius }}°C</span>
                </div>
                <div class="metric-row">
                  <span>Power</span>
                  <span class="metric-value">{{ gpuMetrics.power_draw_watts }}W</span>
                </div>
              </div>
              <div v-else class="no-data">GPU not available</div>
            </div>
          </div>
        </div>

        <!-- NPU Card -->
        <div class="col-md-3">
          <div class="metric-card npu-metrics">
            <div class="card-header">
              <h5>
                <i class="fas fa-brain"></i>
                Intel NPU
              </h5>
            </div>
            <div class="card-body">
              <div v-if="npuMetrics">
                <div class="metric-row">
                  <span>Utilization</span>
                  <span class="metric-value">{{ npuMetrics.utilization_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Acceleration</span>
                  <span class="metric-value">{{ npuMetrics.acceleration_ratio }}x</span>
                </div>
                <div class="metric-row">
                  <span>Inferences</span>
                  <span class="metric-value">{{ npuMetrics.inference_count }}</span>
                </div>
                <div class="metric-row">
                  <span>Avg Time</span>
                  <span class="metric-value">{{ npuMetrics.average_inference_time_ms }}ms</span>
                </div>
              </div>
              <div v-else class="no-data">NPU not available</div>
            </div>
          </div>
        </div>

        <!-- System Card -->
        <div class="col-md-3">
          <div class="metric-card system-metrics">
            <div class="card-header">
              <h5>
                <i class="fas fa-server"></i>
                System (22-core)
              </h5>
            </div>
            <div class="card-body">
              <div v-if="systemMetrics">
                <div class="metric-row">
                  <span>CPU Usage</span>
                  <span class="metric-value">{{ systemMetrics.cpu_usage_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Memory</span>
                  <span class="metric-value">{{ systemMetrics.memory_usage_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Load Avg</span>
                  <span class="metric-value">{{ systemMetrics.cpu_load_1m }}</span>
                </div>
                <div class="metric-row">
                  <span>Network</span>
                  <span class="metric-value">{{ systemMetrics.network_latency_ms }}ms</span>
                </div>
              </div>
              <div v-else class="no-data">System data unavailable</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Performance Charts -->
    <div class="performance-charts">
      <div class="row">
        <!-- GPU Utilization Chart -->
        <div class="col-md-6">
          <div class="chart-card">
            <div class="chart-header">
              <h5>GPU Utilization Timeline</h5>
              <div class="chart-controls">
                <select v-model="gpuTimeRange" @change="updateGpuChart" class="form-select form-select-sm">
                  <option value="5">Last 5 minutes</option>
                  <option value="15">Last 15 minutes</option>
                  <option value="60">Last hour</option>
                </select>
              </div>
            </div>
            <div class="chart-container">
              <canvas ref="gpuChart" id="gpuUtilizationChart"></canvas>
            </div>
          </div>
        </div>

        <!-- System Performance Chart -->
        <div class="col-md-6">
          <div class="chart-card">
            <div class="chart-header">
              <h5>System Performance Timeline</h5>
              <div class="chart-controls">
                <select v-model="systemTimeRange" @change="updateSystemChart" class="form-select form-select-sm">
                  <option value="5">Last 5 minutes</option>
                  <option value="15">Last 15 minutes</option>
                  <option value="60">Last hour</option>
                </select>
              </div>
            </div>
            <div class="chart-container">
              <canvas ref="systemChart" id="systemPerformanceChart"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Service Health -->
    <div class="service-health">
      <div class="section-header">
        <h4>
          <i class="fas fa-network-wired"></i>
          Distributed Services Health
        </h4>
      </div>
      
      <div class="services-grid">
        <div 
          v-for="service in services" 
          :key="service.name"
          :class="['service-card', service.status]"
        >
          <div class="service-header">
            <span class="service-name">{{ service.name }}</span>
            <span :class="['service-status', service.status]">
              <i :class="getStatusIcon(service.status)"></i>
              {{ service.status }}
            </span>
          </div>
          <div class="service-details">
            <div class="detail-row">
              <span>Response Time</span>
              <span>{{ service.response_time_ms }}ms</span>
            </div>
            <div class="detail-row">
              <span>Health Score</span>
              <span>{{ service.health_score }}/100</span>
            </div>
            <div class="detail-row">
              <span>Endpoint</span>
              <span>{{ service.host }}:{{ service.port }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Optimization Recommendations -->
    <div class="optimization-section">
      <div class="section-header">
        <h4>
          <i class="fas fa-lightbulb"></i>
          Performance Optimization Recommendations
        </h4>
        <button @click="refreshRecommendations" class="btn btn-sm btn-outline-primary">
          <i class="fas fa-sync"></i>
          Refresh
        </button>
      </div>
      
      <div v-if="recommendations.length > 0" class="recommendations-list">
        <div 
          v-for="rec in recommendations" 
          :key="rec.category + rec.recommendation"
          :class="['recommendation-card', rec.priority]"
        >
          <div class="rec-header">
            <span :class="['priority-badge', rec.priority]">{{ rec.priority }}</span>
            <span class="category">{{ rec.category.toUpperCase() }}</span>
          </div>
          <div class="rec-content">
            <p class="recommendation">{{ rec.recommendation }}</p>
            <p class="action">
              <strong>Action:</strong> {{ rec.action }}
            </p>
            <p class="expected-improvement">
              <strong>Expected:</strong> {{ rec.expected_improvement }}
            </p>
          </div>
        </div>
      </div>
      <div v-else class="no-recommendations">
        <i class="fas fa-check-circle"></i>
        No optimization recommendations at this time. System performing optimally!
      </div>
    </div>

    <!-- Performance Alerts Modal -->
    <div v-if="showAlertsModal" class="modal-overlay" @click="showAlertsModal = false">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h5>Performance Alerts</h5>
          <button @click="showAlertsModal = false" class="btn-close"></button>
        </div>
        <div class="modal-body">
          <div v-if="allAlerts.length > 0" class="alerts-list">
            <div 
              v-for="alert in allAlerts" 
              :key="alert.timestamp"
              :class="['alert-item', alert.severity]"
            >
              <div class="alert-header">
                <span :class="['severity-badge', alert.severity]">{{ alert.severity }}</span>
                <span class="category">{{ alert.category }}</span>
                <span class="timestamp">{{ formatTimestamp(alert.timestamp) }}</span>
              </div>
              <div class="alert-message">{{ alert.message }}</div>
              <div class="alert-recommendation">
                <strong>Recommendation:</strong> {{ alert.recommendation }}
              </div>
            </div>
          </div>
          <div v-else class="no-alerts">
            <i class="fas fa-check-circle"></i>
            No performance alerts
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { Chart, registerables } from 'chart.js'
import 'chartjs-adapter-date-fns'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('Phase9MonitoringDashboard')

Chart.register(...registerables)

export default {
  name: 'Phase9MonitoringDashboard',
  data() {
    return {
      loading: false,
      monitoringActive: false,
      connectionStatus: 'disconnected', // connected, disconnected, connecting
      showAlertsModal: false,
      
      // Dashboard data
      dashboardData: null,
      gpuMetrics: null,
      npuMetrics: null,
      systemMetrics: null,
      services: [],
      recommendations: [],
      allAlerts: [],
      
      // Chart configurations
      gpuTimeRange: '15',
      systemTimeRange: '15',
      gpuChart: null,
      systemChart: null,
      
      // WebSocket connection
      websocket: null,
      reconnectInterval: null,
      
      // Update intervals
      dashboardUpdateInterval: null,
      chartsUpdateInterval: null
    }
  },
  
  computed: {
    connectionStatusText() {
      switch (this.connectionStatus) {
        case 'connected': return 'Connected'
        case 'connecting': return 'Connecting...'
        default: return 'Disconnected'
      }
    },
    
    overallHealth() {
      return this.dashboardData?.analysis?.overall_health || 'unknown'
    },
    
    overallHealthText() {
      const health = this.overallHealth
      switch (health) {
        case 'healthy': return 'Healthy'
        case 'warning': return 'Warning'
        case 'critical': return 'Critical'
        default: return 'Unknown'
      }
    },
    
    performanceScore() {
      return this.dashboardData?.analysis?.performance_score || 0
    },
    
    criticalAlerts() {
      return this.allAlerts.filter(alert => alert.severity === 'critical')
    }
  },
  
  async mounted() {
    await this.initializeDashboard()
    this.setupWebSocket()
    this.startPeriodicUpdates()
  },
  
  beforeUnmount() {
    this.cleanup()
  },
  
  methods: {
    async initializeDashboard() {
      this.loading = true
      try {
        // Check monitoring status
        const statusResponse = await fetch('/api/monitoring/phase9/status')
        const status = await statusResponse.json()
        this.monitoringActive = status.active
        
        // Load dashboard data
        await this.refreshDashboard()
        
        // Initialize charts
        this.$nextTick(() => {
          this.initializeCharts()
        })
        
      } catch (error) {
        logger.error('Failed to initialize dashboard:', error)
        this.$toast.error('Failed to initialize performance monitoring dashboard')
      } finally {
        this.loading = false
      }
    },
    
    async refreshDashboard() {
      try {
        // Get dashboard data
        const dashboardResponse = await fetch('/api/monitoring/phase9/dashboard')
        this.dashboardData = await dashboardResponse.json()
        
        // Extract metrics
        this.gpuMetrics = this.dashboardData.gpu
        this.npuMetrics = this.dashboardData.npu
        this.systemMetrics = this.dashboardData.system
        this.services = Object.values(this.dashboardData.services || {})
        
        // Get alerts
        const alertsResponse = await fetch('/api/monitoring/phase9/alerts')
        this.allAlerts = await alertsResponse.json()
        
        // Get recommendations
        await this.refreshRecommendations()
        
      } catch (error) {
        logger.error('Failed to refresh dashboard:', error)
        this.$toast.error('Failed to refresh dashboard data')
      }
    },
    
    async refreshRecommendations() {
      try {
        const response = await fetch('/api/monitoring/phase9/optimization/recommendations')
        this.recommendations = await response.json()
      } catch (error) {
        logger.error('Failed to get recommendations:', error)
      }
    },
    
    async toggleMonitoring() {
      this.loading = true
      try {
        const endpoint = this.monitoringActive ? 'stop' : 'start'
        const response = await fetch(`/api/monitoring/phase9/${endpoint}`, {
          method: 'POST'
        })
        
        if (response.ok) {
          this.monitoringActive = !this.monitoringActive
          this.$toast.success(`Monitoring ${this.monitoringActive ? 'started' : 'stopped'}`)
          
          if (this.monitoringActive) {
            this.setupWebSocket()
          } else {
            this.closeWebSocket()
          }
        } else {
          throw new Error('Failed to toggle monitoring')
        }
      } catch (error) {
        logger.error('Failed to toggle monitoring:', error)
        this.$toast.error('Failed to toggle monitoring')
      } finally {
        this.loading = false
      }
    },
    
    setupWebSocket() {
      if (this.websocket) {
        this.websocket.close()
      }
      
      this.connectionStatus = 'connecting'
      
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/api/monitoring/phase9/realtime`
      
      this.websocket = new WebSocket(wsUrl)
      
      this.websocket.onopen = () => {
        this.connectionStatus = 'connected'
        this.$toast.success('Real-time monitoring connected')
        
        // Clear reconnect interval if it exists
        if (this.reconnectInterval) {
          clearInterval(this.reconnectInterval)
          this.reconnectInterval = null
        }
      }
      
      this.websocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleWebSocketMessage(message)
        } catch (error) {
          logger.error('Failed to parse WebSocket message:', error)
        }
      }
      
      this.websocket.onclose = () => {
        this.connectionStatus = 'disconnected'
        
        // Attempt to reconnect if monitoring is active
        if (this.monitoringActive && !this.reconnectInterval) {
          this.reconnectInterval = setInterval(() => {
            this.setupWebSocket()
          }, 5000)
        }
      }
      
      this.websocket.onerror = (error) => {
        logger.error('WebSocket error:', error)
        this.connectionStatus = 'disconnected'
      }
    },
    
    closeWebSocket() {
      if (this.websocket) {
        this.websocket.close()
        this.websocket = null
      }
      
      if (this.reconnectInterval) {
        clearInterval(this.reconnectInterval)
        this.reconnectInterval = null
      }
      
      this.connectionStatus = 'disconnected'
    },
    
    handleWebSocketMessage(message) {
      switch (message.type) {
        case 'performance_update':
          this.updateDashboardFromWebSocket(message.data)
          break
          
        case 'performance_alerts':
          this.handleNewAlerts(message.alerts)
          break
          
        case 'metrics_response':
          // Handle requested metrics
          break
      }
    },
    
    updateDashboardFromWebSocket(data) {
      this.dashboardData = data
      this.gpuMetrics = data.gpu
      this.npuMetrics = data.npu
      this.systemMetrics = data.system
      this.services = Object.values(data.services || {})
      
      // Update charts with new data
      this.updateChartData()
    },
    
    handleNewAlerts(alerts) {
      // Add new alerts to the beginning of the list
      this.allAlerts.unshift(...alerts)
      
      // Keep only the last 100 alerts
      this.allAlerts = this.allAlerts.slice(0, 100)
      
      // Show toast for critical alerts
      const criticalAlerts = alerts.filter(alert => alert.severity === 'critical')
      if (criticalAlerts.length > 0) {
        this.$toast.error(`${criticalAlerts.length} critical performance alert(s)`)
      }
    },
    
    initializeCharts() {
      this.initializeGpuChart()
      this.initializeSystemChart()
    },
    
    initializeGpuChart() {
      const ctx = this.$refs.gpuChart?.getContext('2d')
      if (!ctx) return
      
      this.gpuChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            {
              label: 'GPU Utilization (%)',
              data: [],
              borderColor: '#00d4aa',
              backgroundColor: 'rgba(0, 212, 170, 0.1)',
              tension: 0.1
            },
            {
              label: 'Memory Utilization (%)',
              data: [],
              borderColor: '#ffa726',
              backgroundColor: 'rgba(255, 167, 38, 0.1)',
              tension: 0.1
            },
            {
              label: 'Temperature (°C)',
              data: [],
              borderColor: '#f44336',
              backgroundColor: 'rgba(244, 67, 54, 0.1)',
              tension: 0.1,
              yAxisID: 'y1'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false,
          },
          scales: {
            x: {
              type: 'time',
              time: {
                displayFormats: {
                  minute: 'HH:mm'
                }
              }
            },
            y: {
              type: 'linear',
              display: true,
              position: 'left',
              max: 100,
              min: 0
            },
            y1: {
              type: 'linear',
              display: true,
              position: 'right',
              max: 100,
              min: 0,
              grid: {
                drawOnChartArea: false,
              },
            }
          },
          plugins: {
            legend: {
              position: 'top',
            },
            title: {
              display: false
            }
          }
        }
      })
    },
    
    initializeSystemChart() {
      const ctx = this.$refs.systemChart?.getContext('2d')
      if (!ctx) return
      
      this.systemChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            {
              label: 'CPU Usage (%)',
              data: [],
              borderColor: '#2196f3',
              backgroundColor: 'rgba(33, 150, 243, 0.1)',
              tension: 0.1
            },
            {
              label: 'Memory Usage (%)',
              data: [],
              borderColor: '#9c27b0',
              backgroundColor: 'rgba(156, 39, 176, 0.1)',
              tension: 0.1
            },
            {
              label: 'Load Average',
              data: [],
              borderColor: '#ff9800',
              backgroundColor: 'rgba(255, 152, 0, 0.1)',
              tension: 0.1,
              yAxisID: 'y1'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false,
          },
          scales: {
            x: {
              type: 'time',
              time: {
                displayFormats: {
                  minute: 'HH:mm'
                }
              }
            },
            y: {
              type: 'linear',
              display: true,
              position: 'left',
              max: 100,
              min: 0
            },
            y1: {
              type: 'linear',
              display: true,
              position: 'right',
              max: 25,
              min: 0,
              grid: {
                drawOnChartArea: false,
              },
            }
          },
          plugins: {
            legend: {
              position: 'top',
            },
            title: {
              display: false
            }
          }
        }
      })
    },
    
    async updateGpuChart() {
      await this.updateChartWithHistoricalData('gpu', this.gpuTimeRange, this.gpuChart)
    },
    
    async updateSystemChart() {
      await this.updateChartWithHistoricalData('system', this.systemTimeRange, this.systemChart)
    },
    
    async updateChartWithHistoricalData(category, timeRange, chart) {
      if (!chart) return
      
      try {
        const response = await fetch('/api/monitoring/phase9/metrics/query', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            categories: [category],
            time_range_minutes: parseInt(timeRange),
            include_trends: false,
            include_alerts: false
          })
        })
        
        const data = await response.json()
        const metrics = data.metrics[category] || []
        
        // Update chart data
        const labels = metrics.map(m => new Date(m.timestamp * 1000))
        
        if (category === 'gpu') {
          chart.data.labels = labels
          chart.data.datasets[0].data = metrics.map(m => m.utilization_percent)
          chart.data.datasets[1].data = metrics.map(m => m.memory_utilization_percent)
          chart.data.datasets[2].data = metrics.map(m => m.temperature_celsius)
        } else if (category === 'system') {
          chart.data.labels = labels
          chart.data.datasets[0].data = metrics.map(m => m.cpu_usage_percent)
          chart.data.datasets[1].data = metrics.map(m => m.memory_usage_percent)
          chart.data.datasets[2].data = metrics.map(m => m.cpu_load_1m)
        }
        
        chart.update('none')
        
      } catch (error) {
        logger.error(`Failed to update ${category} chart:`, error)
      }
    },
    
    updateChartData() {
      // Add new data points to charts if they exist
      if (this.gpuChart && this.gpuMetrics) {
        const timestamp = new Date()
        this.gpuChart.data.labels.push(timestamp)
        this.gpuChart.data.datasets[0].data.push(this.gpuMetrics.utilization_percent)
        this.gpuChart.data.datasets[1].data.push(this.gpuMetrics.memory_utilization_percent)
        this.gpuChart.data.datasets[2].data.push(this.gpuMetrics.temperature_celsius)
        
        // Keep only last 50 data points
        if (this.gpuChart.data.labels.length > 50) {
          this.gpuChart.data.labels.shift()
          this.gpuChart.data.datasets.forEach(dataset => dataset.data.shift())
        }
        
        this.gpuChart.update('none')
      }
      
      if (this.systemChart && this.systemMetrics) {
        const timestamp = new Date()
        this.systemChart.data.labels.push(timestamp)
        this.systemChart.data.datasets[0].data.push(this.systemMetrics.cpu_usage_percent)
        this.systemChart.data.datasets[1].data.push(this.systemMetrics.memory_usage_percent)
        this.systemChart.data.datasets[2].data.push(this.systemMetrics.cpu_load_1m)
        
        // Keep only last 50 data points
        if (this.systemChart.data.labels.length > 50) {
          this.systemChart.data.labels.shift()
          this.systemChart.data.datasets.forEach(dataset => dataset.data.shift())
        }
        
        this.systemChart.update('none')
      }
    },
    
    startPeriodicUpdates() {
      // Update dashboard every 30 seconds if not using WebSocket
      this.dashboardUpdateInterval = setInterval(() => {
        if (this.connectionStatus !== 'connected') {
          this.refreshDashboard()
        }
      }, 30000)
      
      // Update charts every 10 seconds
      this.chartsUpdateInterval = setInterval(() => {
        if (this.connectionStatus !== 'connected') {
          this.updateChartData()
        }
      }, 10000)
    },
    
    cleanup() {
      this.closeWebSocket()
      
      if (this.dashboardUpdateInterval) {
        clearInterval(this.dashboardUpdateInterval)
      }
      
      if (this.chartsUpdateInterval) {
        clearInterval(this.chartsUpdateInterval)
      }
      
      if (this.gpuChart) {
        this.gpuChart.destroy()
      }
      
      if (this.systemChart) {
        this.systemChart.destroy()
      }
    },
    
    getStatusIcon(status) {
      switch (status) {
        case 'healthy': return 'fas fa-check-circle'
        case 'degraded': return 'fas fa-exclamation-triangle'
        case 'critical': return 'fas fa-times-circle'
        case 'offline': return 'fas fa-power-off'
        default: return 'fas fa-question-circle'
      }
    },
    
    formatTimestamp(timestamp) {
      return new Date(timestamp * 1000).toLocaleString()
    }
  }
}
</script>

<style scoped>
.phase9-monitoring-dashboard {
  padding: 20px;
  background: #f8f9fa;
  min-height: 100vh;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.header-title h1 {
  margin: 0;
  color: #333;
  font-size: 1.8em;
}

.header-title .subtitle {
  margin: 5px 0 0 0;
  color: #666;
  font-size: 0.9em;
}

.monitoring-controls {
  display: flex;
  align-items: center;
  gap: 15px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9em;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.connected {
  background: #4caf50;
  box-shadow: 0 0 8px rgba(76, 175, 80, 0.5);
}

.status-dot.connecting {
  background: #ff9800;
  animation: pulse 1s infinite;
}

.status-dot.disconnected {
  background: #f44336;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.alert-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 20px;
  margin-bottom: 20px;
  border-radius: 8px;
  font-weight: 500;
}

.alert-banner.critical {
  background: #ffebee;
  border: 1px solid #f44336;
  color: #d32f2f;
}

.performance-overview {
  margin-bottom: 30px;
}

.metric-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
  height: 200px;
}

.metric-card .card-header {
  background: #f8f9fa;
  padding: 15px 20px;
  border-bottom: 1px solid #dee2e6;
}

.metric-card .card-header h5 {
  margin: 0;
  color: #333;
  font-size: 1em;
}

.metric-card .card-body {
  padding: 20px;
  height: calc(100% - 60px);
  overflow-y: auto;
}

.overall-health .health-score {
  font-size: 1.5em;
  font-weight: bold;
  margin-bottom: 10px;
}

.health-score.healthy { color: #4caf50; }
.health-score.warning { color: #ff9800; }
.health-score.critical { color: #f44336; }
.health-score.unknown { color: #666; }

.performance-score {
  color: #666;
  font-size: 0.9em;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.9em;
}

.metric-value {
  font-weight: 600;
  color: #333;
}

.no-data {
  color: #999;
  font-style: italic;
  text-align: center;
  margin-top: 20px;
}

.performance-charts {
  margin-bottom: 30px;
}

.chart-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.chart-header h5 {
  margin: 0;
  color: #333;
  font-size: 1em;
}

.chart-container {
  padding: 20px;
  height: 300px;
}

.service-health, .optimization-section {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.section-header h4 {
  margin: 0;
  color: #333;
  font-size: 1.2em;
}

.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  padding: 20px;
}

.service-card {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 15px;
  background: #fafafa;
}

.service-card.healthy { border-left: 4px solid #4caf50; }
.service-card.degraded { border-left: 4px solid #ff9800; }
.service-card.critical { border-left: 4px solid #f44336; }
.service-card.offline { border-left: 4px solid #999; }

.service-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.service-name {
  font-weight: 600;
  color: #333;
}

.service-status {
  font-size: 0.8em;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.service-status.healthy { background: #e8f5e8; color: #4caf50; }
.service-status.degraded { background: #fff3e0; color: #ff9800; }
.service-status.critical { background: #ffebee; color: #f44336; }
.service-status.offline { background: #f5f5f5; color: #999; }

.service-details {
  font-size: 0.85em;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.recommendations-list {
  padding: 20px;
}

.recommendation-card {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 15px;
  margin-bottom: 15px;
  background: #fafafa;
}

.recommendation-card.high { border-left: 4px solid #f44336; }
.recommendation-card.medium { border-left: 4px solid #ff9800; }
.recommendation-card.low { border-left: 4px solid #2196f3; }

.rec-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.priority-badge {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.priority-badge.high { background: #ffebee; color: #f44336; }
.priority-badge.medium { background: #fff3e0; color: #ff9800; }
.priority-badge.low { background: #e3f2fd; color: #2196f3; }

.category {
  font-size: 0.8em;
  color: #666;
  font-weight: 500;
}

.rec-content p {
  margin: 8px 0;
  font-size: 0.9em;
  line-height: 1.4;
}

.no-recommendations {
  padding: 40px 20px;
  text-align: center;
  color: #4caf50;
}

.no-recommendations i {
  font-size: 2em;
  margin-bottom: 10px;
  display: block;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  max-width: 800px;
  max-height: 80vh;
  width: 90%;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.modal-header h5 {
  margin: 0;
  color: #333;
}

.btn-close {
  background: none;
  border: none;
  font-size: 1.5em;
  cursor: pointer;
  color: #666;
}

.modal-body {
  padding: 20px;
  max-height: 60vh;
  overflow-y: auto;
}

.alerts-list {
  space: 15px;
}

.alert-item {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 15px;
  margin-bottom: 15px;
  background: #fafafa;
}

.alert-item.critical { border-left: 4px solid #f44336; }
.alert-item.warning { border-left: 4px solid #ff9800; }

.alert-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.severity-badge {
  font-size: 0.75em;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.severity-badge.critical { background: #ffebee; color: #f44336; }
.severity-badge.warning { background: #fff3e0; color: #ff9800; }

.timestamp {
  font-size: 0.8em;
  color: #666;
  margin-left: auto;
}

.alert-message {
  font-size: 0.9em;
  margin-bottom: 8px;
  color: #333;
}

.alert-recommendation {
  font-size: 0.85em;
  color: #666;
  line-height: 1.4;
}

.no-alerts {
  text-align: center;
  padding: 40px 20px;
  color: #4caf50;
}

.no-alerts i {
  font-size: 2em;
  margin-bottom: 10px;
  display: block;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
  font-weight: 500;
  text-decoration: none;
  display: inline-block;
  transition: background-color 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-success {
  background: #4caf50;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: #45a049;
}

.btn-danger {
  background: #f44336;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #da190b;
}

.btn-secondary {
  background: #6c757d;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #5a6268;
}

.btn-outline-primary {
  background: transparent;
  color: #007bff;
  border: 1px solid #007bff;
}

.btn-outline-primary:hover:not(:disabled) {
  background: #007bff;
  color: white;
}

.btn-outline-light {
  background: transparent;
  color: white;
  border: 1px solid white;
}

.btn-outline-light:hover:not(:disabled) {
  background: white;
  color: #333;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 0.8em;
}

.form-select {
  padding: 4px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  font-size: 0.9em;
}

.form-select-sm {
  padding: 2px 6px;
  font-size: 0.8em;
}

.row {
  display: flex;
  flex-wrap: wrap;
  margin: 0 -10px;
}

.col-md-3 {
  flex: 0 0 25%;
  max-width: 25%;
  padding: 0 10px;
  margin-bottom: 20px;
}

.col-md-6 {
  flex: 0 0 50%;
  max-width: 50%;
  padding: 0 10px;
  margin-bottom: 20px;
}

@media (max-width: 768px) {
  .col-md-3, .col-md-6 {
    flex: 0 0 100%;
    max-width: 100%;
  }
  
  .dashboard-header {
    flex-direction: column;
    gap: 15px;
    text-align: center;
  }
  
  .monitoring-controls {
    flex-wrap: wrap;
    justify-content: center;
  }
  
  .services-grid {
    grid-template-columns: 1fr;
  }
}
</style>