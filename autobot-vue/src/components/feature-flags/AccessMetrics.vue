<template>
  <div class="access-metrics" :class="{ compact }">
    <div class="section-header">
      <div class="header-info">
        <h3><i class="fas fa-chart-bar"></i> Access Control Metrics</h3>
        <p v-if="!compact" class="description">
          Monitor access control violations during LOG_ONLY mode before enabling full enforcement
        </p>
      </div>
      <div class="header-actions">
        <select v-model="selectedDays" class="days-selector" @change="handleDaysChange">
          <option :value="7">Last 7 days</option>
          <option :value="14">Last 14 days</option>
          <option :value="30">Last 30 days</option>
        </select>
        <button @click="handleRefresh" class="btn-refresh" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !metrics" class="loading-state">
      <LoadingSpinner />
    </div>

    <!-- No Data State -->
    <div v-else-if="!metrics || metrics.total_violations === 0" class="no-data-state">
      <div class="no-data-icon">
        <i class="fas fa-check-circle"></i>
      </div>
      <h4>No Violations Recorded</h4>
      <p>No access control violations have been detected in the selected period.</p>
    </div>

    <!-- Metrics Content -->
    <div v-else class="metrics-content">
      <!-- Summary Stats -->
      <div class="summary-stats">
        <div class="summary-card total" :class="{ alert: metrics.total_violations > 0 }">
          <div class="summary-icon">
            <i class="fas fa-exclamation-circle"></i>
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ metrics.total_violations }}</span>
            <span class="summary-label">Total Violations</span>
          </div>
          <div class="trend" v-if="metrics.daily_change_percent !== undefined">
            <span :class="trendClass">
              <i :class="trendIcon"></i>
              {{ Math.abs(metrics.daily_change_percent) }}%
            </span>
            <span class="trend-label">vs yesterday</span>
          </div>
        </div>

        <div class="summary-card">
          <div class="summary-icon">
            <i class="fas fa-sitemap"></i>
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ endpointCount }}</span>
            <span class="summary-label">Endpoints Affected</span>
          </div>
        </div>

        <div class="summary-card">
          <div class="summary-icon">
            <i class="fas fa-users"></i>
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ userCount }}</span>
            <span class="summary-label">Users Involved</span>
          </div>
        </div>

        <div class="summary-card">
          <div class="summary-icon">
            <i class="fas fa-calendar"></i>
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ metrics.period_days }}</span>
            <span class="summary-label">Days Analyzed</span>
          </div>
        </div>
      </div>

      <!-- Detailed Breakdowns (not in compact mode) -->
      <div v-if="!compact" class="breakdowns">
        <!-- By Endpoint -->
        <div class="breakdown-section">
          <h4><i class="fas fa-sitemap"></i> By Endpoint</h4>
          <div v-if="Object.keys(metrics.by_endpoint).length === 0" class="empty-breakdown">
            No endpoint data available
          </div>
          <div v-else class="breakdown-list">
            <div
              v-for="(count, endpoint) in sortedEndpoints"
              :key="endpoint"
              class="breakdown-item clickable"
              @click="$emit('view-endpoint', endpoint)"
            >
              <div class="item-info">
                <code class="item-label">{{ endpoint }}</code>
                <div class="item-bar">
                  <div
                    class="bar-fill"
                    :style="{ width: getPercentage(count, maxEndpointCount) + '%' }"
                  ></div>
                </div>
              </div>
              <span class="item-count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- By User -->
        <div class="breakdown-section">
          <h4><i class="fas fa-users"></i> By User</h4>
          <div v-if="Object.keys(metrics.by_user).length === 0" class="empty-breakdown">
            No user data available
          </div>
          <div v-else class="breakdown-list">
            <div
              v-for="(count, user) in sortedUsers"
              :key="user"
              class="breakdown-item clickable"
              @click="$emit('view-user', user)"
            >
              <div class="item-info">
                <span class="item-label">{{ user }}</span>
                <div class="item-bar">
                  <div
                    class="bar-fill"
                    :style="{ width: getPercentage(count, maxUserCount) + '%' }"
                  ></div>
                </div>
              </div>
              <span class="item-count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- Daily Trend -->
        <div class="breakdown-section full-width">
          <h4><i class="fas fa-chart-line"></i> Daily Trend</h4>
          <div v-if="Object.keys(metrics.by_day).length === 0" class="empty-breakdown">
            No daily data available
          </div>
          <div v-else class="daily-chart">
            <div
              v-for="(count, date) in sortedDays"
              :key="date"
              class="day-bar"
            >
              <div class="bar-container">
                <div
                  class="bar"
                  :style="{ height: getPercentage(count, maxDayCount) + '%' }"
                ></div>
              </div>
              <span class="day-label">{{ formatDayLabel(date) }}</span>
              <span class="day-count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- Recent Violations -->
        <div v-if="metrics.recent_violations?.length" class="breakdown-section full-width">
          <h4><i class="fas fa-clock"></i> Recent Violations</h4>
          <div class="violations-table">
            <div class="table-header">
              <span class="col-time">Time</span>
              <span class="col-user">User</span>
              <span class="col-endpoint">Endpoint</span>
              <span class="col-owner">Owner</span>
            </div>
            <div
              v-for="violation in metrics.recent_violations.slice(0, 10)"
              :key="violation.id"
              class="table-row"
            >
              <span class="col-time">{{ formatTime(violation.timestamp) }}</span>
              <span class="col-user">{{ violation.username }}</span>
              <span class="col-endpoint">
                <code>{{ violation.endpoint }}</code>
              </span>
              <span class="col-owner">{{ violation.actual_owner }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { ViolationStatistics } from '@/utils/FeatureFlagsApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';

const props = defineProps<{
  metrics: ViolationStatistics | null;
  loading: boolean;
  compact?: boolean;
}>();

const emit = defineEmits<{
  (e: 'refresh', days?: number): void;
  (e: 'view-endpoint', endpoint: string): void;
  (e: 'view-user', username: string): void;
}>();

const selectedDays = ref(7);

// Computed
const endpointCount = computed(() =>
  props.metrics ? Object.keys(props.metrics.by_endpoint).length : 0
);

const userCount = computed(() =>
  props.metrics ? Object.keys(props.metrics.by_user).length : 0
);

const sortedEndpoints = computed(() => {
  if (!props.metrics?.by_endpoint) return {};
  return Object.fromEntries(
    Object.entries(props.metrics.by_endpoint)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10)
  );
});

