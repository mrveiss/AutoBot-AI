<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

FeatureFlagsSettingsPanel.vue - Feature Flags and Access Control Management
Issue #4273: Wire orphaned components EnforcementModeSelector, FlagChangeHistory, EndpointEnforcement, AccessMetrics
-->

<template>
  <div class="feature-flags-settings-panel">
    <!-- Loading State -->
    <div v-if="loading && !featureFlagsStatus" class="loading-state">
      <LoadingSpinner />
      <p>{{ $t('featureFlags.loading') }}</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <BaseAlert variant="error" :message="error">
        <template #actions>
          <button @click="loadData" class="retry-btn">
            <Icon name="redo" />
            {{ $t('featureFlags.retry') }}
          </button>
        </template>
      </BaseAlert>
    </div>

    <!-- Main Content -->
    <div v-else class="settings-content">
      <!-- Operation Error -->
      <BaseAlert
        v-if="operationError"
        variant="error"
        :message="operationError"
        dismissible
        @dismiss="operationError = null"
      />

      <!-- Enforcement Mode Selector -->
      <section class="settings-section">
        <EnforcementModeSelector
          v-if="featureFlagsStatus"
          :current-mode="featureFlagsStatus.current_mode"
          :loading="updating"
          @update:mode="handleModeChange"
        />
      </section>

      <!-- Endpoint Enforcement Overrides -->
      <section class="settings-section">
        <EndpointEnforcement
          v-if="featureFlagsStatus"
          :overrides="featureFlagsStatus.endpoint_overrides"
          :global-mode="featureFlagsStatus.current_mode"
          :loading="updating"
          @add="handleAddEndpointOverride"
          @update="handleUpdateEndpointOverride"
          @remove="handleRemoveEndpointOverride"
        />
      </section>

      <!-- Change History -->
      <section class="settings-section">
        <FlagChangeHistory
          v-if="featureFlagsStatus"
          :history="featureFlagsStatus.history"
          :loading="loading"
        />
      </section>

      <!-- Access Metrics -->
      <section class="settings-section">
        <AccessMetrics
          v-if="accessMetrics"
          :metrics="accessMetrics"
          :loading="loadingMetrics"
          @refresh="handleRefreshMetrics"
          @view-endpoint="handleViewEndpoint"
          @view-user="handleViewUser"
        />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { useNotificationBus } from '@/composables/useNotificationBus';
import featureFlagsApiClient, {
  type EnforcementMode,
  type FeatureFlagsStatus,
  type ViolationStatistics,
} from '@/utils/FeatureFlagsApiClient';
import EnforcementModeSelector from '@/components/feature-flags/EnforcementModeSelector.vue';
import EndpointEnforcement from '@/components/feature-flags/EndpointEnforcement.vue';
import FlagChangeHistory from '@/components/feature-flags/FlagChangeHistory.vue';
import AccessMetrics from '@/components/feature-flags/AccessMetrics.vue';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import Icon from '@/components/ui/Icon.vue';
import BaseAlert from '@/components/ui/BaseAlert.vue';

const logger = createLogger('FeatureFlagsSettingsPanel');
const { t } = useI18n();
const { showToast } = useNotificationBus();

// State
const loading = ref(false);
const updating = ref(false);
const loadingMetrics = ref(false);
const error = ref('');
const operationError = ref<string | null>(null);
const featureFlagsStatus = ref<FeatureFlagsStatus | null>(null);
const accessMetrics = ref<ViolationStatistics | null>(null);

// Load all data
const loadData = async () => {
  loading.value = true;
  error.value = '';

  try {
    const [statusResponse, metricsResponse] = await Promise.all([
      featureFlagsApiClient.getFeatureFlagsStatus(),
      featureFlagsApiClient.getAccessControlMetrics({ days: 7, include_details: true }),
    ]);

    if (!statusResponse.success || !statusResponse.data) {
      throw new Error(statusResponse.error || t('featureFlags.failedToLoadStatus'));
    }

    featureFlagsStatus.value = statusResponse.data;

    if (metricsResponse.success && metricsResponse.data) {
      accessMetrics.value = metricsResponse.data;
    }
  } catch (err) {
    logger.error('Failed to load feature flags data:', err);
    error.value = err instanceof Error ? err.message : t('featureFlags.loadError');
  } finally {
    loading.value = false;
  }
};

// Handle enforcement mode change
const handleModeChange = async (mode: EnforcementMode) => {
  updating.value = true;

  try {
    const response = await featureFlagsApiClient.updateEnforcementMode(mode);

    if (!response.success) {
      throw new Error(response.error || t('featureFlags.failedToUpdateMode'));
    }

    if (featureFlagsStatus.value) {
      featureFlagsStatus.value.current_mode = mode;
    }

    showToast(t('featureFlags.modeUpdatedSuccess'), 'success', 3000);
    operationError.value = null;

    // Reload data to reflect changes
    await loadData();
  } catch (err) {
    logger.error('Failed to update enforcement mode:', err);
    operationError.value = err instanceof Error ? err.message : t('featureFlags.updateModeError');
  } finally {
    updating.value = false;
  }
};

