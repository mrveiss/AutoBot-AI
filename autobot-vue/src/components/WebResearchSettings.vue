<template>
  <div class="web-research-settings">
    <h3>Web Research Settings</h3>

    <!-- Status and Main Toggle -->
    <div class="research-status-section">
      <div class="status-indicator" :class="researchStatus.enabled ? 'enabled' : 'disabled'">
        <div class="status-dot"></div>
        <span>{{ researchStatus.enabled ? 'Enabled' : 'Disabled' }}</span>
      </div>

      <div class="main-toggle">
        <label class="toggle-label">
          <span>Enable Web Research</span>
          <input
            type="checkbox"
            v-model="researchSettings.enabled"
            @change="toggleWebResearch"
            :disabled="isUpdating"
          />
          <div class="toggle-slider"></div>
        </label>
        <p class="setting-description">
          Allow AutoBot to search the web for information not available in the knowledge base
        </p>
      </div>
    </div>

    <!-- Research Settings (only show if enabled) -->
    <div v-if="researchSettings.enabled" class="research-configuration">

      <!-- User Confirmation Settings -->
      <div class="setting-group">
        <h4>User Preferences</h4>

        <div class="setting-item">
          <label>
            <input
              type="checkbox"
              v-model="researchSettings.require_user_confirmation"
              @change="updateSettings"
            />
            <span>Ask permission before conducting web research</span>
          </label>
          <p class="setting-hint">
            When enabled, AutoBot will ask for your confirmation before researching online
          </p>
        </div>

        <div class="setting-item">
          <label>Store high-quality research results in knowledge base</label>
          <input
            type="checkbox"
            v-model="researchSettings.store_results_in_kb"
            @change="updateSettings"
          />
          <p class="setting-hint">
            Automatically save valuable research findings to improve future responses
          </p>
        </div>
      </div>

      <!-- Performance Settings -->
      <div class="setting-group">
        <h4>Performance & Limits</h4>

        <div class="setting-item">
          <label>Research Method</label>
          <select
            v-model="researchSettings.preferred_method"
            @change="updateSettings"
            class="method-select"
          >
            <option value="basic">Basic Research (Fast, reliable)</option>
            <option value="advanced">Advanced Research (Slower, more comprehensive)</option>
            <option value="api_based">API-based Research (Fastest)</option>
          </select>
          <p class="setting-hint">
            Choose the balance between speed and comprehensiveness
          </p>
        </div>

        <div class="setting-item">
          <label>Maximum Results per Query</label>
          <input
            type="number"
            v-model="researchSettings.max_results"
            min="1"
            max="10"
            @change="updateSettings"
          />
          <p class="setting-hint">Limit the number of sources to research per query</p>
        </div>

        <div class="setting-item">
          <label>Research Timeout (seconds)</label>
          <input
            type="number"
            v-model="researchSettings.timeout_seconds"
            min="10"
            max="120"
            @change="updateSettings"
          />
          <p class="setting-hint">Maximum time to spend on each research query</p>
        </div>

        <div class="setting-item">
          <label>Auto-research Confidence Threshold</label>
          <input
            type="range"
            v-model="researchSettings.auto_research_threshold"
            min="0"
            max="1"
            step="0.1"
            @change="updateSettings"
          />
          <span class="threshold-value">{{ (researchSettings.auto_research_threshold * 100).toFixed(0) }}%</span>
          <p class="setting-hint">
            Research automatically when knowledge base confidence is below this threshold
          </p>
        </div>
      </div>

      <!-- Rate Limiting -->
      <div class="setting-group">
        <h4>Rate Limiting</h4>

        <div class="setting-item">
          <label>Requests per Window</label>
          <input
            type="number"
            v-model="researchSettings.rate_limit_requests"
            min="1"
            max="20"
            @change="updateSettings"
          />
          <p class="setting-hint">Maximum research requests in the time window</p>
        </div>

        <div class="setting-item">
          <label>Rate Limit Window (seconds)</label>
          <input
            type="number"
            v-model="researchSettings.rate_limit_window"
            min="30"
            max="300"
            @change="updateSettings"
          />
          <p class="setting-hint">Time window for rate limiting</p>
        </div>
      </div>

      <!-- Privacy Settings -->
      <div class="setting-group">
        <h4>Privacy & Safety</h4>

        <div class="setting-item">
          <label>
            <input
              type="checkbox"
              v-model="researchSettings.anonymize_requests"
              @change="updateSettings"
            />
            <span>Anonymize research requests</span>
          </label>
          <p class="setting-hint">Remove identifying information from web requests</p>
        </div>

        <div class="setting-item">
          <label>
            <input
              type="checkbox"
              v-model="researchSettings.filter_adult_content"
              @change="updateSettings"
            />
            <span>Filter adult content</span>
          </label>
          <p class="setting-hint">Exclude adult content from research results</p>
        </div>
      </div>
    </div>

    <!-- Status Information -->
    <div class="research-info" v-if="researchStatus.enabled">
      <h4>Current Status</h4>

      <div class="status-grid">
        <div class="status-item">
          <span class="status-label">Preferred Method:</span>
          <span class="status-value">{{ researchStatus.preferred_method || 'Not set' }}</span>
        </div>

        <div class="status-item" v-if="researchStatus.cache_stats">
          <span class="status-label">Cache Size:</span>
          <span class="status-value">{{ researchStatus.cache_stats.cache_size || 0 }} entries</span>
        </div>

        <div class="status-item" v-if="researchStatus.cache_stats">
          <span class="status-label">Rate Limiter:</span>
          <span class="status-value">
            {{ researchStatus.cache_stats.rate_limiter?.current_requests || 0 }}/{{ researchStatus.cache_stats.rate_limiter?.max_requests || 0 }}
          </span>
        </div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="action-buttons" v-if="researchSettings.enabled">
      <button @click="testWebResearch" :disabled="isUpdating" class="test-button">
        <i class="fas fa-search"></i>
        Test Web Research
      </button>

      <button @click="clearCache" :disabled="isUpdating" class="clear-button">
        <i class="fas fa-trash"></i>
        Clear Cache
      </button>

      <button @click="resetCircuitBreakers" :disabled="isUpdating" class="reset-button">
        <i class="fas fa-refresh"></i>
        Reset Circuit Breakers
      </button>
    </div>

    <!-- Test Results -->
    <div v-if="testResult" class="test-result" :class="testResult.status">
      <h4>Test Result</h4>
      <pre>{{ JSON.stringify(testResult, null, 2) }}</pre>
    </div>

    <!-- Update Status -->
    <div v-if="updateMessage" class="update-message" :class="updateMessage.type">
      <i :class="updateMessage.type === 'success' ? 'fas fa-check' : 'fas fa-exclamation-triangle'"></i>
      {{ updateMessage.text }}
    </div>
  </div>
