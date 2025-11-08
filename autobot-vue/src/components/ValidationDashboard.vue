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
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 10px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.dashboard-header h1 {
  margin: 0;
  font-size: 2em;
}

.header-controls {
  display: flex;
  gap: 20px;
  align-items: center;
}

.refresh-btn {
  background: rgba(255,255,255,0.2);
  color: white;
  border: 1px solid rgba(255,255,255,0.3);
  padding: 8px 16px;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.3);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auto-refresh label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9em;
}

.loading-state, .error-state {
  text-align: center;
  padding: 60px 20px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-state {
  color: #e74c3c;
}

.retry-btn {
  background: #e74c3c;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 5px;
  cursor: pointer;
  margin-top: 10px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.stat-card-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.stat-icon {
  font-size: 2.5em;
}

.stat-value {
  font-size: 2.5em;
  font-weight: bold;
  margin-bottom: 5px;
}

.stat-label {
  color: #666;
  font-size: 0.9em;
}

.health-excellent { color: #4CAF50; }
.health-good { color: #8BC34A; }
.health-fair { color: #FF9800; }
.health-needs_attention { color: #F44336; }

.main-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 30px;
  margin-bottom: 30px;
}

.phases-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.phase-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  border-left: 4px solid #ddd;
}

.phase-name {
  font-weight: bold;
  font-size: 1.1em;
}

.phase-requirements {
  font-size: 0.9em;
  color: #666;
  margin-top: 5px;
}

.phase-progress {
  text-align: right;
  min-width: 120px;
}

.progress-text {
  font-weight: bold;
  margin-bottom: 5px;
}

.progress-bar {
  width: 100px;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.alert-time {
  font-size: 0.8em;
  opacity: 0.7;
  margin-top: 5px;
}

.recommendation {
  padding: 15px;
  margin: 10px 0;
  background: #f8f9fa;
  border-radius: 5px;
  border-left: 4px solid #007bff;
}

.rec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.rec-title {
  font-weight: bold;
  flex: 1;
}

.rec-urgency {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.7em;
  font-weight: bold;
  margin-left: 10px;
}

.urgency-high { background: #ffcdd2; color: #c62828; }
.urgency-medium { background: #ffe0b2; color: #e65100; }
.urgency-low { background: #c8e6c9; color: #2e7d32; }

.rec-description {
  margin-bottom: 10px;
  font-size: 0.9em;
}

.rec-action {
  font-style: italic;
  color: #666;
  font-size: 0.9em;
}

.progression-section {
  margin-bottom: 20px;
}

.progression-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}

.progression-item {
  text-align: center;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
}

.progression-label {
  font-size: 0.9em;
  color: #666;
  margin-bottom: 5px;
}

.progression-value {
  font-size: 1.2em;
  font-weight: bold;
}

.progression-value.positive { color: #4CAF50; }
.progression-value.negative { color: #F44336; }

.dashboard-footer {
  text-align: center;
  padding: 20px;
  color: #666;
  font-size: 0.9em;
}

@media (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    gap: 15px;
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