// Handle endpoint override addition
const handleAddEndpointOverride = async (endpoint: string, mode: EnforcementMode) => {
  updating.value = true;

  try {
    const response = await featureFlagsApiClient.setEndpointEnforcement(endpoint, mode);

    if (!response.success) {
      throw new Error(response.error || t('featureFlags.failedToAddOverride'));
    }

    if (featureFlagsStatus.value) {
      featureFlagsStatus.value.endpoint_overrides[endpoint] = mode;
    }

    showToast(t('featureFlags.overrideAddedSuccess'), 'success', 3000);
    operationError.value = null;
  } catch (err) {
    logger.error('Failed to add endpoint override:', err);
    operationError.value = err instanceof Error ? err.message : t('featureFlags.addOverrideError');
  } finally {
    updating.value = false;
  }
};

// Handle endpoint override update
const handleUpdateEndpointOverride = async (endpoint: string, mode: EnforcementMode) => {
  updating.value = true;

  try {
    const response = await featureFlagsApiClient.setEndpointEnforcement(endpoint, mode);

    if (!response.success) {
      throw new Error(response.error || t('featureFlags.failedToUpdateOverride'));
    }

    if (featureFlagsStatus.value) {
      featureFlagsStatus.value.endpoint_overrides[endpoint] = mode;
    }

    showToast(t('featureFlags.overrideUpdatedSuccess'), 'success', 3000);
    operationError.value = null;
  } catch (err) {
    logger.error('Failed to update endpoint override:', err);
    operationError.value = err instanceof Error ? err.message : t('featureFlags.updateOverrideError');
  } finally {
    updating.value = false;
  }
};

// Handle endpoint override removal
const handleRemoveEndpointOverride = async (endpoint: string) => {
  updating.value = true;

  try {
    const response = await featureFlagsApiClient.removeEndpointEnforcement(endpoint);

    if (!response.success) {
      throw new Error(response.error || t('featureFlags.failedToRemoveOverride'));
    }

    if (featureFlagsStatus.value) {
      delete featureFlagsStatus.value.endpoint_overrides[endpoint];
    }

    showToast(t('featureFlags.overrideRemovedSuccess'), 'success', 3000);
    operationError.value = null;
  } catch (err) {
    logger.error('Failed to remove endpoint override:', err);
    operationError.value = err instanceof Error ? err.message : t('featureFlags.removeOverrideError');
  } finally {
    updating.value = false;
  }
};

// Handle metrics refresh
const handleRefreshMetrics = async (days?: number) => {
  loadingMetrics.value = true;

  try {
    const response = await featureFlagsApiClient.getAccessControlMetrics({
      days: days || 7,
      include_details: true,
    });

    if (!response.success) {
      throw new Error(response.error || t('featureFlags.failedToLoadMetrics'));
    }

    accessMetrics.value = response.data || null;
    showToast(t('featureFlags.metricsRefreshed'), 'success', 2000);
    operationError.value = null;
  } catch (err) {
    logger.error('Failed to refresh metrics:', err);
    operationError.value = err instanceof Error ? err.message : t('featureFlags.refreshMetricsError');
  } finally {
    loadingMetrics.value = false;
  }
};

// Handle endpoint view
const handleViewEndpoint = (endpoint: string) => {
  logger.info('Viewing endpoint metrics:', endpoint);
  // This can be extended to show detailed endpoint metrics in a modal or drawer
  showToast(`Viewing metrics for ${endpoint}`, 'info', 2000);
};

// Handle user view
const handleViewUser = (username: string) => {
  logger.info('Viewing user metrics:', username);
  // This can be extended to show detailed user metrics in a modal or drawer
  showToast(`Viewing metrics for ${username}`, 'info', 2000);
};

// Load data on mount
onMounted(() => {
  loadData();
});
</script>

<style scoped>
.feature-flags-settings-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 40px;
  text-align: center;
  color: var(--text-secondary);
}

.loading-state {
  min-height: 200px;
}

.error-state {
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-xl);
  min-height: 200px;
  padding: var(--spacing-10);
}

.error-state i {
  font-size: 32px;
  margin-bottom: var(--spacing-3);
}

.error-state p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4);
  font-size: var(--text-sm);
}

.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--color-error);
  color: var(--text-on-error);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--duration-200);
}

.retry-btn:hover {
  opacity: 0.9;
}

.settings-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

.settings-section {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
