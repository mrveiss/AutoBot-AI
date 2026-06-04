<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

WebResearchSettingsPanel.vue - Web Research Settings
Issue #3850: web research settings UI missing
-->

<template>
  <form class="web-research-panel" @submit.prevent>
    <div class="panel-header">
      <h3 class="panel-title">
        <Icon name="search" />
        {{ t('settings.webResearch.title') }}
      </h3>
    </div>

    <div class="panel-content">

      <!-- Enable / disable -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="check" />
          {{ t('settings.webResearch.enabledLabel') }}
        </legend>
        <label class="toggle-row">
          <span class="toggle-description">{{ t('settings.webResearch.enabledHint') }}</span>
          <button
            type="button"
            role="switch"
            :aria-checked="settings.enabled"
            class="toggle-btn"
            :class="{ active: settings.enabled }"
            @click="patch({ enabled: !settings.enabled })"
          >
            <span class="toggle-thumb"></span>
          </button>
        </label>
      </fieldset>

      <!-- Require user confirmation -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="user" />
          {{ t('settings.webResearch.confirmationLabel') }}
        </legend>
        <label class="toggle-row">
          <span class="toggle-description">{{ t('settings.webResearch.confirmationHint') }}</span>
          <button
            type="button"
            role="switch"
            :aria-checked="settings.require_user_confirmation"
            class="toggle-btn"
            :class="{ active: settings.require_user_confirmation }"
            @click="patch({ require_user_confirmation: !settings.require_user_confirmation })"
          >
            <span class="toggle-thumb"></span>
          </button>
        </label>
      </fieldset>

      <!-- Preferred method -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="sliders-h" />
          {{ t('settings.webResearch.methodLabel') }}
        </legend>
        <p class="preference-hint">{{ t('settings.webResearch.methodHint') }}</p>
        <div class="select-wrapper">
          <select
            :value="settings.preferred_method"
            @change="patch({ preferred_method: ($event.target as HTMLSelectElement).value as 'basic' | 'advanced' | 'api_based' })"
            class="preference-select"
            :aria-label="t('settings.webResearch.methodLabel')"
          >
            <option value="basic">{{ t('settings.webResearch.methodBasic') }}</option>
            <option value="advanced">{{ t('settings.webResearch.methodAdvanced') }}</option>
            <option value="api_based">{{ t('settings.webResearch.methodApiBased') }}</option>
          </select>
          <Icon name="chevron-down" class="select-icon" />
        </div>
      </fieldset>

      <!-- Max results -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="list-ol" />
          {{ t('settings.webResearch.maxResultsLabel') }}
        </legend>
        <p class="preference-hint">{{ t('settings.webResearch.maxResultsHint') }}</p>
        <input
          type="number"
          :value="settings.max_results"
          @change="patch({ max_results: clamp(+($event.target as HTMLInputElement).value, 1, 50) })"
          min="1" max="50"
          class="number-input"
          :aria-label="t('settings.webResearch.maxResultsLabel')"
        />
      </fieldset>

      <!-- Timeout -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="clock" />
          {{ t('settings.webResearch.timeoutLabel') }}
        </legend>
        <p class="preference-hint">{{ t('settings.webResearch.timeoutHint') }}</p>
        <input
          type="number"
          :value="settings.timeout_seconds"
          @change="patch({ timeout_seconds: clamp(+($event.target as HTMLInputElement).value, 5, 120) })"
          min="5" max="120"
          class="number-input"
          :aria-label="t('settings.webResearch.timeoutLabel')"
        />
      </fieldset>

      <!-- Auto-research threshold -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="robot" />
          {{ t('settings.webResearch.thresholdLabel') }}
        </legend>
        <p class="preference-hint">{{ t('settings.webResearch.thresholdHint') }}</p>
        <div class="slider-row">
          <input
            type="range"
            :value="settings.auto_research_threshold"
            @input="patch({ auto_research_threshold: +($event.target as HTMLInputElement).value })"
            min="0" max="1" step="0.05"
            class="range-input"
            :aria-label="t('settings.webResearch.thresholdLabel')"
          />
          <span class="range-value">{{ (settings.auto_research_threshold * 100).toFixed(0) }}%</span>
        </div>
      </fieldset>

      <!-- Rate limiting -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="tachometer-alt" />
          {{ t('settings.webResearch.rateLimitLabel') }}
        </legend>
        <p class="preference-hint">{{ t('settings.webResearch.rateLimitHint') }}</p>
        <div class="inline-inputs">
          <label class="inline-label">
            {{ t('settings.webResearch.rateLimitRequests') }}
            <input
              type="number"
              :value="settings.rate_limit_requests"
              @change="patch({ rate_limit_requests: clamp(+($event.target as HTMLInputElement).value, 1, 100) })"
              min="1" max="100"
              class="number-input number-input--small"
            />
          </label>
          <label class="inline-label">
            {{ t('settings.webResearch.rateLimitWindow') }}
            <input
              type="number"
              :value="settings.rate_limit_window"
              @change="patch({ rate_limit_window: clamp(+($event.target as HTMLInputElement).value, 10, 3600) })"
              min="10" max="3600"
              class="number-input number-input--small"
            />
          </label>
        </div>
      </fieldset>

      <!-- Privacy & storage toggles -->
      <fieldset class="preference-section">
        <legend class="preference-label">
          <Icon name="shield-alt" />
          {{ t('settings.webResearch.privacyLabel') }}
        </legend>

        <label class="toggle-row">
          <span class="toggle-description">{{ t('settings.webResearch.storeInKbHint') }}</span>
          <button
            type="button"
            role="switch"
            :aria-checked="settings.store_results_in_kb"
            class="toggle-btn"
            :class="{ active: settings.store_results_in_kb }"
            @click="patch({ store_results_in_kb: !settings.store_results_in_kb })"
          >
            <span class="toggle-thumb"></span>
          </button>
        </label>

        <label class="toggle-row">
          <span class="toggle-description">{{ t('settings.webResearch.anonymizeHint') }}</span>
          <button
            type="button"
            role="switch"
            :aria-checked="settings.anonymize_requests"
            class="toggle-btn"
            :class="{ active: settings.anonymize_requests }"
            @click="patch({ anonymize_requests: !settings.anonymize_requests })"
          >
            <span class="toggle-thumb"></span>
          </button>
        </label>

        <label class="toggle-row">
          <span class="toggle-description">{{ t('settings.webResearch.filterAdultHint') }}</span>
          <button
            type="button"
            role="switch"
            :aria-checked="settings.filter_adult_content"
            class="toggle-btn"
            :class="{ active: settings.filter_adult_content }"
            @click="patch({ filter_adult_content: !settings.filter_adult_content })"
          >
            <span class="toggle-thumb"></span>
          </button>
        </label>
      </fieldset>

      <!-- Reset -->
      <div class="panel-actions">
        <button type="button" class="reset-btn" @click="store.resetSettings()">
          <Icon name="undo" />
          {{ t('settings.reset') }}
        </button>
      </div>

    </div>
  </form>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWebResearchStore } from '@/stores/useWebResearchStore'