const sortedUsers = computed(() => {
  if (!props.metrics?.by_user) return {};
  return Object.fromEntries(
    Object.entries(props.metrics.by_user)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10)
  );
});

const sortedDays = computed(() => {
  if (!props.metrics?.by_day) return {};
  return Object.fromEntries(
    Object.entries(props.metrics.by_day).sort(([a], [b]) => a.localeCompare(b))
  );
});

const maxEndpointCount = computed(() =>
  Math.max(...Object.values(props.metrics?.by_endpoint || { _: 1 }), 1)
);

const maxUserCount = computed(() =>
  Math.max(...Object.values(props.metrics?.by_user || { _: 1 }), 1)
);

const maxDayCount = computed(() =>
  Math.max(...Object.values(props.metrics?.by_day || { _: 1 }), 1)
);

const trendClass = computed(() => {
  const change = props.metrics?.daily_change_percent;
  if (change === undefined) return '';
  if (change > 0) return 'trend-up';
  if (change < 0) return 'trend-down';
  return 'trend-neutral';
});

const trendIcon = computed(() => {
  const change = props.metrics?.daily_change_percent;
  if (change === undefined) return 'fas fa-minus';
  if (change > 0) return 'fas fa-arrow-up';
  if (change < 0) return 'fas fa-arrow-down';
  return 'fas fa-minus';
});

// Methods
const handleRefresh = () => {
  emit('refresh', selectedDays.value);
};

const handleDaysChange = () => {
  emit('refresh', selectedDays.value);
};

const getPercentage = (value: number, max: number) => {
  return Math.min((value / max) * 100, 100);
};

const formatDayLabel = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { weekday: 'short' });
};

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp * 1000);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};
</script>

<style scoped>
.access-metrics {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.access-metrics.compact {
  padding: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.header-info h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-info h3 i {
  color: var(--color-primary);
}

.header-info .description {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.days-selector {
  padding: 8px 12px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.btn-refresh {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Loading & Empty States */
.loading-state,
.no-data-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--text-tertiary);
}

.no-data-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-success-bg);
  color: var(--color-success);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  margin-bottom: 16px;
}

.no-data-state h4 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.no-data-state p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

/* Summary Stats */
.summary-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.compact .summary-stats {
  margin-bottom: 0;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
}

.summary-card.alert {
  border-color: var(--color-error);
}

.summary-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--text-secondary);
}

.summary-card.total .summary-icon {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.summary-info {
  flex: 1;
}

.summary-value {
  display: block;
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.summary-label {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary);
}

.trend {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.trend span:first-child {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
}

.trend-up {
  color: var(--color-error);
}

.trend-down {
  color: var(--color-success);
}

.trend-neutral {
  color: var(--text-muted);
}

.trend-label {
  font-size: 11px;
  color: var(--text-muted);
}

/* Breakdowns */
.breakdowns {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.breakdown-section {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 16px;
}

.breakdown-section.full-width {
  grid-column: 1 / -1;
}

.breakdown-section h4 {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-breakdown {
  text-align: center;
  padding: 20px;
  color: var(--text-muted);
  font-size: 14px;
}

.breakdown-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 250px;
  overflow-y: auto;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.breakdown-item.clickable {
  cursor: pointer;
  padding: 8px;
  margin: -8px;
  border-radius: 6px;
  transition: background 0.15s;
}

.breakdown-item.clickable:hover {
  background: var(--bg-hover);
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-label {
  display: block;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

code.item-label {
  font-family: var(--font-mono);
  font-size: 12px;
}

.item-bar {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--color-error);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.item-count {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

/* Daily Chart */
.daily-chart {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  height: 150px;
  padding-top: 20px;
}

.day-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 40px;
}

.bar-container {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.day-bar .bar {
  width: 100%;
  background: var(--color-error);
  border-radius: 4px 4px 0 0;
  min-height: 4px;
  transition: height 0.3s ease;
}

.day-label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.day-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Violations Table */
.violations-table {
  font-size: 13px;
}

.table-header {
  display: grid;
  grid-template-columns: 120px 100px 1fr 100px;
  gap: 16px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.table-row {
  display: grid;
  grid-template-columns: 120px 100px 1fr 100px;
  gap: 16px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.table-row:last-child {
  border-bottom: none;
}

.col-endpoint code {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

/* Responsive */
@media (max-width: 768px) {
  .breakdowns {
    grid-template-columns: 1fr;
  }

  .summary-stats {
    grid-template-columns: 1fr 1fr;
  }

  .table-header,
  .table-row {
    grid-template-columns: 1fr 1fr;
  }

  .col-endpoint,
  .col-owner {
    display: none;
  }
}
</style>
