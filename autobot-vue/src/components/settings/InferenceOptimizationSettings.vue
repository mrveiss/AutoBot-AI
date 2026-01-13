<template>
  <div class="inference-optimization-settings">
    <h3><i class="fas fa-bolt mr-2"></i>Inference Optimization</h3>
    <p class="section-description">
      Configure LLM inference optimizations for improved latency and efficiency.
    </p>

    <!-- Optimization Metrics Overview -->
    <div class="metrics-overview" v-if="metrics">
      <div class="metric-card">
        <i class="fas fa-compress"></i>
        <div class="metric-value">{{ metrics.prompts_compressed || 0 }}</div>
        <div class="metric-label">Prompts Compressed</div>
      </div>
      <div class="metric-card">
        <i class="fas fa-coins"></i>
        <div class="metric-value">{{ metrics.tokens_saved || 0 }}</div>
        <div class="metric-label">Tokens Saved</div>
      </div>
      <div class="metric-card">
        <i class="fas fa-clock"></i>
        <div class="metric-value">{{ metrics.cache?.hit_rate?.toFixed(1) || 0 }}%</div>
        <div class="metric-label">Cache Hit Rate</div>
      </div>
      <div class="metric-card">
        <i class="fas fa-hourglass-half"></i>
        <div class="metric-value">{{ metrics.rate_limits_handled || 0 }}</div>
        <div class="metric-label">Rate Limits Handled</div>
      </div>
    </div>

    <!-- Prompt Compression Section -->
    <div class="settings-section">
      <h4><i class="fas fa-compress-alt"></i> Prompt Compression</h4>
      <p class="section-hint">Reduces token usage by removing filler phrases and redundant text.</p>

      <div class="setting-item">
        <label for="prompt-compression-enabled">Enable Prompt Compression</label>
        <input
          id="prompt-compression-enabled"
          type="checkbox"
          :checked="settings.prompt_compression_enabled"
          @change="updateSetting('prompt_compression_enabled', ($event.target as HTMLInputElement).checked)"
        />
      </div>

      <div class="setting-item" v-if="settings.prompt_compression_enabled">
        <label for="prompt-compression-ratio">Target Compression Ratio</label>
        <div class="slider-container">
          <input
            id="prompt-compression-ratio"
            type="range"
            min="0.3"
            max="1.0"
            step="0.05"
            :value="settings.prompt_compression_ratio"
            @input="updateSetting('prompt_compression_ratio', parseFloat(($event.target as HTMLInputElement).value))"
          />
          <span class="slider-value">{{ (settings.prompt_compression_ratio * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <div class="setting-item" v-if="settings.prompt_compression_enabled">
        <label for="prompt-compression-min-length">Minimum Length (chars)</label>
        <input
          id="prompt-compression-min-length"
          type="number"
          :value="settings.prompt_compression_min_length"
          min="10"
          max="1000"
          @input="updateSetting('prompt_compression_min_length', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item" v-if="settings.prompt_compression_enabled">
        <label for="prompt-compression-preserve-code">Preserve Code Blocks</label>
        <input
          id="prompt-compression-preserve-code"
          type="checkbox"
          :checked="settings.prompt_compression_preserve_code"
          @change="updateSetting('prompt_compression_preserve_code', ($event.target as HTMLInputElement).checked)"
        />
      </div>

      <div class="setting-item" v-if="settings.prompt_compression_enabled">
        <label for="prompt-compression-aggressive">Aggressive Mode</label>
        <input
          id="prompt-compression-aggressive"
          type="checkbox"
          :checked="settings.prompt_compression_aggressive"
          @change="updateSetting('prompt_compression_aggressive', ($event.target as HTMLInputElement).checked)"
        />
        <span class="setting-hint">Uses more aggressive compression techniques</span>
      </div>
    </div>

    <!-- Response Caching Section -->
    <div class="settings-section">
      <h4><i class="fas fa-database"></i> Response Caching</h4>
      <p class="section-hint">Caches LLM responses to avoid redundant API calls.</p>

      <div class="setting-item">
        <label for="cache-enabled">Enable Response Caching</label>
        <input
          id="cache-enabled"
          type="checkbox"
          :checked="settings.cache_enabled"
          @change="updateSetting('cache_enabled', ($event.target as HTMLInputElement).checked)"
        />
      </div>

      <div class="setting-item" v-if="settings.cache_enabled">
        <label for="cache-l1-size">L1 Cache Size (entries)</label>
        <input
          id="cache-l1-size"
          type="number"
          :value="settings.cache_l1_size"
          min="10"
          max="1000"
          @input="updateSetting('cache_l1_size', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item" v-if="settings.cache_enabled">
        <label for="cache-l2-ttl">L2 Cache TTL (seconds)</label>
        <input
          id="cache-l2-ttl"
          type="number"
          :value="settings.cache_l2_ttl"
          min="60"
          max="3600"
          @input="updateSetting('cache_l2_ttl', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- Cloud Provider Optimizations -->
    <div class="settings-section">
      <h4><i class="fas fa-cloud"></i> Cloud Provider Optimizations</h4>
      <p class="section-hint">Optimizations for OpenAI, Anthropic, and other cloud APIs.</p>

      <div class="setting-item">
        <label for="cloud-connection-pool-size">Connection Pool Size</label>
        <input
          id="cloud-connection-pool-size"
          type="number"
          :value="settings.cloud_connection_pool_size"
          min="10"
          max="500"
          @input="updateSetting('cloud_connection_pool_size', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item">
        <label for="cloud-batch-window-ms">Batch Window (ms)</label>
        <input
          id="cloud-batch-window-ms"
          type="number"
          :value="settings.cloud_batch_window_ms"
          min="10"
          max="500"
          @input="updateSetting('cloud_batch_window_ms', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item">
        <label for="cloud-max-batch-size">Max Batch Size</label>
        <input
          id="cloud-max-batch-size"
          type="number"
          :value="settings.cloud_max_batch_size"
          min="1"
          max="50"
          @input="updateSetting('cloud_max_batch_size', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item">
        <label for="cloud-retry-max-attempts">Retry Max Attempts</label>
        <input
          id="cloud-retry-max-attempts"
          type="number"
          :value="settings.cloud_retry_max_attempts"
          min="1"
          max="10"
          @input="updateSetting('cloud_retry_max_attempts', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item">
        <label for="cloud-retry-base-delay">Retry Base Delay (s)</label>
        <input
          id="cloud-retry-base-delay"
          type="number"
          step="0.1"
          :value="settings.cloud_retry_base_delay"
          min="0.1"
          max="10"
          @input="updateSetting('cloud_retry_base_delay', parseFloat(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item">
        <label for="cloud-retry-max-delay">Retry Max Delay (s)</label>
        <input
          id="cloud-retry-max-delay"
          type="number"
          :value="settings.cloud_retry_max_delay"
          min="10"
          max="300"
          @input="updateSetting('cloud_retry_max_delay', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- Local Provider Optimizations -->
    <div class="settings-section">
      <h4><i class="fas fa-server"></i> Local Provider Optimizations</h4>
      <p class="section-hint">Optimizations for Ollama, vLLM, and local models.</p>

      <div class="setting-item">
        <label for="local-speculation-enabled">Enable Speculative Decoding</label>
        <input
          id="local-speculation-enabled"
          type="checkbox"
          :checked="settings.local_speculation_enabled"
          @change="updateSetting('local_speculation_enabled', ($event.target as HTMLInputElement).checked)"
        />
        <span class="setting-hint">Uses a draft model for faster token generation</span>
      </div>

      <div class="setting-item" v-if="settings.local_speculation_enabled">
        <label for="local-speculation-draft-model">Draft Model</label>
        <input
          id="local-speculation-draft-model"
          type="text"
          :value="settings.local_speculation_draft_model"
          placeholder="e.g., llama3.2:1b"
          @input="updateSetting('local_speculation_draft_model', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div class="setting-item" v-if="settings.local_speculation_enabled">
        <label for="local-speculation-num-tokens">Speculation Tokens</label>
        <input
          id="local-speculation-num-tokens"
          type="number"
          :value="settings.local_speculation_num_tokens"
          min="1"
          max="20"
          @input="updateSetting('local_speculation_num_tokens', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item" v-if="settings.local_speculation_enabled">
        <label for="local-speculation-use-ngram">Use N-gram Speculation</label>
        <input
          id="local-speculation-use-ngram"
          type="checkbox"
          :checked="settings.local_speculation_use_ngram"
          @change="updateSetting('local_speculation_use_ngram', ($event.target as HTMLInputElement).checked)"
        />
      </div>

      <div class="setting-item">
        <label for="local-quantization-type">Quantization Type</label>
        <select
          id="local-quantization-type"
          :value="settings.local_quantization_type"
          @change="updateSetting('local_quantization_type', ($event.target as HTMLSelectElement).value)"
        >
          <option value="none">None</option>
          <option value="int8">INT8</option>
          <option value="int4">INT4</option>
          <option value="fp8">FP8</option>
          <option value="awq">AWQ</option>
          <option value="gptq">GPTQ</option>
        </select>
      </div>

      <div class="setting-item">
        <label for="local-vllm-multi-step">vLLM Multi-Step Count</label>
        <input
          id="local-vllm-multi-step"
          type="number"
          :value="settings.local_vllm_multi_step"
          min="1"
          max="32"
          @input="updateSetting('local_vllm_multi_step', parseInt(($event.target as HTMLInputElement).value))"
        />
      </div>

      <div class="setting-item">
        <label for="local-vllm-prefix-caching">vLLM Prefix Caching</label>
        <input
          id="local-vllm-prefix-caching"
          type="checkbox"
          :checked="settings.local_vllm_prefix_caching"
          @change="updateSetting('local_vllm_prefix_caching', ($event.target as HTMLInputElement).checked)"
        />
      </div>

      <div class="setting-item">
        <label for="local-vllm-async-output">vLLM Async Output</label>
        <input
          id="local-vllm-async-output"
          type="checkbox"
          :checked="settings.local_vllm_async_output"
          @change="updateSetting('local_vllm_async_output', ($event.target as HTMLInputElement).checked)"
        />
      </div>
    </div>

    <!-- Actions -->
    <div class="settings-actions">
      <button @click="refreshMetrics" class="action-btn secondary">
        <i class="fas fa-sync"></i> Refresh Metrics
      </button>
      <button @click="saveSettings" :disabled="isSaving" class="action-btn primary">
        <i :class="isSaving ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
        {{ isSaving ? 'Saving...' : 'Save Settings' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('InferenceOptimizationSettings')

// Props
interface Props {
  isSettingsLoaded?: boolean
}

defineProps<Props>()

// Emits
const emit = defineEmits<{
  'setting-changed': [key: string, value: unknown]
  'change': []
}>()

// Settings state
const settings = reactive({
  // Prompt compression
  prompt_compression_enabled: true,
  prompt_compression_ratio: 0.7,
  prompt_compression_min_length: 100,
  prompt_compression_preserve_code: true,
  prompt_compression_aggressive: false,
  // Response caching
  cache_enabled: true,
  cache_l1_size: 100,
  cache_l2_ttl: 300,
  // Cloud optimizations
  cloud_connection_pool_size: 100,
  cloud_batch_window_ms: 50,
  cloud_max_batch_size: 10,
  cloud_retry_max_attempts: 3,
  cloud_retry_base_delay: 1.0,
  cloud_retry_max_delay: 60.0,
  // Local optimizations
  local_speculation_enabled: false,
  local_speculation_draft_model: '',
  local_speculation_num_tokens: 5,
  local_speculation_use_ngram: false,
  local_quantization_type: 'none',
  local_vllm_multi_step: 8,
  local_vllm_prefix_caching: true,
  local_vllm_async_output: true
})

// Metrics state
interface OptimizationMetrics {
  prompts_compressed?: number
  tokens_saved?: number
  rate_limits_handled?: number
  cache?: {
    hit_rate?: number
    l1_hits?: number
    l2_hits?: number
  }
}

const metrics = ref<OptimizationMetrics | null>(null)
const isSaving = ref(false)

// Update individual setting
const updateSetting = (key: string, value: unknown) => {
  (settings as Record<string, unknown>)[key] = value
  emit('setting-changed', key, value)
  emit('change')
}

// Load settings from backend
const loadSettings = async () => {
  try {
    const response = await fetch(`${getBackendUrl()}/api/llm-optimization/inference/settings`)
    if (response.ok) {
      const data = await response.json()
      Object.assign(settings, data.settings)
      logger.debug('Loaded inference optimization settings')
    }
  } catch (error) {
    logger.error('Failed to load inference optimization settings:', error)
  }
}

// Save settings to backend
const saveSettings = async () => {
  isSaving.value = true
  try {
    const response = await fetch(`${getBackendUrl()}/api/llm-optimization/inference/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    })
    if (response.ok) {
      logger.info('Inference optimization settings saved')
    } else {
      logger.error('Failed to save settings:', await response.text())
    }
  } catch (error) {
    logger.error('Failed to save inference optimization settings:', error)
  } finally {
    isSaving.value = false
  }
}

// Refresh metrics from backend
const refreshMetrics = async () => {
  try {
    const response = await fetch(`${getBackendUrl()}/api/llm-optimization/inference/metrics`)
    if (response.ok) {
      const data = await response.json()
      metrics.value = data.optimization
      logger.debug('Refreshed inference optimization metrics')
    }
  } catch (error) {
    logger.error('Failed to refresh metrics:', error)
  }
}

// Initialize on mount
onMounted(async () => {
  await loadSettings()
  await refreshMetrics()
})
</script>

<style scoped>
.inference-optimization-settings {
  padding: var(--spacing-lg, 1.5rem);
}

.inference-optimization-settings h3 {
  margin-bottom: var(--spacing-sm, 0.5rem);
  color: var(--text-primary, #1a1a2e);
  font-size: 1.25rem;
  font-weight: 600;
}

.section-description {
  color: var(--text-secondary, #6b7280);
  margin-bottom: var(--spacing-lg, 1.5rem);
  font-size: 0.9rem;
}

/* Metrics Overview */
.metrics-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-md, 1rem);
  margin-bottom: var(--spacing-xl, 2rem);
}

.metric-card {
  background: var(--bg-secondary, #f8fafc);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  padding: var(--spacing-md, 1rem);
  text-align: center;
  transition: all 0.2s ease;
}

.metric-card:hover {
  border-color: var(--primary-color, #3b82f6);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}

.metric-card i {
  font-size: 1.5rem;
  color: var(--primary-color, #3b82f6);
  margin-bottom: var(--spacing-sm, 0.5rem);
}

.metric-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary, #1a1a2e);
}

.metric-label {
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
  margin-top: var(--spacing-xs, 0.25rem);
}

/* Settings Sections */
.settings-section {
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  padding: var(--spacing-lg, 1.5rem);
  margin-bottom: var(--spacing-lg, 1.5rem);
}

.settings-section h4 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: var(--spacing-xs, 0.25rem);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 0.5rem);
}

.settings-section h4 i {
  color: var(--primary-color, #3b82f6);
}

.section-hint {
  font-size: 0.85rem;
  color: var(--text-secondary, #6b7280);
  margin-bottom: var(--spacing-md, 1rem);
}

/* Setting Items */
.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm, 0.5rem) 0;
  border-bottom: 1px solid var(--border-light, #f1f5f9);
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-item label {
  font-size: 0.9rem;
  color: var(--text-primary, #1a1a2e);
  flex: 1;
}

.setting-item input[type="checkbox"] {
  width: 1.25rem;
  height: 1.25rem;
  cursor: pointer;
}

.setting-item input[type="number"],
.setting-item input[type="text"],
.setting-item select {
  width: 120px;
  padding: var(--spacing-xs, 0.25rem) var(--spacing-sm, 0.5rem);
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  font-size: 0.9rem;
}

.setting-item input[type="number"]:focus,
.setting-item input[type="text"]:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--primary-color, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.setting-hint {
  font-size: 0.75rem;
  color: var(--text-tertiary, #9ca3af);
  margin-left: var(--spacing-sm, 0.5rem);
}

/* Slider Container */
.slider-container {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 0.5rem);
}

.slider-container input[type="range"] {
  width: 150px;
  cursor: pointer;
}

.slider-value {
  min-width: 40px;
  text-align: right;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--primary-color, #3b82f6);
}

/* Actions */
.settings-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md, 1rem);
  margin-top: var(--spacing-lg, 1.5rem);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 0.5rem);
  padding: var(--spacing-sm, 0.5rem) var(--spacing-lg, 1.5rem);
  border: none;
  border-radius: var(--radius-md, 8px);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn.primary {
  background: var(--primary-color, #3b82f6);
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  background: var(--primary-hover, #2563eb);
}

.action-btn.secondary {
  background: var(--bg-secondary, #f8fafc);
  color: var(--text-primary, #1a1a2e);
  border: 1px solid var(--border-color, #e2e8f0);
}

.action-btn.secondary:hover {
  background: var(--bg-tertiary, #f1f5f9);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 768px) {
  .metrics-overview {
    grid-template-columns: repeat(2, 1fr);
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm, 0.5rem);
  }

  .setting-item input[type="number"],
  .setting-item input[type="text"],
  .setting-item select {
    width: 100%;
  }

  .slider-container {
    width: 100%;
  }

  .slider-container input[type="range"] {
    flex: 1;
  }

  .settings-actions {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