import type { WebResearchSettings } from '@/stores/useWebResearchStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('WebResearchSettingsPanel')
const { t } = useI18n()
const store = useWebResearchStore()
const settings = computed(() => store.settings)

function patch(partial: Partial<WebResearchSettings>): void {
  store.updateSettings(partial)
  logger.debug('Web research settings updated', partial)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}
</script>

<style scoped>
.web-research-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
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
  gap: var(--spacing-xl);
}

.preference-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  border: none;
  padding: var(--spacing-0);
  margin: var(--spacing-0);
}

.preference-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preference-label i {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.preference-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: var(--leading-normal);
}

/* Toggle */
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) 0;
}

.toggle-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  flex: 1;
}

.toggle-btn {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: var(--radius-xl);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-out), border-color var(--duration-200) var(--ease-out);
  flex-shrink: 0;
}

.toggle-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: white;
  transition: transform var(--duration-200) var(--ease-out);
  pointer-events: none;
}

.toggle-btn.active .toggle-thumb {
  transform: translateX(20px);
}

/* Select */
.select-wrapper {
  position: relative;
  max-width: 280px;
}

.preference-select {
  width: 100%;
  min-height: 40px;
  padding: var(--spacing-sm) var(--spacing-xl) var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  appearance: none;
  transition: border-color var(--transition-fast);
}

.preference-select:hover {
  border-color: var(--color-primary);
}

.preference-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.select-icon {
  position: absolute;
  right: var(--spacing-md);
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  font-size: var(--font-size-xs);
  pointer-events: none;
}

/* Number input */
.number-input {
  width: 100px;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  transition: border-color var(--transition-fast);
}

.number-input:hover {
  border-color: var(--color-primary);
}

.number-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.number-input--small {
  width: 80px;
}

/* Range slider */
.slider-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  max-width: 320px;
}

.range-input {
  flex: 1;
  accent-color: var(--color-primary);
  cursor: pointer;
}

.range-value {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

/* Inline inputs */
.inline-inputs {
  display: flex;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
}

.inline-label {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* Actions */
.panel-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-color);
}

.reset-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.reset-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

@media (max-width: 768px) {
  .panel-content {
    padding: var(--spacing-md);
  }
}
</style>
