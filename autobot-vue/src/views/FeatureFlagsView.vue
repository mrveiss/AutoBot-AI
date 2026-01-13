<template>
  <div class="feature-flags-view">
    <!-- Sidebar Navigation -->
    <aside class="flags-sidebar">
      <div class="sidebar-header">
        <h3><i class="fas fa-flag"></i> Feature Flags</h3>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav">
        <div
          class="category-item"
          :class="{ active: activeSection === 'overview' }"
          @click="activeSection = 'overview'"
        >
          <i class="fas fa-tachometer-alt"></i>
          <span>Overview</span>
        </div>

        <div class="category-divider">
          <span>Configuration</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'enforcement' }"
          @click="activeSection = 'enforcement'"
        >
          <i class="fas fa-shield-alt"></i>
          <span>Enforcement Mode</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'endpoints' }"
          @click="activeSection = 'endpoints'"
        >
          <i class="fas fa-sitemap"></i>
          <span>Endpoint Overrides</span>
          <span class="count" v-if="endpointOverrideCount > 0">{{ endpointOverrideCount }}</span>
        </div>

        <div class="category-divider">
          <span>Analytics</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'metrics' }"
          @click="activeSection = 'metrics'"
        >
          <i class="fas fa-chart-bar"></i>
          <span>Access Metrics</span>
          <span class="count alert" v-if="totalViolations > 0">{{ totalViolations }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'history' }"
          @click="activeSection = 'history'"
        >
          <i class="fas fa-history"></i>
          <span>Change History</span>
        </div>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="loadAllData" class="btn-refresh" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flags-content">
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ sectionTitle }}</h2>
          <span class="subtitle">{{ sectionDescription }}</span>
        </div>
        <div class="header-actions">
          <div class="mode-badge" :class="currentMode">
            <i :class="modeIcon"></i>
            <span>{{ modeLabel }}</span>
          </div>
        </div>
      </header>

      <!-- Loading State -->
      <div v-if="loading && !hasData" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>Loading feature flags data...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-container">
        <div class="error-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <h3>Failed to Load Data</h3>
        <p>{{ error }}</p>
        <button @click="loadAllData" class="btn-primary">
          <i class="fas fa-redo"></i> Retry
        </button>
      </div>

      <!-- Content Sections -->
      <div v-else class="content-body">
        <!-- Overview Section -->
        <section v-if="activeSection === 'overview'" class="section-overview">
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon" :class="currentMode">
                <i :class="modeIcon"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ modeLabel }}</span>
                <span class="stat-label">Current Mode</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-sitemap"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ endpointOverrideCount }}</span>
                <span class="stat-label">Endpoint Overrides</span>
              </div>
            </div>

            <div class="stat-card" :class="{ alert: totalViolations > 0 }">
              <div class="stat-icon">
                <i class="fas fa-exclamation-circle"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ totalViolations }}</span>
                <span class="stat-label">Violations (7d)</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-clock"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ historyCount }}</span>
                <span class="stat-label">Recent Changes</span>
              </div>
            </div>
          </div>

          <div class="overview-sections">
            <EnforcementModeSelector
              :current-mode="currentMode"
              :loading="modeUpdateLoading"
              @update:mode="handleModeUpdate"
            />

            <AccessMetrics
              :metrics="accessMetrics"
              :loading="metricsLoading"
              compact
              @refresh="loadAccessMetrics"
            />
          </div>
        </section>

        <!-- Enforcement Mode Section -->
        <section v-if="activeSection === 'enforcement'" class="section-enforcement">
          <EnforcementModeSelector
            :current-mode="currentMode"
            :loading="modeUpdateLoading"
            @update:mode="handleModeUpdate"
          />
        </section>

        <!-- Endpoint Overrides Section -->
        <section v-if="activeSection === 'endpoints'" class="section-endpoints">
          <EndpointEnforcement
            :overrides="endpointOverrides"
            :global-mode="currentMode"
            :loading="endpointLoading"
            @add="handleAddEndpoint"
            @remove="handleRemoveEndpoint"
            @update="handleUpdateEndpoint"
          />
        </section>

        <!-- Access Metrics Section -->
        <section v-if="activeSection === 'metrics'" class="section-metrics">
          <AccessMetrics
            :metrics="accessMetrics"
            :loading="metricsLoading"
            @refresh="loadAccessMetrics"
            @view-endpoint="handleViewEndpointMetrics"
            @view-user="handleViewUserMetrics"
          />
        </section>

        <!-- Change History Section -->
        <section v-if="activeSection === 'history'" class="section-history">
          <FlagChangeHistory
            :history="changeHistory"
            :loading="loading"
          />
        </section>
      </div>
    </main>

    <!-- Endpoint Metrics Modal -->
    <BaseModal
      v-model="showEndpointModal"
      :title="`Endpoint Metrics: ${selectedEndpoint}`"
      size="large"
    >
      <div v-if="endpointMetricsLoading" class="loading-container">
        <LoadingSpinner />
      </div>
      <div v-else-if="selectedEndpointMetrics" class="endpoint-metrics-detail">
        <div class="metric-summary">
          <div class="metric-item">
            <span class="metric-value">{{ selectedEndpointMetrics.total_violations }}</span>
            <span class="metric-label">Total Violations</span>
          </div>
          <div class="metric-item">
            <span class="metric-value">{{ selectedEndpointMetrics.period_days }}</span>
            <span class="metric-label">Days Analyzed</span>
          </div>
        </div>
        <div class="daily-breakdown">
          <h4>Daily Breakdown</h4>
          <div class="breakdown-grid">
            <div
              v-for="(count, date) in selectedEndpointMetrics.by_day"
              :key="date"
              class="breakdown-item"
            >
              <span class="date">{{ formatDate(date) }}</span>
              <span class="count">{{ count }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #actions>
        <button @click="showEndpointModal = false" class="btn-secondary">Close</button>
      </template>
    </BaseModal>

    <!-- User Metrics Modal -->
    <BaseModal
      v-model="showUserModal"
      :title="`User Metrics: ${selectedUser}`"
      size="large"
    >
      <div v-if="userMetricsLoading" class="loading-container">
        <LoadingSpinner />
      </div>
      <div v-else-if="selectedUserMetrics" class="user-metrics-detail">
        <div class="metric-summary">
          <div class="metric-item">
            <span class="metric-value">{{ selectedUserMetrics.total_violations }}</span>
            <span class="metric-label">Total Violations</span>
          </div>
          <div class="metric-item">
            <span class="metric-value">{{ selectedUserMetrics.period_days }}</span>
            <span class="metric-label">Days Analyzed</span>
          </div>
        </div>
        <div class="daily-breakdown">
          <h4>Daily Breakdown</h4>
          <div class="breakdown-grid">
            <div
              v-for="(count, date) in selectedUserMetrics.by_day"
              :key="date"
              class="breakdown-item"
            >
              <span class="date">{{ formatDate(date) }}</span>
              <span class="count">{{ count }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #actions>
        <button @click="showUserModal = false" class="btn-secondary">Close</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useToast } from '@/composables/useToast';
import {
  featureFlagsApiClient,
  type EnforcementMode,
  type FeatureFlagsStatus,
  type ViolationStatistics,
  type EndpointStatistics,
  type UserStatistics,
} from '@/utils/FeatureFlagsApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseModal from '@/components/ui/BaseModal.vue';
import EnforcementModeSelector from '@/components/feature-flags/EnforcementModeSelector.vue';
import EndpointEnforcement from '@/components/feature-flags/EndpointEnforcement.vue';
import AccessMetrics from '@/components/feature-flags/AccessMetrics.vue';
import FlagChangeHistory from '@/components/feature-flags/FlagChangeHistory.vue';

const logger = createLogger('FeatureFlagsView');
const { showToast } = useToast();

// State
const loading = ref(false);
const error = ref<string | null>(null);
const activeSection = ref<'overview' | 'enforcement' | 'endpoints' | 'metrics' | 'history'>('overview');

// Feature Flags State
const currentMode = ref<EnforcementMode>('disabled');
const endpointOverrides = ref<Record<string, EnforcementMode>>({});
const changeHistory = ref<Array<{ timestamp: string; mode: EnforcementMode; changed_by: string }>>([]);

// Metrics State
const accessMetrics = ref<ViolationStatistics | null>(null);
const metricsLoading = ref(false);

// Update State
const modeUpdateLoading = ref(false);
const endpointLoading = ref(false);

// Modal State
const showEndpointModal = ref(false);
const selectedEndpoint = ref('');
const selectedEndpointMetrics = ref<EndpointStatistics | null>(null);
const endpointMetricsLoading = ref(false);

const showUserModal = ref(false);
const selectedUser = ref('');
const selectedUserMetrics = ref<UserStatistics | null>(null);
const userMetricsLoading = ref(false);

// Computed
const hasData = computed(() => currentMode.value !== null);

const endpointOverrideCount = computed(() => Object.keys(endpointOverrides.value).length);

const totalViolations = computed(() => accessMetrics.value?.total_violations ?? 0);

const historyCount = computed(() => changeHistory.value.length);

const modeLabel = computed(() => {
  const labels: Record<EnforcementMode, string> = {
    disabled: 'Disabled',
    log_only: 'Log Only',
    enforced: 'Enforced',
  };
  return labels[currentMode.value] || 'Unknown';
});

const modeIcon = computed(() => {
  const icons: Record<EnforcementMode, string> = {
    disabled: 'fas fa-ban',
    log_only: 'fas fa-clipboard-list',
    enforced: 'fas fa-shield-alt',
  };
  return icons[currentMode.value] || 'fas fa-question';
});

const sectionTitle = computed(() => {
  const titles: Record<string, string> = {
    overview: 'Feature Flags Overview',
    enforcement: 'Enforcement Mode',
    endpoints: 'Endpoint Overrides',
    metrics: 'Access Control Metrics',
    history: 'Change History',
  };
  return titles[activeSection.value] || 'Feature Flags';
});

const sectionDescription = computed(() => {
  const descriptions: Record<string, string> = {
    overview: 'Monitor and manage access control feature flags',
    enforcement: 'Configure the global enforcement mode for access control',
    endpoints: 'Set custom enforcement modes for specific API endpoints',
    metrics: 'View access control violation statistics and trends',
    history: 'Review recent changes to feature flag configuration',
  };
  return descriptions[activeSection.value] || '';
});

// Methods
const loadAllData = async () => {
  loading.value = true;
  error.value = null;

  try {
    await Promise.all([
      loadFeatureFlagsStatus(),
      loadAccessMetrics(),
    ]);
  } catch (err) {
    logger.error('Failed to load data:', err);
    error.value = err instanceof Error ? err.message : 'Failed to load feature flags data';
  } finally {
    loading.value = false;
  }
};

const loadFeatureFlagsStatus = async () => {
  const response = await featureFlagsApiClient.getFeatureFlagsStatus();

  if (response.success && response.data) {
    currentMode.value = response.data.current_mode;
    endpointOverrides.value = response.data.endpoint_overrides || {};
    changeHistory.value = response.data.history || [];
    logger.debug('Loaded feature flags status:', response.data);
  } else {
    throw new Error(response.error || 'Failed to load feature flags status');
  }
};

const loadAccessMetrics = async () => {
  metricsLoading.value = true;
  try {
    const response = await featureFlagsApiClient.getAccessControlMetrics({
      days: 7,
      include_details: true,
    });

    if (response.success && response.data) {
      accessMetrics.value = response.data;
      logger.debug('Loaded access metrics:', response.data);
    }
  } catch (err) {
    logger.error('Failed to load access metrics:', err);
  } finally {
    metricsLoading.value = false;
  }
};

const handleModeUpdate = async (newMode: EnforcementMode) => {
  modeUpdateLoading.value = true;
  try {
    const response = await featureFlagsApiClient.updateEnforcementMode(newMode);

    if (response.success) {
      currentMode.value = newMode;
      // Refresh to get updated history
      await loadFeatureFlagsStatus();
      showToast(`Enforcement mode updated to ${newMode}`, 'success');
      logger.info('Enforcement mode updated to:', newMode);
    } else {
      showToast(response.error || 'Failed to update enforcement mode', 'error');
      logger.error('Failed to update enforcement mode:', response.error);
    }
  } catch (err) {
    showToast('Failed to update enforcement mode', 'error');
    logger.error('Failed to update enforcement mode:', err);
  } finally {
    modeUpdateLoading.value = false;
  }
};

const handleAddEndpoint = async (endpoint: string, mode: EnforcementMode) => {
  endpointLoading.value = true;
  try {
    const response = await featureFlagsApiClient.setEndpointEnforcement(endpoint, mode);

    if (response.success) {
      endpointOverrides.value = { ...endpointOverrides.value, [endpoint]: mode };
      showToast('Endpoint override added', 'success');
      logger.info('Added endpoint enforcement:', endpoint, mode);
    } else {
      showToast(response.error || 'Failed to add endpoint override', 'error');
      logger.error('Failed to add endpoint enforcement:', response.error);
    }
  } catch (err) {
    showToast('Failed to add endpoint override', 'error');
    logger.error('Failed to add endpoint enforcement:', err);
  } finally {
    endpointLoading.value = false;
  }
};

const handleUpdateEndpoint = async (endpoint: string, mode: EnforcementMode) => {
  await handleAddEndpoint(endpoint, mode);
};

const handleRemoveEndpoint = async (endpoint: string) => {
  endpointLoading.value = true;
  try {
    const response = await featureFlagsApiClient.removeEndpointEnforcement(endpoint);

    if (response.success) {
      const newOverrides = { ...endpointOverrides.value };
      delete newOverrides[endpoint];
      endpointOverrides.value = newOverrides;
      showToast('Endpoint override removed', 'success');
      logger.info('Removed endpoint enforcement:', endpoint);
    } else {
      showToast(response.error || 'Failed to remove endpoint override', 'error');
      logger.error('Failed to remove endpoint enforcement:', response.error);
    }
  } catch (err) {
    showToast('Failed to remove endpoint override', 'error');
    logger.error('Failed to remove endpoint enforcement:', err);
  } finally {
    endpointLoading.value = false;
  }
};

const handleViewEndpointMetrics = async (endpoint: string) => {
  selectedEndpoint.value = endpoint;
  showEndpointModal.value = true;
  endpointMetricsLoading.value = true;
  selectedEndpointMetrics.value = null;

  try {
    const response = await featureFlagsApiClient.getEndpointMetrics(endpoint, 7);

    if (response.success && response.data) {
      selectedEndpointMetrics.value = response.data;
    }
  } catch (err) {
    logger.error('Failed to load endpoint metrics:', err);
  } finally {
    endpointMetricsLoading.value = false;
  }
};

const handleViewUserMetrics = async (username: string) => {
  selectedUser.value = username;
  showUserModal.value = true;
  userMetricsLoading.value = true;
  selectedUserMetrics.value = null;

  try {
    const response = await featureFlagsApiClient.getUserMetrics(username, 7);

    if (response.success && response.data) {
      selectedUserMetrics.value = response.data;
    }
  } catch (err) {
    logger.error('Failed to load user metrics:', err);
  } finally {
    userMetricsLoading.value = false;
  }
};

const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Lifecycle
onMounted(() => {
  loadAllData();
});
</script>

<style scoped>
.feature-flags-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.flags-sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-header i {
  color: var(--color-primary);
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.category-divider {
  padding: 12px 20px 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-secondary);
}

.category-item:hover {
  background: var(--bg-hover);
}

.category-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: 14px;
}

