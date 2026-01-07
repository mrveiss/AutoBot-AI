<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  MonitoringDashboard.vue - Performance Monitoring Dashboard

  Issue #469: Refactored to use Prometheus metrics composable and Grafana embeds.
  Replaces legacy custom JSON API calls with unified Prometheus/Grafana integration.
-->
<template>
  <div class="performance-monitoring-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-title">
        <h1>
          <i class="fas fa-tachometer-alt"></i>
          Performance Monitoring
        </h1>
        <p class="subtitle">Real-time GPU/NPU utilization & Multi-modal AI performance</p>
      </div>

      <div class="monitoring-controls">
        <BaseButton
          @click="toggleMonitoring"
          :variant="monitoringActive ? 'danger' : 'success'"
          :disabled="isLoading"
        >
          <i :class="monitoringActive ? 'fas fa-stop' : 'fas fa-play'"></i>
          {{ monitoringActive ? 'Stop' : 'Start' }} Monitoring
        </BaseButton>

        <BaseButton variant="secondary" @click="refresh" :loading="isLoading">
          <i class="fas fa-sync"></i>
          Refresh
        </BaseButton>

        <div class="status-indicator">
          <span :class="['status-dot', connectionStatusClass]"></span>
          {{ connectionStatusText }}
        </div>

        <!-- Issue #469: Data source toggle -->
        <div class="data-source-toggle">
          <label class="toggle-label">
            <input type="checkbox" v-model="useGrafanaEmbed" />
            <span>Grafana View</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Alert Banner -->
    <BaseAlert
      v-if="hasCriticalAlerts"
      variant="critical"
      :message="`${criticalAlertCount} critical performance alert(s) detected`"
    >
      <template #actions>
        <BaseButton variant="outline" size="sm" @click="showAlertsModal = true" class="btn-outline-light">
          View Details
        </BaseButton>
      </template>
    </BaseAlert>

    <!-- Grafana Embed View (Issue #469) -->
    <div v-if="useGrafanaEmbed" class="grafana-view">
      <GrafanaDashboard
        dashboard="performance"
        :height="800"
        :showControls="true"
      />
    </div>

    <!-- Native Vue View with Prometheus Data -->
    <div v-else>
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
                <div :class="['health-score', systemHealthClass]">
                  {{ systemHealthText }}
                </div>
                <div class="performance-score">
                  Score: {{ healthScore }}/100
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
                  {{ gpuName }}
                </h5>
              </template>
              <div v-if="gpuDetails?.available">
                <div class="metric-row">
                  <span>Utilization</span>
                  <span class="metric-value">{{ gpuDetails.utilization_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Memory</span>
                  <span class="metric-value">{{ gpuDetails.memory_utilization_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Temperature</span>
                  <span class="metric-value">{{ gpuDetails.temperature_celsius }}°C</span>
                </div>
                <div class="metric-row">
                  <span>Power</span>
                  <span class="metric-value">{{ gpuDetails.power_watts }}W</span>
                </div>
                <div v-if="gpuDetails.thermal_throttling" class="throttle-warning">
                  <i class="fas fa-exclamation-triangle"></i> Thermal Throttling
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
              <div v-if="npuDetails?.available">
                <div class="metric-row">
                  <span>Utilization</span>
                  <span class="metric-value">{{ npuDetails.utilization_percent }}%</span>
                </div>
                <div class="metric-row">
                  <span>Acceleration</span>
                  <span class="metric-value">{{ npuDetails.acceleration_ratio }}x</span>
                </div>
                <div class="metric-row">
                  <span>Inferences</span>
                  <span class="metric-value">{{ npuDetails.inference_count }}</span>
                </div>
                <div v-if="npuDetails.wsl_limitation" class="wsl-warning">
                  <i class="fas fa-info-circle"></i> WSL Limitation Active
                </div>
              </div>
              <EmptyState
                v-else
                icon="fas fa-brain"
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
              <div v-if="dashboard?.system_metrics">
                <div class="metric-row">
                  <span>CPU Usage</span>
                  <span class="metric-value">{{ Math.round(cpuUsage) }}%</span>
                </div>
                <div class="metric-row">
                  <span>Memory</span>
                  <span class="metric-value">{{ Math.round(memoryUsage) }}%</span>
                </div>
                <div class="metric-row">
                  <span>Disk</span>
                  <span class="metric-value">{{ Math.round(diskUsage) }}%</span>
                </div>
                <div class="metric-row">
                  <span>Processes</span>
                  <span class="metric-value">{{ dashboard.system_metrics.process_count || 0 }}</span>
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

        <!-- Log Forwarding Status Row (Issue #553) -->
        <div class="row mt-3">
          <div class="col-md-4">
            <BasePanel variant="elevated" size="small">
              <template #header>
                <h5>
                  <i class="fas fa-share-alt"></i>
                  Log Forwarding
                </h5>
              </template>
              <div v-if="logForwardingStatus">
                <div class="metric-row">
                  <span>Status</span>
                  <span :class="['metric-value', logForwardingStatus.running ? 'text-success' : 'text-muted']">
                    {{ logForwardingStatus.running ? 'Running' : 'Stopped' }}
                  </span>
                </div>
                <div class="metric-row">
                  <span>Destinations</span>
                  <span class="metric-value">
                    {{ logForwardingStatus.healthy_count }}/{{ logForwardingStatus.total_count }} healthy
                  </span>
                </div>
                <div class="metric-row">
                  <span>Sent</span>
                  <span class="metric-value">{{ formatNumber(logForwardingStatus.total_sent) }}</span>
                </div>
                <div class="metric-row">
                  <span>Failed</span>
                  <span :class="['metric-value', logForwardingStatus.total_failed > 0 ? 'text-warning' : '']">
                    {{ formatNumber(logForwardingStatus.total_failed) }}
                  </span>
                </div>
                <div v-if="logForwardingStatus.total_failed > 0" class="throttle-warning">
                  <i class="fas fa-exclamation-triangle"></i> Check destination health
                </div>
              </div>
              <EmptyState
                v-else
                icon="fas fa-share-alt"
                message="Log forwarding not configured"
                compact
              />
            </BasePanel>
          </div>
        </div>
      </div>

      <!-- Performance Charts - Grafana Embeds -->
      <div class="performance-charts">
        <div class="row">
          <!-- GPU Utilization Chart - Grafana Panel -->
          <div class="col-md-6">
            <BasePanel variant="bordered" size="medium">
              <template #header>
                <h5>GPU Performance Timeline</h5>
              </template>
              <GrafanaDashboard
                dashboard="performance"
                :height="300"
                :showControls="false"
              />
            </BasePanel>
          </div>

          <!-- System Performance Chart - Grafana Panel -->
          <div class="col-md-6">
            <BasePanel variant="bordered" size="medium">
              <template #header>
                <h5>System Performance Timeline</h5>
              </template>
              <GrafanaDashboard
                dashboard="system"
                :height="300"
                :showControls="false"
              />
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
            v-for="service in servicesList"
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
            <BaseButton variant="outline" size="sm" @click="fetchRecommendations" class="btn-outline-primary">
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
              <StatusBadge :variant="(getPriorityVariant(rec.priority) as any)" size="small">{{ rec.priority }}</StatusBadge>
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
    </div>

    <!-- Performance Alerts Modal -->
    <BaseModal
      v-model="showAlertsModal"
      title="Performance Alerts"
      size="large"
      scrollable
    >
      <div v-if="alertsList.length > 0" class="alerts-list">
        <div
          v-for="alert in alertsList"
          :key="alert.timestamp"
          :class="['alert-item', alert.severity]"
        >
          <div class="alert-header">
            <StatusBadge :variant="(getSeverityVariant(alert.severity) as any)" size="small">{{ alert.severity }}</StatusBadge>
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

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * MonitoringDashboard Component
 *
 * Issue #469: Refactored to use Prometheus metrics composable.
 * - Uses usePrometheusMetrics for all data fetching
 * - Embeds Grafana dashboards for visualization
 * - Removes legacy custom JSON API calls
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { usePrometheusMetrics } from '@/composables/usePrometheusMetrics'
import { getStatusIcon as getStatusIconUtil } from '@/utils/iconMappings'
import { createLogger } from '@/utils/debugUtils'

// Components
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseAlert from '@/components/ui/BaseAlert.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import GrafanaDashboard from './GrafanaDashboard.vue'

// Create scoped logger
const logger = createLogger('MonitoringDashboard')

// Issue #469: Use Prometheus metrics composable for all data
const {
  dashboard,
  services,
  alerts,
  recommendations,
  gpuDetails,
  npuDetails,
  isLoading,
  error,
  isConnected,
  systemHealth,
  cpuUsage,
  memoryUsage,
  diskUsage,
  gpuUsage,
  npuUsage,
  healthScore,
  activeAlertCount,
  fetchAll,
  fetchRecommendations,
  connectWebSocket,
  disconnectWebSocket,
  refresh
} = usePrometheusMetrics({
  autoFetch: true,
  pollInterval: 30000,
  useWebSocket: false
})

// Local state
const monitoringActive = ref(false)
const showAlertsModal = ref(false)
const useGrafanaEmbed = ref(false)

// Issue #553: Log Forwarding status
interface LogForwardingStatus {
  running: boolean
  total_count: number
  healthy_count: number
  total_sent: number
  total_failed: number
}
const logForwardingStatus = ref<LogForwardingStatus | null>(null)

// Issue #553: Fetch log forwarding status
async function fetchLogForwardingStatus() {
  try {
    const response = await fetch('/api/log-forwarding/status')
    if (response.ok) {
      const data = await response.json()
      logForwardingStatus.value = {
        running: data.running || false,
        total_count: data.destinations?.length || 0,
        healthy_count: data.destinations?.filter((d: { healthy: boolean }) => d.healthy).length || 0,
        total_sent: data.destinations?.reduce((sum: number, d: { sent_count: number }) => sum + (d.sent_count || 0), 0) || 0,
        total_failed: data.destinations?.reduce((sum: number, d: { failed_count: number }) => sum + (d.failed_count || 0), 0) || 0
      }
    }
  } catch (err) {
    logger.debug('Log forwarding status not available:', err)
    logForwardingStatus.value = null
  }
}

// Issue #553: Format large numbers
function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

// Computed properties
const connectionStatusClass = computed(() => {
  if (isConnected.value) return 'connected'
  if (isLoading.value) return 'connecting'
  return 'disconnected'
})

const connectionStatusText = computed(() => {
  if (isConnected.value) return 'Connected'
  if (isLoading.value) return 'Connecting...'
  return 'Disconnected'
})

const systemHealthClass = computed(() => {
  return systemHealth.value || 'unknown'
})

const systemHealthText = computed(() => {
  const health = systemHealth.value
  switch (health) {
    case 'healthy': return 'Healthy'
    case 'degraded': return 'Warning'
    case 'critical': return 'Critical'
    default: return 'Unknown'
  }
})

const gpuName = computed(() => {
  return gpuDetails.value?.name || 'NVIDIA RTX 4070'
})

const servicesList = computed(() => {
  return services.value?.services || []
})

const alertsList = computed(() => {
  return alerts.value?.alerts || []
})

const hasCriticalAlerts = computed(() => {
  return (alerts.value?.critical_count || 0) > 0
})

const criticalAlertCount = computed(() => {
  return alerts.value?.critical_count || 0
})

// Methods
async function toggleMonitoring() {
  try {
    const endpoint = monitoringActive.value ? 'stop' : 'start'
    const response = await fetch(`/api/monitoring/${endpoint}`, {
      method: 'POST'
    })

    if (response.ok) {
      monitoringActive.value = !monitoringActive.value

      if (monitoringActive.value) {
        connectWebSocket()
      } else {
        disconnectWebSocket()
      }
    }
  } catch (err) {
    logger.error('Failed to toggle monitoring:', err)
  }
}

function getStatusIcon(status: string): string {
  const statusMap: Record<string, string> = {
    'healthy': 'healthy',
    'degraded': 'warning',
    'critical': 'error',
    'offline': 'offline'
  }
  return getStatusIconUtil(statusMap[status] || status)
}

function formatTimestamp(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}

function getPriorityVariant(priority: string): string {
  const variantMap: Record<string, string> = {
    'high': 'danger',
    'medium': 'warning',
    'low': 'info'
  }
  return variantMap[priority] || 'secondary'
}

function getSeverityVariant(severity: string): string {
  const variantMap: Record<string, string> = {
    'critical': 'danger',
    'warning': 'warning'
  }
  return variantMap[severity] || 'secondary'
}

// Lifecycle
onMounted(async () => {
  try {
    // Check initial monitoring status
    const statusResponse = await fetch('/api/monitoring/status')
    if (statusResponse.ok) {
      const status = await statusResponse.json()
      monitoringActive.value = status.active
    }
  } catch (err) {
    logger.warn('Could not check monitoring status:', err)
  }

  // Issue #553: Fetch log forwarding status
  await fetchLogForwardingStatus()
})

onUnmounted(() => {
  disconnectWebSocket()
})
</script>

<style scoped>
.performance-monitoring-dashboard {
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

.data-source-toggle {
  margin-left: 10px;
  padding: 6px 12px;
  background: #f0f0f0;
  border-radius: 4px;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 0.9em;
}

.toggle-label input {
  cursor: pointer;
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

.grafana-view {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
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
.health-score.degraded { color: #ff9800; }
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

.throttle-warning,
.wsl-warning {
  margin-top: 10px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 0.85em;
}

.throttle-warning {
  background: #ffebee;
  color: #c62828;
}

.wsl-warning {
  background: #fff3e0;
  color: #e65100;
}

.performance-charts {
  margin-bottom: 30px;
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
