<template>
  <div class="access-metrics" :class="{ compact }">
    <div class="section-header">
      <div class="header-info">
        <h3><Icon name="chart-bar" /> {{ $t('featureFlags.accessMetrics.title') }}</h3>
        <p v-if="!compact" class="description">
          {{ $t('featureFlags.accessMetrics.description') }}
        </p>
      </div>
      <div class="header-actions">
        <select
          v-model="selectedDays"
          class="days-selector"
          :aria-label="$t('featureFlags.accessMetrics.title')"
          @change="handleDaysChange"
        >
          <option :value="7">{{ $t('featureFlags.accessMetrics.last7Days') }}</option>
          <option :value="14">{{ $t('featureFlags.accessMetrics.last14Days') }}</option>
          <option :value="30">{{ $t('featureFlags.accessMetrics.last30Days') }}</option>
        </select>
        <button
          @click="handleRefresh"
          class="btn-refresh"
          :disabled="loading"
          :aria-label="$t('common.refresh')"
        >
          <Icon name="sync-alt" />
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
        <Icon name="check-circle" />
      </div>
      <h4>{{ $t('featureFlags.accessMetrics.noData') }}</h4>
      <p>{{ $t('featureFlags.accessMetrics.noData') }}</p>
    </div>

    <!-- Metrics Content -->
    <div v-else class="metrics-content">
      <!-- Summary Stats -->
      <div class="summary-stats">
        <div class="summary-card total" :class="{ alert: metrics.total_violations > 0 }">
          <div class="summary-icon">
            <Icon name="exclamation-circle" />
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ metrics.total_violations }}</span>
            <span class="summary-label">{{ $t('featureFlags.accessMetrics.totalViolations') }}</span>
          </div>
          <div class="trend" v-if="metrics.daily_change_percent !== undefined">
            <span :class="trendClass">
              <Icon :name="trendIcon" />
              {{ Math.abs(metrics.daily_change_percent) }}%
            </span>
            <span class="trend-label">{{ $t('featureFlags.accessMetrics.vsYesterday') }}</span>
          </div>
        </div>

        <div class="summary-card">
          <div class="summary-icon">
            <Icon name="sitemap" />
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ endpointCount }}</span>
            <span class="summary-label">{{ $t('featureFlags.accessMetrics.endpointsAffected') }}</span>
          </div>
        </div>

        <div class="summary-card">
          <div class="summary-icon">
            <Icon name="users" />
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ userCount }}</span>
            <span class="summary-label">{{ $t('featureFlags.accessMetrics.usersInvolved') }}</span>
          </div>
        </div>

        <div class="summary-card">
          <div class="summary-icon">
            <Icon name="calendar" />
          </div>
          <div class="summary-info">
            <span class="summary-value">{{ metrics.period_days }}</span>
            <span class="summary-label">{{ $t('featureFlags.accessMetrics.daysAnalyzed') }}</span>
          </div>
        </div>
      </div>

      <!-- Detailed Breakdowns (not in compact mode) -->
      <div v-if="!compact" class="breakdowns">
        <!-- By Endpoint -->
        <div class="breakdown-section">
          <h4><Icon name="sitemap" /> {{ $t('featureFlags.accessMetrics.byEndpoint') }}</h4>
          <div v-if="Object.keys(metrics.by_endpoint).length === 0" class="empty-breakdown">
            {{ $t('featureFlags.accessMetrics.noEndpointData') }}
          </div>
          <div v-else class="breakdown-list">
            <div
              v-for="(count, endpoint) in sortedEndpoints"
              :key="endpoint"
              class="breakdown-item clickable"
              @click="$emit('view-endpoint', String(endpoint))"
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
          <h4><Icon name="users" /> {{ $t('featureFlags.accessMetrics.byUser') }}</h4>
          <div v-if="Object.keys(metrics.by_user).length === 0" class="empty-breakdown">
            {{ $t('featureFlags.accessMetrics.noUserData') }}
          </div>
          <div v-else class="breakdown-list">
            <div
              v-for="(count, user) in sortedUsers"
              :key="user"
              class="breakdown-item clickable"
              @click="$emit('view-user', String(user))"
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
          <h4><Icon name="chart-line" /> {{ $t('featureFlags.accessMetrics.dailyTrend') }}</h4>
          <div v-if="Object.keys(metrics.by_day).length === 0" class="empty-breakdown">
            {{ $t('featureFlags.accessMetrics.noTrendData') }}
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
              <span class="day-label">{{ formatDayLabel(String(date)) }}</span>
              <span class="day-count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- Recent Violations -->
        <div v-if="metrics.recent_violations?.length" class="breakdown-section full-width">
          <h4><Icon name="clock" /> {{ $t('featureFlags.accessMetrics.recentViolations') }}</h4>
          <div class="violations-table">
            <div class="table-header">
              <span class="col-time">{{ $t('featureFlags.accessMetrics.time') }}</span>
              <span class="col-user">{{ $t('featureFlags.accessMetrics.user') }}</span>
              <span class="col-endpoint">{{ $t('featureFlags.accessMetrics.endpoint') }}</span>
              <span class="col-owner">{{ $t('featureFlags.accessMetrics.owner') }}</span>
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
import Icon from '@/components/ui/Icon.vue'
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
  if (change === undefined) return 'minus';
  if (change > 0) return 'arrow-up';
  if (change < 0) return 'arrow-down';
  return 'minus';
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
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.access-metrics.compact {
  padding: var(--spacing-5);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-5);
}

