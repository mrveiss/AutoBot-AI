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
import { getConfig } from '@/config/ssot-config'

const config = getConfig()
const viewMode = ref<'grafana' | 'legacy'>('grafana')
const activeDashboard = ref('autobot-multi-machine')

// Grafana runs on Redis VM with its dedicated port
const grafanaBaseUrl = `${config.httpProtocol}://${config.vm.redis}:${config.port.grafana}`

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
  return `${grafanaBaseUrl}${dashboard.path}?orgId=1&kiosk=tv&theme=light&from=now-1h&to=now`
}
</script>

<style scoped>
.grafana-system-monitor {
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  min-height: 100vh;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.monitor-header h2 {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.view-toggle {
  display: flex;
  gap: var(--spacing-2);
}

.toggle-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: 2px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  transition: var(--transition-all);
}

.toggle-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary-hover);
}

.toggle-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary);
}

.toggle-btn i {
  margin-right: var(--spacing-1-5);
}

.grafana-view {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.dashboard-tabs {
  display: flex;
  gap: var(--spacing-1);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
  overflow-x: auto;
}

.tab-btn {
  padding: var(--spacing-2-5) var(--spacing-5);
  border: none;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  transition: var(--transition-all);
  white-space: nowrap;
  flex-shrink: 0;
}

.tab-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.tab-btn.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.tab-btn i {
  margin-right: var(--spacing-2);
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
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  box-shadow: var(--shadow-sm);
}

/* Responsive */
@media (max-width: 768px) {
  .monitor-header {
    flex-direction: column;
    gap: var(--spacing-4);
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