</template>

<script lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import apiClient from '@/utils/ApiClient'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { useWebResearchStore } from '@/stores/useWebResearchStore'

interface UpdateMessage {
  text: string
  type: string
}

interface TestResult {
  status: string
  error?: string
  [key: string]: any
}

// Type for API responses with status field
interface ApiResponseWithStatus {
  status: string
  message?: string
  settings?: Record<string, unknown>
  [key: string]: unknown
}

export default {
  name: 'WebResearchSettings',
  setup() {
    // Use centralized Pinia store
    const webResearchStore = useWebResearchStore()

    // Local UI state
    const updateMessage = ref<UpdateMessage | null>(null)
    const testResult = ref<TestResult | null>(null)

    // Direct refs from store (for v-model compatibility)
    const researchSettings = webResearchStore.settings
    const researchStatus = webResearchStore.status

    // Show message utility
    const showMessage = (text: string, type: string = 'info') => {
      updateMessage.value = { text, type }
      setTimeout(() => {
        updateMessage.value = null
      }, 3000)
    }

    // Load current settings
    const { execute: loadSettings, loading: isLoadingSettings } = useAsyncHandler(
      async () => {
        // ApiClient.get() returns parsed JSON directly
        // Issue #552: Fixed path to match backend /api/web-research-settings/web-research/*
        // Load status
        const statusData = await apiClient.get('/api/web-research-settings/web-research/status') as unknown as ApiResponseWithStatus
        if (statusData.status === 'success') {
          webResearchStore.updateStatus(statusData as unknown as Record<string, unknown>)
        }

        // Load settings
        const settingsData = await apiClient.get('/api/web-research-settings/web-research/settings') as unknown as ApiResponseWithStatus
        if (settingsData.status === 'success') {
          webResearchStore.updateSettings((settingsData.settings || {}) as Record<string, unknown>)
        }
      },
      {
        errorMessage: 'Failed to load settings',
        notify: showMessage
      }
    )

    // Toggle web research on/off
    const { execute: toggleWebResearch, loading: isTogglingResearch } = useAsyncHandler(
      async () => {
        // ApiClient.post() returns parsed JSON directly
        // Issue #552: Fixed path to match backend /api/web-research-settings/web-research/*
        const endpoint = researchSettings.enabled
          ? '/api/web-research-settings/web-research/enable'
          : '/api/web-research-settings/web-research/disable'
        return await apiClient.post(endpoint) as unknown as ApiResponseWithStatus
      },
      {
        onSuccess: async (data) => {
          if (data.status === 'success') {
            showMessage(data.message || 'Status updated', 'success')
            await loadSettings() // Reload to get updated status
          }
        },
        onRollback: () => {
          // Revert toggle on error
          researchSettings.enabled = !researchSettings.enabled
        },
        errorMessage: 'Failed to update web research status',
        notify: showMessage
      }
    )

    // Update settings (with debounce for auto-save)
    const { execute: updateSettings, loading: isUpdatingSettings } = useAsyncHandler(
      async () => {
        // ApiClient.put() returns parsed JSON directly
        // Issue #552: Fixed path to match backend /api/web-research-settings/web-research/*
        return await apiClient.put('/api/web-research-settings/web-research/settings', researchSettings) as unknown as ApiResponseWithStatus
      },
      {
        debounce: 1000, // Built-in debounce
        onSuccess: async (data) => {
          if (data.status === 'success') {
            showMessage('Settings updated successfully', 'success')
            await loadSettings() // Reload to confirm changes
          }
        },
        errorMessage: 'Failed to update settings',
        notify: showMessage
      }
    )

    // Test web research
    const { execute: testWebResearch, loading: isTestingResearch } = useAsyncHandler(
      async () => {
        testResult.value = null

        // ApiClient.post() returns parsed JSON directly
        // Issue #552: Fixed path to match backend /api/web-research-settings/web-research/*
        const data = await apiClient.post('/api/web-research-settings/web-research/test', { query: 'test web research functionality' }) as unknown as ApiResponseWithStatus
        testResult.value = data as TestResult

        showMessage('Test completed', data.status === 'success' ? 'success' : 'error')
        return data
      },
      {
        onError: (error) => {
          testResult.value = {
            status: 'error',
            error: error.message
          }
        },
        errorMessage: 'Test failed',
        notify: showMessage
      }
    )

    // Clear cache
    const { execute: clearCache, loading: isClearingCache } = useAsyncHandler(
      async () => {
        // ApiClient.post() returns parsed JSON directly
        // Issue #552: Fixed path to match backend /api/web-research-settings/web-research/*
        return await apiClient.post('/api/web-research-settings/web-research/clear-cache') as unknown as ApiResponseWithStatus
      },
      {
        onSuccess: async (data) => {
          if (data.status === 'success') {
            showMessage('Cache cleared successfully', 'success')
            await loadSettings() // Reload to show updated cache stats
          }
        },
        errorMessage: 'Failed to clear cache',
        notify: showMessage
      }
    )

    // Reset circuit breakers
    const { execute: resetCircuitBreakers, loading: isResettingCircuitBreakers } = useAsyncHandler(
      async () => {
        // ApiClient.post() returns parsed JSON directly
        // Issue #552: Fixed path to match backend /api/web-research-settings/web-research/*
        return await apiClient.post('/api/web-research-settings/web-research/reset-circuit-breakers') as unknown as ApiResponseWithStatus
      },
      {
        onSuccess: async (data) => {
          if (data.status === 'success') {
            showMessage('Circuit breakers reset successfully', 'success')
            await loadSettings() // Reload to show updated status
          }
        },
        errorMessage: 'Failed to reset circuit breakers',
        notify: showMessage
      }
    )

    // Computed: Combined loading state
    const isUpdating = computed(() =>
      isLoadingSettings.value ||
      isTogglingResearch.value ||
      isUpdatingSettings.value ||
      isTestingResearch.value ||
      isClearingCache.value ||
      isResettingCircuitBreakers.value
    )

    // Load settings on mount
    onMounted(() => {
      loadSettings()
    })

    // Watch for auto-save on certain settings changes
    watch([
      () => researchSettings.max_results,
      () => researchSettings.timeout_seconds,
      () => researchSettings.auto_research_threshold,
      () => researchSettings.rate_limit_requests,
      () => researchSettings.rate_limit_window
    ], () => {
      // Debounce is built into updateSettings, just call it
      // Only guard against settings update in progress, allow other operations
      if (!isUpdatingSettings.value) {
        updateSettings()
      }
    })

    return {
      // State
      isUpdating,
      updateMessage,
      testResult,
      researchStatus,
      researchSettings,

      // Methods
      loadSettings,
      toggleWebResearch,
      updateSettings,
      testWebResearch,
      clearCache,
      resetCircuitBreakers
    }
  }
}
</script>