.header-info h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-info h3 i {
  color: var(--color-primary);
}

.header-info .description {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

.days-selector {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: var(--text-sm);
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
  border-radius: var(--radius-lg);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-150);
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
  padding: var(--spacing-10);
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
  margin-bottom: var(--spacing-4);
}

.no-data-state h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.no-data-state p {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Summary Stats */
.summary-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.compact .summary-stats {
  margin-bottom: var(--spacing-0);
}

.summary-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-3-5);
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
}

.summary-card.alert {
  border-color: var(--color-error);
}

.summary-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-xl);
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-lg);
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
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
}

.summary-label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.trend {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.trend span:first-child {
  font-size: var(--text-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
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
  font-size: var(--text-xs);
  color: var(--text-muted);
}

/* Breakdowns */
.breakdowns {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-6);
}

.breakdown-section {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-4);
}

.breakdown-section.full-width {
  grid-column: 1 / -1;
}

.breakdown-section h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.empty-breakdown {
  text-align: center;
  padding: var(--spacing-5);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.breakdown-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2-5);
  max-height: 250px;
  overflow-y: auto;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.breakdown-item.clickable {
  cursor: pointer;
  padding: var(--spacing-2);
  margin: var(--spacing-neg-8px);
  border-radius: var(--radius-md);
  transition: background var(--duration-150);
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
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: var(--spacing-1);
}

code.item-label {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.item-bar {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--color-error);
  border-radius: var(--radius-default);
  transition: width var(--duration-300) var(--ease-out);
}

.item-count {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

/* Daily Chart */
.daily-chart {
  display: flex;
  gap: var(--spacing-2);
  align-items: flex-end;
  height: 150px;
  padding-top: var(--spacing-5);
}

.day-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
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
  border-radius: var(--radius-default) 4px 0 0;
  min-height: 4px;
  transition: height var(--duration-300) var(--ease-out);
}

.day-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.day-count {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-primary);
}

/* Violations Table */
.violations-table {
  font-size: var(--text-sm);
}

.table-header {
  display: grid;
  grid-template-columns: 120px 100px 1fr 100px;
  gap: var(--spacing-4);
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.table-row {
  display: grid;
  grid-template-columns: 120px 100px 1fr 100px;
  gap: var(--spacing-4);
  padding: var(--spacing-2-5) var(--spacing-3);
  border-bottom: 1px solid var(--border-subtle);
}

.table-row:last-child {
  border-bottom: none;
}

.col-endpoint code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
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
