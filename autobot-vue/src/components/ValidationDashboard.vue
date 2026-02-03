<template>
  <div class="validation-dashboard">
    <!-- Dashboard Header -->
    <div class="dashboard-header">
      <h1>🤖 Validation Dashboard</h1>
      <div class="header-controls">
        <button @click="refreshData" :disabled="loading" class="refresh-btn">
          <span v-if="loading">🔄</span>
          <span v-else>↻</span>
          Refresh
        </button>
        <div class="auto-refresh">
          <label>
            <input type="checkbox" v-model="autoRefresh" @change="toggleAutoRefresh">
            Auto-refresh ({{ refreshInterval }}s)
          </label>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !reportData" class="loading-state">
      <div class="spinner"></div>
      <p>Loading validation data...</p>
    </div>

    <!-- Error State -->
    <div v-if="error" class="error-state">
      <h3>❌ Dashboard Error</h3>
      <p>{{ error }}</p>
      <button @click="refreshData" class="retry-btn">Try Again</button>
    </div>

    <!-- Dashboard Content -->
    <div v-if="reportData && !error" class="dashboard-content">
      <!-- System Overview Cards -->
      <div class="stats-grid">
        <BasePanel variant="elevated" size="small">
          <div class="stat-card-content maturity">
            <div class="stat-icon">📈</div>
            <div class="stat-content">
              <div class="stat-value" :class="'health-' + reportData.system_overview.system_health">
                {{ reportData.system_overview.overall_maturity.toFixed(1) }}%
              </div>
              <div class="stat-label">System Maturity</div>
            </div>
          </div>
        </BasePanel>

        <BasePanel variant="elevated" size="small">
          <div class="stat-card-content phases">
            <div class="stat-icon">🎯</div>
            <div class="stat-content">
              <div class="stat-value">
                {{ reportData.system_overview.completed_phases }}/{{ reportData.system_overview.total_phases }}
              </div>
              <div class="stat-label">Phases Completed</div>
            </div>
          </div>
        </BasePanel>

        <BasePanel variant="elevated" size="small">
          <div class="stat-card-content capabilities">
            <div class="stat-icon">⚡</div>
            <div class="stat-content">
              <div class="stat-value">{{ reportData.system_overview.active_capabilities }}</div>
              <div class="stat-label">Active Capabilities</div>
            </div>
          </div>
        </BasePanel>

        <BasePanel variant="elevated" size="small">
          <div class="stat-card-content health">
            <div class="stat-icon">💚</div>
            <div class="stat-content">
              <div class="stat-value" :class="'health-' + reportData.system_overview.system_health">
                {{ reportData.system_overview.system_health.replace('_', ' ') }}
              </div>
              <div class="stat-label">System Health</div>
            </div>
          </div>
        </BasePanel>
      </div>

      <!-- Main Content Grid -->
      <div class="main-grid">
        <!-- Phase Progress Section -->
        <BasePanel variant="bordered" size="medium">
          <template #header>
            <h2>📊 Phase Progress</h2>
          </template>
          <div class="phases-list">
            <div v-for="phase in reportData.phase_details" :key="phase.name" class="phase-item">
              <div class="phase-info">
                <div class="phase-name">{{ phase.display_name }}</div>
                <div class="phase-requirements">
                  {{ phase.requirements_met }}/{{ phase.total_requirements }} requirements
                </div>
              </div>
              <div class="phase-progress">
                <div class="progress-text">{{ phase.completion_percentage.toFixed(1) }}%</div>
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{ width: phase.completion_percentage + '%', backgroundColor: phase.status_color }"
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </BasePanel>

        <!-- Alerts and Recommendations Sidebar -->
        <div class="sidebar">
          <!-- System Alerts -->
          <BasePanel variant="bordered" size="medium">
            <template #header>
              <h3>🚨 System Alerts</h3>
            </template>
            <EmptyState
              v-if="reportData.alerts.length === 0"
              icon="fas fa-check-circle"
              message="No active alerts"
              variant="success"
            />
            <div v-else class="alerts-list">
              <BaseAlert
                v-for="alert in reportData.alerts"
                :key="alert.timestamp"
                :variant="alert.level"
                :title="alert.title"
                :message="alert.message"
                bordered
              >
                <template #actions>
                  <span class="alert-time">{{ formatTime(alert.timestamp) }}</span>
                </template>
              </BaseAlert>
            </div>
          </BasePanel>

          <!-- Recommendations -->
          <BasePanel variant="bordered" size="medium">
            <template #header>
              <h3>💡 Recommendations</h3>
            </template>
            <EmptyState
              v-if="(reportData.recommendations || []).length === 0"
              icon="fas fa-check-circle"
              message="No recommendations at this time"
              variant="success"
            />
            <div v-else>
              <div v-for="rec in (reportData.recommendations || []).slice(0, 5)"
                   :key="rec.title" class="recommendation">
                <div class="rec-header">
                  <div class="rec-title">{{ rec.title }}</div>
                  <span :class="['rec-urgency', 'urgency-' + rec.urgency]">
                    {{ rec.urgency.toUpperCase() }}
                  </span>
                </div>
                <div class="rec-description">{{ rec.description }}</div>
                <div class="rec-action">💡 {{ rec.action }}</div>
              </div>
            </div>
          </BasePanel>
        </div>
      </div>

      <!-- Progression Status -->
      <BasePanel variant="bordered" size="medium">
        <template #header>
          <h2>🚀 Progression Status</h2>
        </template>
        <div class="progression-grid">
          <div class="progression-item">
            <div class="progression-label">Can Progress</div>
            <div :class="['progression-value', reportData.progression_status.can_progress ? 'positive' : 'negative']">
              {{ reportData.progression_status.can_progress ? '✅ Yes' : '❌ No' }}
            </div>
          </div>
          <div class="progression-item">
            <div class="progression-label">Current Phase</div>
            <div class="progression-value">{{ reportData.progression_status.current_phase }}</div>
          </div>
          <div class="progression-item">
            <div class="progression-label">Available Next</div>
            <div class="progression-value">{{ reportData.progression_status.next_available.length }}</div>
          </div>
          <div class="progression-item">
            <div class="progression-label">Blocked Phases</div>
            <div class="progression-value">{{ reportData.progression_status.blocked_phases.length }}</div>
          </div>
        </div>
      </BasePanel>

      <!-- Phase Progression Indicator -->
      <BasePanel variant="bordered" size="medium">
        <PhaseProgressionIndicator />
      </BasePanel>
    </div>

    <!-- Footer -->
    <div class="dashboard-footer">
      <div class="footer-info">
        Last updated: {{ lastUpdated }} |
        Generated: {{ reportData ? formatTime(reportData.generated_at) : 'N/A' }}
      </div>
    </div>
  </div>
