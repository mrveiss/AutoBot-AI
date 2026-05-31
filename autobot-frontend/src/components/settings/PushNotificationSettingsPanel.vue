<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

PushNotificationSettingsPanel.vue — per-device web push notification toggle
Issue GH#4459: Web push notifications for async task completion
-->

<template>
  <div class="push-notification-settings-panel">
    <!-- Browser not supported -->
    <div v-if="!isSupported" class="unsupported-state">
      <Icon name="bell-slash" />
      <p>Push notifications are not supported in this browser.</p>
      <p class="hint">Try Chrome, Edge, or Firefox on desktop.</p>
    </div>

    <!-- Supported -->
    <template v-else>
      <!-- Error banner -->
      <div v-if="error" class="error-banner" role="alert">
        <Icon name="exclamation-triangle" />
        <span>{{ error }}</span>
        <button class="dismiss-btn" @click="clearError" aria-label="Dismiss error">
          <Icon name="times" />
        </button>
      </div>

      <!-- Permission denied warning -->
      <div v-if="permissionState === 'denied'" class="permission-denied-banner">
        <Icon name="ban" />
        <span>
          Notifications are blocked. Enable them in your browser's site settings, then reload this
          page.
        </span>
      </div>

      <!-- Main toggle row -->
      <div class="toggle-row">
        <div class="toggle-info">
          <span class="toggle-label">Browser push notifications</span>
          <span class="toggle-description">
            Receive notifications when background tasks complete — even when AutoBot is not the
            active tab.
          </span>
        </div>

        <button
          :class="['toggle-btn', { active: subscribed, loading: loading }]"
          :disabled="loading || permissionState === 'denied'"
          :aria-pressed="subscribed"
          :aria-label="subscribed ? 'Disable push notifications' : 'Enable push notifications'"
          @click="handleToggle"
        >
          <span class="toggle-track">
            <span class="toggle-thumb" />
          </span>
          <span class="toggle-text">
            <template v-if="loading">
              <Icon name="spinner" class="spin" />
              {{ subscribed ? 'Disabling…' : 'Enabling…' }}
            </template>
            <template v-else>
              {{ subscribed ? 'On' : 'Off' }}
            </template>
          </span>
        </button>
      </div>

      <!-- Status line -->
      <p class="status-line">
        <template v-if="subscribed">
          <Icon name="check-circle" class="status-icon ok" />
          Notifications are active on this device.
        </template>
        <template v-else-if="permissionState === 'granted'">
          <Icon name="info-circle" class="status-icon info" />
          Permission granted — toggle on to receive notifications.
        </template>
        <template v-else-if="permissionState === 'default'">
          <Icon name="info-circle" class="status-icon info" />
          Toggle on to be asked for notification permission.
        </template>
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { usePushNotifications } from '@/composables/usePushNotifications'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('PushNotificationSettingsPanel')

const { subscribed, permissionState, loading, error: pushError, isSupported, subscribe, unsubscribe } =
  usePushNotifications()

// Re-expose error as writable ref for dismiss button
import { ref, watch } from 'vue'
const error = ref<string | null>(null)
watch(pushError, (v: string | null) => (error.value = v))

function clearError() {
  error.value = null
}

async function handleToggle() {
  logger.info('Push toggle clicked, subscribed=', subscribed.value)
  if (subscribed.value) {
    await unsubscribe()
  } else {
    await subscribe()
  }
}
</script>

<style scoped>
.push-notification-settings-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.unsupported-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-10);
  color: var(--text-secondary);
  text-align: center;
}

.unsupported-state .hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.error-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.error-banner .dismiss-btn {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  padding: 0;
  line-height: 1;
}

.permission-denied-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

.toggle-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.toggle-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.toggle-description {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  max-width: 420px;
  line-height: 1.5;
}

/* Toggle button */
.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: none;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--duration-200);
  white-space: nowrap;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.toggle-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-on-primary, #fff);
}

.toggle-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-btn.loading {
  opacity: 0.7;
}

.toggle-track {
  display: inline-flex;
  width: 32px;
  height: 18px;
  background: var(--border-color);
  border-radius: var(--radius-full);
  padding: 2px;
  transition: background var(--duration-200);
}

.toggle-btn.active .toggle-track {
  background: rgba(255, 255, 255, 0.4);
}

.toggle-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--text-secondary);
  transition: transform var(--duration-200), background var(--duration-200);
}

.toggle-btn.active .toggle-thumb {
  transform: translateX(14px);
  background: #fff;
}

.toggle-text {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  min-width: 56px;
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.status-line {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  padding: 0 var(--spacing-1);
}

.status-icon {
  flex-shrink: 0;
}

.status-icon.ok {
  color: var(--color-success);
}

.status-icon.info {
  color: var(--color-info, var(--color-primary));
}
</style>
