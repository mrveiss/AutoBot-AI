<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  GrafanaDashboardsView.vue - Comprehensive Grafana Dashboards Display
  Phase 4: Grafana Integration (Issue #347) - Navigation Integration
-->
<template>
  <div class="grafana-dashboards-view view-container">
    <div class="dashboard-header">
      <h2 class="text-2xl font-bold text-blueGray-700">Grafana Dashboards</h2>
      <p class="text-blueGray-600 mt-1">Prometheus + Grafana monitoring dashboards (Phase 4: Issue #347)</p>
    </div>

    <!-- Dashboard selector tabs -->
    <div class="dashboard-tabs">
      <button
        v-for="dashboard in dashboards"
        :key="dashboard.id"
        @click="activeDashboard = dashboard.id"
        class="tab-button"
        :class="{ 'active': activeDashboard === dashboard.id }"
      >
        <i :class="dashboard.icon" class="mr-2"></i>
        {{ dashboard.label }}
      </button>
    </div>

    <!-- Active dashboard display -->
    <div class="dashboard-container">
      <GrafanaDashboard
        :dashboard="activeDashboard"
        :time-range="timeRange"
        :refresh="refreshInterval"
        :theme="theme"
        :show-controls="true"
        @load="onDashboardLoad"
        @error="onDashboardError"
      />
    </div>

    <!-- Connection status -->
    <div v-if="connectionError" class="connection-warning">
      <i class="fas fa-exclamation-triangle mr-2"></i>
      Grafana connection issue: {{ connectionError }}
    </div>

    <!-- Quick info panel -->
    <div class="info-panel">
      <div class="info-item">
        <span class="label">Grafana URL:</span>
        <span class="value">http://172.16.168.23:3000</span>
      </div>
      <div class="info-item">
        <span class="label">Data Source:</span>
        <span class="value">Prometheus (http://172.16.168.23:9090)</span>
      </div>
      <div class="info-item">
        <span class="label">Total Dashboards:</span>
        <span class="value">6</span>
      </div>
      <div class="info-item">
        <span class="label">Total Panels:</span>
        <span class="value">50</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GrafanaDashboard from '@/components/monitoring/GrafanaDashboard.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('GrafanaDashboardsView')

// Dashboard definitions
const dashboards = [
  { id: 'overview', label: 'Overview', icon: 'fas fa-home' },
  { id: 'system', label: 'System', icon: 'fas fa-server' },
  { id: 'workflow', label: 'Workflow', icon: 'fas fa-project-diagram' },
  { id: 'errors', label: 'Errors', icon: 'fas fa-exclamation-circle' },
  { id: 'claude', label: 'Claude API', icon: 'fas fa-brain' },
  { id: 'github', label: 'GitHub', icon: 'fab fa-github' }
] as const

// State
const activeDashboard = ref<typeof dashboards[number]['id']>('overview')
const timeRange = ref('now-1h')
const refreshInterval = ref('5s')
const theme = ref<'light' | 'dark'>('dark')
const connectionError = ref<string | null>(null)

// Event handlers
function onDashboardLoad() {
  logger.debug(`Dashboard loaded: ${activeDashboard.value}`)
  connectionError.value = null
}

function onDashboardError(error: string) {
  logger.error(`Dashboard error: ${error}`)
  connectionError.value = error
}
</script>

<style scoped>
.grafana-dashboards-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 16px;
  background: var(--bg-primary, #f9fafb);
}

.dashboard-header {
  margin-bottom: 8px;
}

.dashboard-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow-x: auto;
}

.tab-button {
  padding: 10px 20px;
  background: transparent;
  border: 2px solid transparent;
  border-radius: 6px;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab-button:hover {
  background: #f1f5f9;
  color: #475569;
}

.tab-button.active {
  background: #eef2ff;
  border-color: #6366f1;
  color: #6366f1;
}

.dashboard-container {
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.connection-warning {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: #fef3c7;
  border: 1px solid #fbbf24;
  border-radius: 8px;
  color: #92400e;
  font-size: 14px;
}

.info-panel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item .label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-item .value {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
  font-family: 'Courier New', monospace;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .dashboard-tabs {
    flex-wrap: wrap;
  }

  .info-panel {
    grid-template-columns: 1fr;
  }
}
</style>