</template>

<script>
import apiClient from '../utils/ApiClient.js';
import errorHandler from '../utils/ErrorHandler.js';
import PhaseProgressionIndicator from './PhaseProgressionIndicator.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import BaseAlert from '@/components/ui/BaseAlert.vue';
import BasePanel from '@/components/base/BasePanel.vue';

export default {
  name: 'ValidationDashboard',
  components: {
    PhaseProgressionIndicator,
    EmptyState,
    BaseAlert,
    BasePanel
  },
  data() {
    return {
      reportData: null,
      loading: false,
      error: null,
      autoRefresh: false,
      refreshInterval: 30,
      refreshTimer: null,
      lastUpdated: null
    }
  },

  mounted() {
    // Validation dashboard is now on-demand only - no automatic loading
    // this.loadDashboardData();  // Commented out - load only on user request
  },

  beforeUnmount() {
    this.clearAutoRefresh();
  },

  methods: {
    async loadDashboardData() {
      this.loading = true;
      this.error = null;

      try {
        // Use singleton ApiClient instance
        const data = await apiClient.get('/api/validation-dashboard/report');

        if (data.status === 'success') {
          this.reportData = data.report;
          this.lastUpdated = new Date().toLocaleTimeString();
        } else {
          throw new Error(data.message || 'Unknown error');
        }

      } catch (err) {
        const errorResult = errorHandler.handleApiError(err, 'ValidationDashboard.loadDashboardData');
        this.error = errorResult.error;
      } finally {
        this.loading = false;
      }
    },

    async refreshData() {
      await this.loadDashboardData();
    },

    toggleAutoRefresh() {
      if (this.autoRefresh) {
        this.startAutoRefresh();
      } else {
        this.clearAutoRefresh();
      }
    },

    startAutoRefresh() {
      this.clearAutoRefresh();
      this.refreshTimer = setInterval(() => {
        this.loadDashboardData();
      }, this.refreshInterval * 1000);
    },

    clearAutoRefresh() {
      if (this.refreshTimer) {
        clearInterval(this.refreshTimer);
        this.refreshTimer = null;
      }
    },

    formatTime(timestamp) {
      if (!timestamp) return 'N/A';
      return new Date(timestamp).toLocaleString();
    }
  }
}
</script>

