<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

TelemetrySettingsPanel.vue - Local Usage Metrics Settings
Issue #9035: Operator-controlled local usage metrics (never transmitted)
-->

<template>
  <form class="telemetry-panel" @submit.prevent>
    <div class="panel-header">
      <h3 class="panel-title">
        <Icon name="shield-alt" aria-hidden="true" />
        {{ t('settings.telemetry.title') }}
      </h3>
    </div>

    <div class="panel-content">
      <!-- Telemetry Toggle -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="chart-line" aria-hidden="true" />
          {{ t('settings.telemetry.recordLabel') }}
        </legend>
        <p class="preference-hint">
          {{ t('settings.telemetry.recordHint') }}
        </p>
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input
              type="checkbox"
              v-model="telemetryEnabled"
              @change="handleTelemetryToggle"
              :aria-label="t('settings.telemetry.toggleAriaLabel')"
            />
            <span class="toggle-slider"></span>
          </label>
          <span class="toggle-label">
            {{ telemetryEnabled ? t('settings.telemetry.enabled') : t('settings.telemetry.disabled') }}
          </span>
        </div>
      </fieldset>

      <!-- What Data is Collected -->
      <div class="info-section">
        <details class="data-disclosure">
          <summary class="disclosure-summary">
            <Icon name="info-circle" aria-hidden="true" />
            {{ t('settings.telemetry.disclosureSummary') }}
          </summary>
          <div class="disclosure-content">
            <h4>{{ t('settings.telemetry.recordedTitle') }}</h4>
            <ul>
              <li><strong>{{ t('settings.telemetry.recordedApiLabel') }}</strong> {{ t('settings.telemetry.recordedApi') }}</li>
              <li><strong>{{ t('settings.telemetry.recordedVoiceLabel') }}</strong> {{ t('settings.telemetry.recordedVoice') }}</li>
              <li><strong>{{ t('settings.telemetry.recordedFeatureLabel') }}</strong> {{ t('settings.telemetry.recordedFeature') }}</li>
            </ul>
            <h4>{{ t('settings.telemetry.neverRecordedTitle') }}</h4>
            <ul>
              <li>{{ t('settings.telemetry.neverPersonal') }}</li>
              <li>{{ t('settings.telemetry.neverContent') }}</li>
              <li>{{ t('settings.telemetry.neverPaths') }}</li>
            </ul>
            <p class="disclosure-note">
              {{ t('settings.telemetry.disclosureNote') }}
            </p>
          </div>
        </details>
      </div>
    </div>

    <!-- Screen reader announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ announcement }}
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('TelemetrySettingsPanel')
const { t } = useI18n()
const api = useApiClient()
const { showToast } = useNotificationBus()

const telemetryEnabled = ref(true)
const announcement = ref('')

onMounted(async () => {
  await loadTelemetrySettings()
})

async function loadTelemetrySettings() {
  try {
    const response = await api.get<{
      enabled: boolean
      anonymous_usage_stats: boolean
      first_run_prompt_shown: boolean
    }>('/api/settings/telemetry')

    telemetryEnabled.value = response.enabled
    logger.debug('Loaded telemetry settings', response)
  } catch (error) {
    logger.error('Failed to load telemetry settings', error)
    showToast(t('settings.telemetry.loadFailed'), 'error')
  }
}

async function handleTelemetryToggle() {
  try {
    await api.post('/api/settings/telemetry', {
      enabled: telemetryEnabled.value,
      anonymous_usage_stats: telemetryEnabled.value,
      first_run_prompt_shown: true,
    })

    const message = telemetryEnabled.value
      ? t('settings.telemetry.enabledMessage')
      : t('settings.telemetry.disabledMessage')

    showToast(message, 'success')
    announceChange(message)
    logger.debug(`Telemetry ${telemetryEnabled.value ? 'enabled' : 'disabled'}`)
  } catch (error) {
    logger.error('Failed to update telemetry settings', error)
    showToast(t('settings.telemetry.updateFailed'), 'error')

    // Revert toggle on error
    telemetryEnabled.value = !telemetryEnabled.value
  }
}

function announceChange(message: string): void {
  announcement.value = message
  setTimeout(() => {
    announcement.value = ''
  }, 1000)
}
</script>

<style scoped>
.telemetry-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: var(--spacing-0);
  margin: var(--spacing-neg-px);
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.panel-title i {
  color: var(--color-primary);
}

.panel-content {
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.preference-section {
  border: none;
  padding: var(--spacing-0);
  margin: var(--spacing-0);
}

.preference-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.preference-label i {
  color: var(--color-primary);
}

.preference-hint {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  margin-bottom: var(--spacing-md);
  line-height: 1.5;
}

.toggle-wrapper {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 26px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--bg-tertiary);
  transition: 0.3s;
  border-radius: 26px;
  border: 1px solid var(--border-color);
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

input:checked + .toggle-slider {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

input:checked + .toggle-slider:before {
  transform: translateX(24px);
}

.toggle-label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.info-section {
  margin-top: var(--spacing-md);
}

.data-disclosure {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  background: var(--bg-tertiary);
}

.disclosure-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  list-style: none;
}

.disclosure-summary::-webkit-details-marker {
  display: none;
}

.disclosure-summary i {
  color: var(--color-info);
}

.disclosure-content {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color);
}

.disclosure-content h4 {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-md) 0 var(--spacing-sm) 0;
}

.disclosure-content ul {
  margin: var(--spacing-sm) 0;
  padding-left: var(--spacing-lg);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.disclosure-content li {
  margin-bottom: var(--spacing-xs);
}

.disclosure-note {
  margin-top: var(--spacing-md);
  padding: var(--spacing-sm);
  background: var(--bg-secondary);
  border-left: 3px solid var(--color-info);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
}
</style>