<style scoped>
.web-research-settings {
  padding: 20px;
  max-width: 800px;
}

/* Status Section */
.research-status-section {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 30px;
  padding: 15px;
  background: var(--background-secondary);
  border-radius: 8px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-error);
}

.status-indicator.enabled .status-dot {
  background: var(--color-success);
}

/* Main Toggle */
.main-toggle {
  flex: 1;
}

.toggle-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.toggle-slider {
  width: 50px;
  height: 24px;
  background: var(--background-tertiary);
  border-radius: 12px;
  position: relative;
  transition: background 0.3s;
}

.toggle-slider::after {
  content: '';
  position: absolute;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: transform 0.3s;
}

.toggle-label input:checked + .toggle-slider {
  background: var(--color-primary);
}

.toggle-label input:checked + .toggle-slider::after {
  transform: translateX(26px);
}

.toggle-label input {
  display: none;
}

/* Setting Groups */
.setting-group {
  margin-bottom: 30px;
  padding: 20px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.setting-group h4 {
  margin: 0 0 15px 0;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
}

.setting-item {
  margin-bottom: 20px;
}

.setting-item:last-child {
  margin-bottom: 0;
}

.setting-item label {
  display: block;
  margin-bottom: 5px;
  font-weight: 500;
  color: var(--text-primary);
}

.setting-item input,
.setting-item select {
  width: 100%;
  max-width: 200px;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--background-primary);
  color: var(--text-primary);
}