.category-item span:first-of-type:not(.count) {
  flex: 1;
  font-size: 14px;
}

.category-item .count {
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--text-tertiary);
}

.category-item.active .count {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.category-item .count.alert {
  background: var(--color-error);
  color: var(--text-on-error);
}

.sidebar-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}

.btn-refresh {
  width: 100%;
  padding: 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Main Content */
.flags-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.mode-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.mode-badge.disabled {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.mode-badge.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.mode-badge.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

/* Loading & Error States */
.loading-container,
.error-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-tertiary);
  padding: 40px;
}

.error-container .error-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.error-container h3 {
  margin: 0;
  color: var(--text-primary);
}

.error-container p {
  margin: 0;
  color: var(--text-secondary);
}

/* Content Body */
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* Overview Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.stat-card.alert {
  border-color: var(--color-error);
}

.stat-card .stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--text-secondary);
}

.stat-card .stat-icon.disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.stat-card .stat-icon.log_only {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.stat-card .stat-icon.enforced {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.stat-card.alert .stat-icon {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Overview Sections */
.overview-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Modal Content */
.endpoint-metrics-detail,
.user-metrics-detail {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.metric-summary {
  display: flex;
  gap: 24px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 24px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.metric-item .metric-value {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
}

.metric-item .metric-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.daily-breakdown h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
}

.breakdown-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}

.breakdown-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.breakdown-item .date {
  font-size: 12px;
  color: var(--text-tertiary);
}

.breakdown-item .count {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Buttons */
.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

/* Responsive */
@media (max-width: 768px) {
  .feature-flags-view {
    flex-direction: column;
  }

  .flags-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
