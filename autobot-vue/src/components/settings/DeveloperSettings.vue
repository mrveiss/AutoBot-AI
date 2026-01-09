<template>
  <div v-if="developerSettings && isSettingsLoaded" class="settings-section">
    <div class="developer-section">
      <h3>Developer Mode</h3>
      <div class="setting-item">
        <label for="developer-enabled">Enable Developer Mode</label>
        <input
          id="developer-enabled"
          type="checkbox"
          :checked="developerSettings.enabled"
          @change="handleCheckboxChange('enabled')"
        />
      </div>

      <div v-if="developerSettings.enabled" class="developer-options">
        <div class="setting-item">
          <label for="enhanced-errors">Enhanced Error Messages</label>
          <input
            id="enhanced-errors"
            type="checkbox"
            :checked="developerSettings.enhanced_errors"
            @change="handleCheckboxChange('enhanced_errors')"
          />
        </div>
        <div class="setting-item">
          <label for="endpoint-suggestions">API Endpoint Suggestions</label>
          <input
            id="endpoint-suggestions"
            type="checkbox"
            :checked="developerSettings.endpoint_suggestions"
            @change="handleCheckboxChange('endpoint_suggestions')"
          />
        </div>
        <div class="setting-item">
          <label for="debug-logging">Debug Logging</label>
          <input
            id="debug-logging"
            type="checkbox"
            :checked="developerSettings.debug_logging"
            @change="handleCheckboxChange('debug_logging')"
          />
        </div>

        <!-- RUM (Real User Monitoring) Settings -->
        <div class="rum-settings">
          <h4>Real User Monitoring (RUM)</h4>
          <div class="setting-item">
            <label for="rum-enabled" class="with-description">
              Enable RUM Agent
              <span class="description">Monitor user interactions, performance metrics, and errors in real-time</span>
            </label>
            <input
              id="rum-enabled"
              type="checkbox"
              :checked="rumSettings?.enabled || false"
              @change="handleRUMCheckboxChange('enabled')"
            />
          </div>

          <div v-if="rumSettings?.enabled" class="rum-config">
            <div class="setting-item">
              <label for="error-tracking" class="with-description">
                Error Tracking
                <span class="description">Capture JavaScript errors and exceptions</span>
              </label>
              <input
                id="error-tracking"
                type="checkbox"
                :checked="rumSettings.error_tracking || false"
                @change="handleRUMCheckboxChange('error_tracking')"
              />
            </div>
            <div class="setting-item">
              <label for="performance-monitoring" class="with-description">
                Performance Monitoring
                <span class="description">Track page load times, API calls, and resource loading</span>
              </label>
              <input
                id="performance-monitoring"
                type="checkbox"
                :checked="rumSettings.performance_monitoring || false"
                @change="handleRUMCheckboxChange('performance_monitoring')"
              />
            </div>
            <div class="setting-item">
              <label for="interaction-tracking" class="with-description">
                User Interaction Tracking
                <span class="description">Monitor clicks, form submissions, and navigation</span>
              </label>
              <input
                id="interaction-tracking"
                type="checkbox"
                :checked="rumSettings.interaction_tracking || false"
                @change="handleRUMCheckboxChange('interaction_tracking')"
              />
            </div>
            <div class="setting-item">
              <label for="session-recording" class="with-description">
                Session Recording
                <span class="description">Record user sessions for debugging (privacy-aware)</span>
              </label>
              <input
                id="session-recording"
                type="checkbox"
                :checked="rumSettings.session_recording || false"
                @change="handleRUMCheckboxChange('session_recording')"
              />
            </div>
            <div class="setting-item">
              <label for="sample-rate">Sample Rate (%)</label>
              <input
                id="sample-rate"
                type="number"
                :value="rumSettings.sample_rate || 100"
                min="0"
                max="100"
                step="1"
                @input="handleRUMIntegerInputChange('sample_rate')"
              />
            </div>
            <div class="setting-item">
              <label for="max-events">Max Events per Session</label>
              <input
                id="max-events"
                type="number"
                :value="rumSettings.max_events_per_session || 1000"
                min="100"
                max="10000"
                step="100"
                @input="handleRUMIntegerInputChange('max_events_per_session')"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface RUMSettings {
  enabled: boolean
  error_tracking: boolean
  performance_monitoring: boolean
  interaction_tracking: boolean
  session_recording: boolean
  sample_rate: number
  max_events_per_session: number
}

interface DeveloperSettings {
  enabled: boolean
  enhanced_errors: boolean
  endpoint_suggestions: boolean
  debug_logging: boolean
  rum: RUMSettings
}

interface Props {
  developerSettings: DeveloperSettings | null
  isSettingsLoaded: boolean
}

interface Emits {
  (e: 'setting-changed', key: string, value: any): void
  (e: 'rum-setting-changed', key: string, value: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const rumSettings = computed(() => props.developerSettings?.rum)

const updateSetting = (key: string, value: any) => {
  emit('setting-changed', key, value)
}

const updateRUMSetting = (key: string, value: any) => {
  emit('rum-setting-changed', key, value)
}

// Typed event handlers for developer settings
const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.checked)
}

const handleInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, target.value)
}

const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateSetting(key, parseInt(target.value))
}

// Typed event handlers for RUM settings
const handleRUMCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateRUMSetting(key, target.checked)
}

const handleRUMNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateRUMSetting(key, parseFloat(target.value))
}

const handleRUMIntegerInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateRUMSetting(key, parseInt(target.value))
}
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */

.settings-section {
  margin-bottom: var(--spacing-8);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.developer-section h3 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: var(--text-lg);
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: var(--spacing-2);
}

.developer-options {
  margin-top: var(--spacing-5);
  padding-top: var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  flex: 1;
  margin-right: var(--spacing-4);
  cursor: pointer;
}

.setting-item label.with-description {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.setting-item label .description {
  font-size: var(--text-xs);
  font-weight: var(--font-normal);
  color: var(--text-secondary);
  font-style: italic;
}

.setting-item input {
  min-width: 150px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  transition: border-color var(--duration-200) ease;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.setting-item input:invalid {
  border-color: var(--color-error);
  box-shadow: 0 0 0 2px var(--color-error-alpha-20);
}

.rum-settings {
  margin-top: var(--spacing-8);
  padding-top: var(--spacing-5);
  border-top: 2px solid var(--color-info);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.rum-settings h4 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--color-info);
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.rum-settings h4::before {
  content: "📊";
  font-size: var(--text-lg);
}

.rum-config {
  margin-top: var(--spacing-5);
  padding-left: var(--spacing-5);
  border-left: 3px solid var(--color-info);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
}

.rum-config .setting-item {
  border-bottom-color: var(--border-subtle);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: var(--spacing-4);
    margin-bottom: var(--spacing-5);
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-2);
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: var(--spacing-1);
  }

  .setting-item input {
    min-width: auto;
    width: 100%;
  }

  .setting-item input[type="checkbox"] {
    width: 20px;
    align-self: flex-start;
  }

  .rum-config {
    padding-left: var(--spacing-3);
  }
}
</style>