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
        <BaseButton
          @click="toggleMonitoring"
          :variant="monitoringActive ? 'danger' : 'success'"
          :disabled="loading"
        >
          <i :class="monitoringActive ? 'fas fa-stop' : 'fas fa-play'"></i>
          {{ monitoringActive ? 'Stop' : 'Start' }} Monitoring
        </BaseButton>

        <BaseButton variant="secondary" @click="refreshDashboard" :loading="loading">
          <i class="fas fa-sync"></i>
          Refresh
        </BaseButton>
        
        <div class="status-indicator">
          <span :class="['status-dot', connectionStatus]"></span>
          {{ connectionStatusText }}
        </div>
      </div>
    </div>

    <!-- Alert Banner -->
    <BaseAlert
      v-if="criticalAlerts.length > 0"
      variant="critical"
      :message="`${criticalAlerts.length} critical performance alert(s) detected`"
    >
      <template #actions>
        <BaseButton variant="outline" size="sm" @click="showAlertsModal = true" class="btn-outline-light">
          View Details
        </BaseButton>
      </template>
    </BaseAlert>

    <!-- Performance Overview Cards -->
    <div class="performance-overview">
      <div class="row">
        <!-- Overall Health Card -->
        <div class="col-md-3">
          <BasePanel variant="elevated" size="small">
            <template #header>
              <h5>
                <i class="fas fa-heartbeat"></i>
                Overall Health
              </h5>
            </template>
            <div class="overall-health">
              <div :class="['health-score', overallHealth]">
                {{ overallHealthText }}
              </div>
              <div class="performance-score">
                Score: {{ performanceScore }}/100
              </div>
            </div>
          </BasePanel>
        </div>

        <!-- GPU Card -->
        <div class="col-md-3">
          <BasePanel variant="elevated" size="small">
            <template #header>
              <h5>
                <i class="fas fa-microchip"></i>
                NVIDIA RTX 4070
              </h5>
            </template>
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
                <span class="metric-value">{{ gpuMetrics.temperature_c }}°C</span>
              </div>
              <div class="metric-row">
                <span>Power</span>
                <span class="metric-value">{{ gpuMetrics.power_draw_w }}W</span>
              </div>
            </div>
            <EmptyState
              v-else
              icon="fas fa-microchip"
              message="GPU not available"
              compact
            />
          </BasePanel>
        </div>

        <!-- NPU Card -->
        <div class="col-md-3">
          <BasePanel variant="elevated" size="small">
            <template #header>
              <h5>
                <i class="fas fa-brain"></i>
                Intel NPU
              </h5>
            </template>
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
            <EmptyState
              v-else
              icon="fas fa-microchip"
              message="NPU not available"
              compact
            />
          </BasePanel>
        </div>

        <!-- System Card -->
        <div class="col-md-3">
          <BasePanel variant="elevated" size="small">
            <template #header>
              <h5>
                <i class="fas fa-server"></i>
                System (22-core)
              </h5>
            </template>
            <div v-if="systemMetrics">
              <div class="metric-row">
                <span>CPU Usage</span>
                <span class="metric-value">{{ Math.round(systemMetrics.cpu?.percent_overall || 0) }}%</span>
              </div>
              <div class="metric-row">
                <span>Memory</span>
                <span class="metric-value">{{ systemMetrics.memory?.percent || 0 }}%</span>
              </div>
              <div class="metric-row">
                <span>Load Avg</span>
                <span class="metric-value">{{ systemMetrics.cpu?.load_average?.[0]?.toFixed(2) || '0.00' }}</span>
              </div>
              <div class="metric-row">
                <span>Network</span>
                <span class="metric-value">{{ Math.round((systemMetrics.network?.bytes_sent || 0) / 1024 / 1024) }}MB sent</span>
              </div>
            </div>
            <EmptyState
              v-else
              icon="fas fa-server"
              message="System data unavailable"
              compact
            />
          </BasePanel>
        </div>
      </div>
    </div>

    <!-- Performance Charts -->
    <div class="performance-charts">
      <div class="row">
        <!-- GPU Utilization Chart -->
        <div class="col-md-6">
          <BasePanel variant="bordered" size="medium">
            <template #header>
              <div class="chart-header-content">
                <h5>GPU Utilization Timeline</h5>
                <div class="chart-controls">
                  <select v-model="gpuTimeRange" @change="updateGpuChart" class="form-select form-select-sm">
                    <option value="5">Last 5 minutes</option>
                    <option value="15">Last 15 minutes</option>
                    <option value="60">Last hour</option>
                  </select>
                </div>
              </div>
            </template>
            <div class="chart-container">
              <canvas ref="gpuChart" id="gpuUtilizationChart"></canvas>
            </div>
          </BasePanel>
        </div>

        <!-- System Performance Chart -->
        <div class="col-md-6">
          <BasePanel variant="bordered" size="medium">
            <template #header>
              <div class="chart-header-content">
                <h5>System Performance Timeline</h5>
                <div class="chart-controls">
                  <select v-model="systemTimeRange" @change="updateSystemChart" class="form-select form-select-sm">
                    <option value="5">Last 5 minutes</option>
                    <option value="15">Last 15 minutes</option>
                    <option value="60">Last hour</option>
                  </select>
                </div>
              </div>
            </template>
            <div class="chart-container">
              <canvas ref="systemChart" id="systemPerformanceChart"></canvas>
            </div>
          </BasePanel>
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
    <BasePanel variant="bordered" size="medium">
      <template #header>
        <div class="section-header-content">
          <h4>
            <i class="fas fa-lightbulb"></i>
            Performance Optimization Recommendations
          </h4>
          <BaseButton variant="outline" size="sm" @click="refreshRecommendations" class="btn-outline-primary">
            <i class="fas fa-sync"></i>
            Refresh
          </BaseButton>
        </div>
      </template>

      <div v-if="recommendations.length > 0" class="recommendations-list">
        <div
          v-for="rec in recommendations"
          :key="rec.category + rec.recommendation"
          :class="['recommendation-card', rec.priority]"
        >
          <div class="rec-header">
            <StatusBadge :variant="getPriorityVariant(rec.priority)" size="small">{{ rec.priority }}</StatusBadge>
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
    </BasePanel>

    <!-- Performance Alerts Modal -->
    <BaseModal
      v-model="showAlertsModal"
      title="Performance Alerts"
      size="large"
      scrollable
    >
      <div v-if="allAlerts.length > 0" class="alerts-list">
        <div
          v-for="alert in allAlerts"
          :key="alert.timestamp"
          :class="['alert-item', alert.severity]"
        >
          <div class="alert-header">
            <StatusBadge :variant="getSeverityVariant(alert.severity)" size="small">{{ alert.severity }}</StatusBadge>
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
    </BaseModal>
  </div>
