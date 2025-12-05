<template>
  <div class="grafana-system-monitor">
    <!-- Header with Switch -->
    <div class="monitor-header">
      <h2>System Monitoring</h2>
      <div class="view-toggle">
        <button
          @click="viewMode = 'grafana'"
          :class="{ active: viewMode === 'grafana' }"
          class="toggle-btn"
        >
          <i class="fas fa-chart-line"></i> Metrics Dashboards
        </button>
        <button
          @click="viewMode = 'legacy'"
          :class="{ active: viewMode === 'legacy' }"
          class="toggle-btn"
        >
          <i class="fas fa-list"></i> Service Details
        </button>
      </div>
    </div>

    <!-- Grafana Dashboard View -->
    <div v-show="viewMode === 'grafana'" class="grafana-view">
      <!-- Dashboard Tabs -->
      <div class="dashboard-tabs">
        <button
          v-for="dashboard in dashboards"
          :key="dashboard.uid"
          @click="activeDashboard = dashboard.uid"
          :class="{ active: activeDashboard === dashboard.uid }"
          class="tab-btn"
        >
          <i :class="dashboard.icon"></i> {{ dashboard.name }}
        </button>
      </div>

      <!-- Embedded Grafana Dashboards - preload all, show active -->
      <div class="dashboard-container">
        <iframe
          v-for="dashboard in dashboards"
          :key="dashboard.uid"
          v-show="activeDashboard === dashboard.uid"
          :src="getDashboardUrl(dashboard.uid)"
          frameborder="0"
          class="grafana-iframe"
          loading="lazy"
        ></iframe>
      </div>
    </div>

    <!-- Legacy SystemMonitor View -->
    <div v-show="viewMode === 'legacy'" class="legacy-view">
      <SystemMonitor />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SystemMonitor from './SystemMonitor.vue'

const viewMode = ref<'grafana' | 'legacy'>('grafana')
const activeDashboard = ref('autobot-multi-machine')

const dashboards = [
  {
    uid: 'autobot-multi-machine',
    name: 'Multi-Machine',
    icon: 'fas fa-network-wired',
    path: '/d/autobot-multi-machine/autobot-multi-machine-infrastructure'
  },
  {
    uid: 'autobot-api-health',
    name: 'API Health',
    icon: 'fas fa-heartbeat',
    path: '/d/autobot-api-health/autobot-api-health-performance'
  },
  {
    uid: 'autobot-system',
    name: 'System Metrics',
    icon: 'fas fa-server',
    path: '/d/autobot-system/autobot-system-metrics'
  },
  {
    uid: 'autobot-overview',
    name: 'Overview',
    icon: 'fas fa-tachometer-alt',
    path: '/d/autobot-overview/autobot-overview'
  },
  {
    uid: 'autobot-workflow',
    name: 'Workflows',
    icon: 'fas fa-project-diagram',
    path: '/d/autobot-workflow/autobot-workflow-metrics'
  },
  {
    uid: 'autobot-claude-api',
    name: 'Claude API',
    icon: 'fas fa-robot',
    path: '/d/autobot-claude-api/autobot-claude-api-metrics'
  },
  {
    uid: 'autobot-errors',
    name: 'Errors',
    icon: 'fas fa-exclamation-triangle',
    path: '/d/autobot-errors/autobot-error-tracking'
  },
  {
    uid: 'autobot-github',
    name: 'GitHub',
    icon: 'fab fa-github',
    path: '/d/autobot-github/autobot-github-activity'
  }
]

const getDashboardUrl = (uid: string) => {
  const dashboard = dashboards.find(d => d.uid === uid)
  if (!dashboard) return ''

  // Grafana embed URL with kiosk mode (removes UI chrome)
  // Removed refresh=5s to prevent flickering - Grafana handles its own refresh
  return `http://172.16.168.23:3000${dashboard.path}?orgId=1&kiosk=tv&theme=light&from=now-1h&to=now`
}
</script>

<style scoped>
.grafana-system-monitor {
  padding: 20px;
  background: #f5f5f5;
  min-height: 100vh;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 16px 24px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.monitor-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #1a202c;
}

.view-toggle {
  display: flex;
  gap: 8px;
}

.toggle-btn {
  padding: 8px 16px;
  border: 2px solid #e2e8f0;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #4a5568;
  transition: all 0.2s;
}

.toggle-btn:hover {
  border-color: #4299e1;
  color: #2b6cb0;
}

.toggle-btn.active {
  background: #4299e1;
  border-color: #4299e1;
  color: white;
}

.toggle-btn i {
  margin-right: 6px;
}

.grafana-view {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
}

.dashboard-tabs {
  display: flex;
  gap: 4px;
  padding: 16px;
  background: #f7fafc;
  border-bottom: 1px solid #e2e8f0;
  overflow-x: auto;
}

.tab-btn {
  padding: 10px 20px;
  border: none;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #4a5568;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.tab-btn:hover {
  background: #edf2f7;
  color: #2d3748;
}

.tab-btn.active {
  background: #4299e1;
  color: white;
}

.tab-btn i {
  margin-right: 8px;
}

.dashboard-container {
  width: 100%;
  height: calc(100vh - 220px);
  min-height: 800px;
}

.grafana-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.legacy-view {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

/* Responsive */
@media (max-width: 768px) {
  .monitor-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .view-toggle {
    width: 100%;
  }

  .toggle-btn {
    flex: 1;
  }

  .dashboard-tabs {
    flex-wrap: wrap;
  }

  .dashboard-container {
    height: calc(100vh - 280px);
  }
}
</style>
