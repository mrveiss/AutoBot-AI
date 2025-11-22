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
.settings-section {
  margin-bottom: 30px;
  background: #ffffff;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.developer-section h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid #3498db;
  padding-bottom: 8px;
}

.developer-options {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: #34495e;
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item label.with-description {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.setting-item label .description {
  font-size: 12px;
  font-weight: 400;
  color: #6c757d;
  font-style: italic;
}

.setting-item input {
  min-width: 150px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: #007acc;
}

.setting-item input:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.setting-item input:invalid {
  border-color: #e74c3c;
  box-shadow: 0 0 0 2px rgba(231, 76, 60, 0.2);
}

.rum-settings {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 2px solid #17a2b8;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
}

.rum-settings h4 {
  margin: 0 0 20px 0;
  color: #17a2b8;
  font-weight: 600;
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.rum-settings h4::before {
  content: "📊";
  font-size: 18px;
}

.rum-config {
  margin-top: 20px;
  padding-left: 20px;
  border-left: 3px solid #17a2b8;
  background: #ffffff;
  border-radius: 6px;
  padding: 16px;
}

.rum-config .setting-item {
  border-bottom-color: #e9ecef;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-section {
    background: #2d2d2d;
    border-color: #404040;
  }

  .developer-section h3 {
    color: #ffffff;
    border-bottom-color: #4fc3f7;
  }

  .developer-options {
    border-top-color: #404040;
  }

  .setting-item {
    border-bottom-color: #404040;
  }

  .setting-item label {
    color: #e0e0e0;
  }

  .setting-item label .description {
    color: #aaaaaa;
  }

  .setting-item input {
    background: #404040;
    border-color: #555;
    color: #ffffff;
  }

  .setting-item input:focus {
    border-color: #4fc3f7;
    box-shadow: 0 0 0 2px rgba(79, 195, 247, 0.2);
  }

  .rum-settings {
    background: #383838;
    border-top-color: #4fc3f7;
  }

  .rum-settings h4 {
    color: #4fc3f7;
  }

  .rum-config {
    background: #2d2d2d;
    border-left-color: #4fc3f7;
  }

  .rum-config .setting-item {
    border-bottom-color: #404040;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: 16px;
    margin-bottom: 20px;
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: 4px;
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
    padding-left: 12px;
  }
}
</style>