.setting-item input[type="checkbox"] {
  width: auto;
  margin-right: 8px;
}

.setting-item input[type="range"] {
  max-width: 150px;
  margin-right: 10px;
}

.threshold-value {
  font-weight: 600;
  color: var(--color-primary);
}

.setting-hint {
  margin-top: 5px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.setting-description {
  margin-top: 5px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* Method Select */
.method-select {
  min-width: 250px;
}

/* Status Info */
.research-info {
  margin-top: 30px;
  padding: 15px;
  background: var(--background-secondary);
  border-radius: 8px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
  margin-top: 10px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-label {
  font-weight: 500;
  color: var(--text-secondary);
}

.status-value {
  font-weight: 600;
  color: var(--text-primary);
}

/* Action Buttons */
.action-buttons {
  display: flex;
  gap: 10px;
  margin-top: 30px;
  flex-wrap: wrap;
}

.action-buttons button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 15px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--background-primary);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.action-buttons button:hover:not(:disabled) {
  background: var(--background-secondary);
  border-color: var(--color-primary);
}

.action-buttons button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.test-button {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.clear-button {
  background: var(--color-warning);
  color: white;
  border-color: var(--color-warning);
}

.reset-button {
  background: var(--color-info);
  color: white;
  border-color: var(--color-info);
}

/* Test Result */
.test-result {
  margin-top: 20px;
  padding: 15px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.test-result.success {
  background: var(--background-success);
  border-color: var(--color-success);
}

.test-result.error {
  background: var(--background-error);
  border-color: var(--color-error);
}

.test-result pre {
  margin-top: 10px;
  font-size: 12px;
  overflow: auto;
  max-height: 200px;
}

/* Update Message */
.update-message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 15px;
  padding: 10px 15px;
  border-radius: 6px;
  font-size: 14px;
}

.update-message.success {
  background: var(--background-success);
  color: var(--color-success);
  border: 1px solid var(--color-success);
}

.update-message.error {
  background: var(--background-error);
  color: var(--color-error);
  border: 1px solid var(--color-error);
}

/* Responsive Design */
@media (max-width: 768px) {
  .research-status-section {
    flex-direction: column;
    align-items: flex-start;
  }

  .status-grid {
    grid-template-columns: 1fr;
  }

  .action-buttons {
    flex-direction: column;
  }

  .action-buttons button {
    width: 100%;
    justify-content: center;
  }
}
</style>
