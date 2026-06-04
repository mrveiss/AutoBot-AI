<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

TelemetrySettingsPanel.vue - Telemetry and Usage Data Collection Settings
-->

<template>
  <div class="telemetry-settings-panel">
    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <LoadingSpinner />
      <p>Loading telemetry settings...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <BaseAlert variant="error" :message="error">
        <template #actions>
          <button @click="loadSettings" class="retry-btn">
            <Icon name="redo" />
            Retry
          </button>
        </template>
      </BaseAlert>
    </div>

    <!-- Main Content -->
    <div v-else class="settings-content">
      <!-- Operation Success -->
      <BaseAlert
        v-if="successMessage"
        variant="success"
        :message="successMessage"
        dismissible
        @dismiss="successMessage = null"
      />

      <!-- Operation Error -->
      <BaseAlert
        v-if="operationError"
        variant="error"
        :message="operationError"
        dismissible
        @dismiss="operationError = null"
      />

      <!-- Telemetry Settings -->
      <section class="settings-section">
        <h3 class="section-title">Usage Data Collection</h3>
        <p class="section-description">
          Control what data AutoBot collects to improve the platform and provide better support.
        </p>

        <div class="setting-row">
          <div class="setting-label">
            <strong>Anonymous Usage Statistics</strong>
            <p class="setting-hint">
              Collect anonymous usage data to help us understand how AutoBot is used and prioritize improvements.
            </p>
          </div>
          <div class="setting-control">
            <label class="toggle-switch">
              <input
                v-model="settings.collectUsageStats"
                type="checkbox"
                @change="handleSettingChange"
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="setting-label">
            <strong>Error Reports</strong>
            <p class="setting-hint">
              Automatically send error reports to help us identify and fix bugs faster.
            </p>
          </div>
          <div class="setting-control">
            <label class="toggle-switch">
              <input
                v-model="settings.collectErrorReports"
                type="checkbox"
                @change="handleSettingChange"
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="setting-label">
            <strong>Performance Metrics</strong>
            <p class="setting-hint">
              Collect performance data to help optimize AutoBot's speed and resource usage.
            </p>
          </div>
          <div class="setting-control">
            <label class="toggle-switch">
              <input
                v-model="settings.collectPerformanceMetrics"
                type="checkbox"
                @change="handleSettingChange"
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </section>

      <!-- Privacy Notice -->
      <section class="settings-section">
        <h3 class="section-title">Privacy</h3>
        <div class="privacy-notice">
          <Icon name="shield-check" />
          <p>
            Your privacy is important to us. All telemetry data is anonymized and used solely to improve AutoBot.
            We never sell or share your data with third parties. You can disable telemetry at any time.
          </p>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useNotificationBus } from '@/composables/useNotificationBus';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseAlert from '@/components/ui/BaseAlert.vue';
import Icon from '@/components/ui/Icon.vue';

const logger = createLogger('TelemetrySettingsPanel');
const { notifyError, notifySuccess } = useNotificationBus();

// State
const loading = ref(false);
const error = ref<string | null>(null);
const operationError = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const settings = ref({
  collectUsageStats: true,
  collectErrorReports: true,
  collectPerformanceMetrics: true,
});

// Methods
async function loadSettings() {
  loading.value = true;
  error.value = null;

  try {
    // TODO: Implement actual API call when telemetry backend is ready
    // For now, use localStorage
    const stored = localStorage.getItem('autobot_telemetry_settings');
    if (stored) {
      settings.value = JSON.parse(stored);
    }
    logger.info('Telemetry settings loaded', settings.value);
  } catch (err) {
    error.value = 'Failed to load telemetry settings';
    logger.error('Failed to load telemetry settings', err);
  } finally {
    loading.value = false;
  }
}

async function handleSettingChange() {
  operationError.value = null;
  successMessage.value = null;

  try {
    // TODO: Implement actual API call when telemetry backend is ready
    // For now, use localStorage
    localStorage.setItem('autobot_telemetry_settings', JSON.stringify(settings.value));

    successMessage.value = 'Telemetry settings updated';
    logger.info('Telemetry settings updated', settings.value);
    notifySuccess('Telemetry settings updated');
  } catch (err) {
    operationError.value = 'Failed to update telemetry settings';
    logger.error('Failed to update telemetry settings', err);
    notifyError('Failed to update telemetry settings');
  }
}

// Lifecycle
onMounted(() => {
  loadSettings();
});
</script>

<style scoped>
.telemetry-settings-panel {
  padding: 0;
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  text-align: center;
  gap: 1rem;
}

.retry-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.875rem;
}

.retry-btn:hover {
  background: var(--color-primary-dark);
}

.settings-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.settings-section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  padding: 1.5rem;
}

.section-title {
  margin: 0 0 0.5rem 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-description {
  margin: 0 0 1.5rem 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 1rem 0;
  border-bottom: 1px solid var(--color-border);
}

.setting-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.setting-row:first-child {
  padding-top: 0;
}

.setting-label {
  flex: 1;
  padding-right: 2rem;
}

.setting-label strong {
  display: block;
  margin-bottom: 0.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.setting-hint {
  margin: 0;
  font-size: 0.813rem;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.setting-control {
  flex-shrink: 0;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: var(--color-primary);
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(24px);
}

.toggle-switch input:disabled + .toggle-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--color-border);
  transition: 0.3s;
  border-radius: 24px;
}

.toggle-slider::before {
  position: absolute;
  content: '';
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

.toggle-slider:hover {
  opacity: 0.8;
}

.privacy-notice {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: 0.5rem;
}

.privacy-notice p {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.privacy-notice :deep(.icon) {
  flex-shrink: 0;
  color: var(--color-info);
  width: 1.25rem;
  height: 1.25rem;
}
</style>