</template>

<script>
import { Chart, registerables } from 'chart.js'
import 'chartjs-adapter-date-fns'
import { getStatusIcon as getStatusIconUtil } from '@/utils/iconMappings'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseAlert from '@/components/ui/BaseAlert.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BasePanel from '@/components/base/BasePanel.vue'

Chart.register(...registerables)

export default {
  name: 'MonitoringDashboard',
  components: {
    EmptyState,
    StatusBadge,
    BaseButton,
    BaseAlert,
    BaseModal,
    BasePanel
  },
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
        // Check monitoring status (may fail if monitoring service not available)
        try {
          const statusResponse = await fetch('/api/monitoring/status')
          if (statusResponse.ok) {
            const status = await statusResponse.json()
            this.monitoringActive = status.active
          }
        } catch (statusError) {
          console.warn('[MonitoringDashboard] Monitoring status unavailable, using fallback data:', statusError)
          this.monitoringActive = false
        }

        // Load dashboard data (will fetch from multiple sources)
        await this.refreshDashboard()

        // Initialize charts
        this.$nextTick(() => {
          this.initializeCharts()
        })

      } catch (error) {
        console.error('[MonitoringDashboard] Failed to initialize dashboard:', error)
        this.$toast.error('Failed to initialize performance monitoring dashboard')
      } finally {
        this.loading = false
      }
    },
    
    async refreshDashboard() {
      try {
        // Fetch data from multiple sources in parallel for better performance
        const [dashboardResponse, resourcesResponse, servicesResponse, alertsResponse] = await Promise.all([
          fetch('/api/monitoring/dashboard/overview').catch(err => {
            console.warn('[MonitoringDashboard] Dashboard overview fetch failed:', err.message)
            return null
          }),
          fetch('/api/service-monitor/resources').catch(err => {
            console.warn('[MonitoringDashboard] Resources fetch failed:', err.message)
            return null
          }),
          fetch('/api/service-monitor/services').catch(err => {
            console.warn('[MonitoringDashboard] Services fetch failed:', err.message)
            return null
          }),
          fetch('/api/monitoring/alerts/check').catch(err => {
            console.warn('[MonitoringDashboard] Alerts fetch failed:', err.message)
            return null
          })
        ])

        // Process monitoring dashboard data (may have GPU/NPU data when active)
        if (dashboardResponse && dashboardResponse.ok) {
          try {
            this.dashboardData = await dashboardResponse.json()
            // Extract GPU/NPU metrics from monitoring system
            this.gpuMetrics = this.dashboardData.gpu || this.dashboardData.gpu_status || null
            this.npuMetrics = this.dashboardData.npu || this.dashboardData.npu_status || null
          } catch (parseErr) {
            console.error('[MonitoringDashboard] Failed to parse dashboard response:', parseErr)
          }
        }

        // Process real-time system resources (ALWAYS available)
        if (resourcesResponse && resourcesResponse.ok) {
          try {
            const resources = await resourcesResponse.json()

            // Map service-monitor resources to expected systemMetrics format
            // Use actual load_average from backend (not estimated)
            this.systemMetrics = {
              cpu: {
                percent_overall: resources.cpu?.usage_percent || 0,
                load_average: resources.cpu?.load_average || [0, 0, 0]
              },
              memory: {
                percent: resources.memory?.percent || 0,
                total_gb: resources.memory?.total || 0,
                available_gb: resources.memory?.available || 0,
                used_gb: resources.memory?.used || 0
              },
              disk: {
                percent: resources.disk?.percent || 0,
                total_gb: resources.disk?.total || 0,
                free_gb: resources.disk?.free || 0,
                used_gb: resources.disk?.used || 0
              },
              network: {
                bytes_sent: resources.network?.bytes_sent || 0,
                bytes_recv: resources.network?.bytes_recv || 0,
                packets_sent: resources.network?.packets_sent || 0,
                packets_recv: resources.network?.packets_recv || 0
              }
            }
          } catch (parseErr) {
            console.error('[MonitoringDashboard] Failed to parse resources response:', parseErr)
          }
        }

        // Process real-time services status (ALWAYS available)
        if (servicesResponse && servicesResponse.ok) {
          try {
            const servicesData = await servicesResponse.json()
            // Normalize services to array format consistently
            this.services = this.normalizeServicesData(servicesData.services || servicesData || [])
          } catch (parseErr) {
            console.error('[MonitoringDashboard] Failed to parse services response:', parseErr)
          }
        }

        // Process alerts
        if (alertsResponse && alertsResponse.ok) {
          try {
            const alertsData = await alertsResponse.json()
            this.allAlerts = alertsData.alerts || []
          } catch (parseErr) {
            console.error('[MonitoringDashboard] Failed to parse alerts response:', parseErr)
          }
        }

        // Get recommendations
        await this.refreshRecommendations()

      } catch (error) {
        console.error('[MonitoringDashboard] Failed to refresh dashboard:', error)
        this.$toast.error('Failed to refresh dashboard data')
      }
    },

    /**
     * Normalize services data to consistent array format
     * Handles both array and object inputs from different API endpoints
     */
    normalizeServicesData(servicesInput) {
      if (!servicesInput) return []

      // Convert object to array if needed
      const servicesArray = Array.isArray(servicesInput)
        ? servicesInput
        : Object.values(servicesInput)

      return servicesArray.map(svc => ({
        name: svc.name || svc.service_name || 'Unknown',
        status: this.normalizeServiceStatus(svc.status),
        host: svc.host || 'localhost',
        port: svc.port || 0,
        response_time_ms: svc.response_time_ms || svc.latency_ms || 0,
        health_score: svc.health_score || (svc.status === 'online' || svc.status === 'healthy' ? 100 : 0)
      }))
    },

    /**
     * Normalize service status to expected values
     */
    normalizeServiceStatus(status) {
      const statusMap = {
        'online': 'healthy',
        'healthy': 'healthy',
        'offline': 'offline',
        'degraded': 'degraded',
        'warning': 'degraded',
        'critical': 'critical'
      }
      return statusMap[status] || 'offline'
    },
    
    async refreshRecommendations() {
      try {
        const response = await fetch('/api/monitoring/optimization/recommendations')
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        this.recommendations = await response.json()
      } catch (error) {
        console.error('[MonitoringDashboard] Failed to get recommendations:', error)
        this.$toast.warning('Failed to load optimization recommendations')
      }
    },
    
    async toggleMonitoring() {
      this.loading = true
      try {
        const endpoint = this.monitoringActive ? 'stop' : 'start'
        const response = await fetch(`/api/monitoring/${endpoint}`, {
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
        console.error('[MonitoringDashboard] Failed to toggle monitoring:', error)
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
      const wsUrl = `${protocol}//${window.location.host}/api/monitoring/realtime`
      
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
          console.error('[MonitoringDashboard] Failed to parse WebSocket message:', error)
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
        console.error('[MonitoringDashboard] WebSocket error:', error)
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
      this.gpuMetrics = data.gpu || data.gpu_status || null
      this.npuMetrics = data.npu || data.npu_status || null

      // Map system resources to expected format
      if (data.system_resources || data.system) {
        const sys = data.system_resources || data.system
        this.systemMetrics = {
          cpu: {
            percent_overall: sys.cpu_usage_percent || sys.cpu?.percent_overall || 0,
            // Use actual load_average from backend, fallback to cpu_load_1m if available
            load_average: sys.cpu?.load_average || (sys.cpu_load_1m ? [sys.cpu_load_1m, 0, 0] : [0, 0, 0])
          },
          memory: {
            percent: sys.memory_usage_percent || sys.memory?.percent || 0
          },
          network: {
            bytes_sent: sys.network?.bytes_sent || 0
          }
        }
      }

      // Map services to expected format using shared normalizer
      if (data.services_status || data.services) {
        const services = data.services_status || data.services
        this.services = this.normalizeServicesData(services)
      }

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
        const response = await fetch('/api/monitoring/metrics/query', {
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

        if (!response.ok) {
          throw new Error(`Metrics query failed: HTTP ${response.status}`)
        }
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
        console.error(`[MonitoringDashboard] Failed to update ${category} chart:`, error)
        this.$toast.warning(`Failed to update ${category} chart data`)
      }
    },
    
    updateChartData() {
      // Add new data points to charts if they exist
      if (this.gpuChart && this.gpuMetrics) {
        const timestamp = new Date()
        this.gpuChart.data.labels.push(timestamp)
        this.gpuChart.data.datasets[0].data.push(this.gpuMetrics.utilization_percent)
        this.gpuChart.data.datasets[1].data.push(this.gpuMetrics.memory_utilization_percent)
        this.gpuChart.data.datasets[2].data.push(this.gpuMetrics.temperature_c)
        
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
        this.systemChart.data.datasets[0].data.push(this.systemMetrics.cpu?.percent_overall || 0)
        this.systemChart.data.datasets[1].data.push(this.systemMetrics.memory?.percent || 0)
        this.systemChart.data.datasets[2].data.push(this.systemMetrics.cpu?.load_average?.[0] || 0)
        
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
    
    // Icon mapping centralized in @/utils/iconMappings
    getStatusIcon(status) {
      // Map component-specific statuses to standard statuses
      const statusMap = {
        'healthy': 'healthy',
        'degraded': 'warning',
        'critical': 'error',
        'offline': 'offline'
      }

      const mappedStatus = statusMap[status] || status
      return getStatusIconUtil(mappedStatus)
    },
    
    formatTimestamp(timestamp) {
      return new Date(timestamp * 1000).toLocaleString()
    },

    getPriorityVariant(priority) {
      const variantMap = {
        'high': 'danger',
        'medium': 'warning',
        'low': 'info'
      }
      return variantMap[priority] || 'secondary'
    },

    getSeverityVariant(severity) {
      const variantMap = {
        'critical': 'danger',
        'warning': 'warning'
      }
      return variantMap[severity] || 'secondary'
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

.performance-overview {
  margin-bottom: 30px;
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

.performance-charts {
  margin-bottom: 30px;
}

.chart-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.chart-header-content h5 {
  margin: 0;
  color: #333;
  font-size: 1em;
}

.chart-container {
  padding: 20px;
  height: 300px;
}

.service-health {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
  margin-bottom: 20px;
}

.service-health .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.service-health .section-header h4 {
  margin: 0;
  color: #333;
  font-size: 1.2em;
}

.section-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.section-header-content h4 {
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