<style scoped>
.validation-dashboard {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--spacing-5);
  font-family: var(--font-sans);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-8);
  padding: var(--spacing-5);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--chart-purple) 100%);
  color: var(--text-on-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

.dashboard-header h1 {
  margin: 0;
  font-size: var(--text-3xl);
}

.header-controls {
  display: flex;
  gap: var(--spacing-5);
  align-items: center;
}

.refresh-btn {
  background: var(--bg-hover);
  color: var(--text-on-primary);
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-colors);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-active);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auto-refresh label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
}

.loading-state,
.error-state {
  text-align: center;
  padding: var(--spacing-16) var(--spacing-5);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--bg-tertiary);
  border-top: 4px solid var(--color-primary);
  border-radius: var(--radius-full);
  animation: spin 1s linear infinite;
  margin: 0 auto var(--spacing-5);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-state {
  color: var(--color-error);
}

.retry-btn {
  background: var(--color-error);
  color: var(--text-on-error);
  border: none;
  padding: var(--spacing-2-5) var(--spacing-5);
  border-radius: var(--radius-md);
  cursor: pointer;
  margin-top: var(--spacing-2-5);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-8);
}

.stat-card-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-5);
}

.stat-icon {
  font-size: var(--text-4xl);
}

.stat-value {
  font-size: var(--text-4xl);
  font-weight: var(--font-bold);
  margin-bottom: var(--spacing-1);
}

.stat-label {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.health-excellent { color: var(--color-success); }
.health-good { color: var(--color-success-light); }
.health-fair { color: var(--color-warning); }
.health-needs_attention { color: var(--color-error); }

.main-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-8);
  margin-bottom: var(--spacing-8);
}

.phases-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.phase-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--border-default);
}

.phase-name {
  font-weight: var(--font-bold);
  font-size: var(--text-lg);
}

.phase-requirements {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.phase-progress {
  text-align: right;
  min-width: 120px;
}

.progress-text {
  font-weight: var(--font-bold);
  margin-bottom: var(--spacing-1);
}

.progress-bar {
  width: 100px;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-out);
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.alert-time {
  font-size: var(--text-xs);
  opacity: 0.7;
  margin-top: var(--spacing-1);
}

.recommendation {
  padding: var(--spacing-4);
  margin: var(--spacing-2-5) 0;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-info);
}

.rec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-2-5);
}

.rec-title {
  font-weight: var(--font-bold);
  flex: 1;
}

.rec-urgency {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  margin-left: var(--spacing-2-5);
}

.urgency-high { background: var(--color-error-bg); color: var(--color-error); }
.urgency-medium { background: var(--color-warning-bg); color: var(--color-warning); }
.urgency-low { background: var(--color-success-bg); color: var(--color-success); }

.rec-description {
  margin-bottom: var(--spacing-2-5);
  font-size: var(--text-sm);
}

.rec-action {
  font-style: italic;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.progression-section {
  margin-bottom: var(--spacing-5);
}

.progression-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-5);
}

.progression-item {
  text-align: center;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.progression-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.progression-value {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
}

.progression-value.positive { color: var(--color-success); }
.progression-value.negative { color: var(--color-error); }

.dashboard-footer {
  text-align: center;
  padding: var(--spacing-5);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

@media (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .header-controls {
    width: 100%;
    justify-content: center;
  }

  .main-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
