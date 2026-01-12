<template>
  <div class="sub-tab-content">
    <h3>LLM Configuration</h3>

    <!-- Enhanced LLM Status Display -->
    <div class="llm-status-display">
      <div class="current-llm-info">
        <strong>Current LLM:</strong> {{ currentLLMDisplay }}
      </div>
      <div
        v-if="healthStatus?.backend?.llm_provider"
        :class="['health-indicator', healthStatus.backend.llm_provider.status || 'unknown']"
      >
        <i :class="getHealthIconClass(healthStatus.backend.llm_provider.status)"></i>
        {{ healthStatus.backend.llm_provider.message || 'Status unknown' }}
      </div>
      <div class="llm-actions">
        <button @click="testLLMConnection" :disabled="isTestingLLM" class="test-llm-btn">
          <i :class="isTestingLLM ? 'fas fa-spinner fa-spin' : 'fas fa-brain'"></i>
          {{ isTestingLLM ? 'Testing LLM...' : 'Test LLM' }}
        </button>
        <button @click="refreshLLMModels" :disabled="isRefreshingLLMModels" class="refresh-models-btn">
          <i :class="isRefreshingLLMModels ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
          {{ isRefreshingLLMModels ? 'Refreshing...' : 'Refresh Models' }}
        </button>
      </div>
    </div>

    <div class="setting-item">
      <label for="provider-type">Provider Type</label>
      <select
        id="provider-type"
        :value="llmSettings?.provider_type || 'local'"
        @change="handleSelectChange('provider_type')"
      >
        <option value="local">Local LLM</option>
        <option value="cloud">Cloud LLM</option>
      </select>
    </div>

    <!-- Local LLM Settings -->
    <div v-if="llmSettings?.provider_type === 'local'" class="provider-section">
      <div class="setting-item">
        <label for="local-provider">Local Provider</label>
        <select
          id="local-provider"
          :value="llmSettings.local?.provider || 'ollama'"
          @change="handleSelectChange('local.provider')"
        >
          <option value="ollama">Ollama</option>
          <option value="lmstudio">LM Studio</option>
        </select>
      </div>

      <!-- Ollama Settings -->
      <div v-if="llmSettings.local?.provider === 'ollama'" class="provider-config">
        <div class="setting-item">
          <label for="ollama-endpoint">Ollama Endpoint</label>
          <div class="input-group">
            <input
              id="ollama-endpoint"
              type="text"
              :value="llmSettings.local?.providers?.ollama?.endpoint || ''"
              @input="handleInputChangeValidated('local.providers.ollama.endpoint')"
              :class="{ 'validation-error': validationErrors.ollama_endpoint }"
            />
            <button @click="testOllamaConnection" class="test-endpoint-btn">
              <i class="fas fa-plug"></i>
            </button>
          </div>
        </div>
        <div class="setting-item">
          <label for="ollama-model">Model</label>
          <div class="model-selection">
            <select
              id="ollama-model"
              :value="llmSettings.local?.providers?.ollama?.selected_model || ''"
              @change="handleSelectChange('local.providers.ollama.selected_model')"
            >
              <option
                v-for="model in llmSettings.local?.providers?.ollama?.models || []"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
            <div v-if="isRefreshingLLMModels" class="loading-indicator">
              <i class="fas fa-spinner fa-spin"></i> Loading models...
            </div>
          </div>
        </div>
      </div>

      <!-- LM Studio Settings -->
      <div v-else-if="llmSettings.local?.provider === 'lmstudio'" class="provider-config">
        <div class="setting-item">
          <label for="lmstudio-endpoint">LM Studio Endpoint</label>
          <div class="input-group">
            <input
              id="lmstudio-endpoint"
              type="text"
              :value="llmSettings.local?.providers?.lmstudio?.endpoint || ''"
              @input="handleInputChangeValidated('local.providers.lmstudio.endpoint')"
              :class="{ 'validation-error': validationErrors.lmstudio_endpoint }"
            />
            <button @click="testLMStudioConnection" class="test-endpoint-btn">
              <i class="fas fa-plug"></i>
            </button>
          </div>
        </div>
        <div class="setting-item">
          <label for="lmstudio-model">Model</label>
          <select
            id="lmstudio-model"
            :value="llmSettings.local?.providers?.lmstudio?.selected_model || ''"
            @change="handleSelectChange('local.providers.lmstudio.selected_model')"
          >
            <option
              v-for="model in llmSettings.local?.providers?.lmstudio?.models || []"
              :key="model"
              :value="model"
            >
              {{ model }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- Cloud LLM Settings -->
    <div v-else-if="llmSettings?.provider_type === 'cloud'" class="provider-section">
      <div class="setting-item">
        <label for="cloud-provider">Cloud Provider</label>
        <select
          id="cloud-provider"
          :value="llmSettings.cloud?.provider || 'openai'"
          @change="handleSelectChange('cloud.provider')"
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </div>

      <!-- OpenAI Settings -->
      <div v-if="llmSettings.cloud?.provider === 'openai'" class="provider-config">
        <div class="setting-item">
          <label for="openai-api-key">API Key</label>
          <div class="input-group">
            <input
              id="openai-api-key"
              type="password"
              :value="llmSettings.cloud?.providers?.openai?.api_key || ''"
              placeholder="Enter API Key"
              @input="handleInputChangeValidated('cloud.providers.openai.api_key')"
              :class="{ 'validation-error': validationErrors.openai_api_key }"
            />
            <button @click="testOpenAIConnection" class="test-endpoint-btn">
              <i class="fas fa-key"></i> Test
            </button>
          </div>
        </div>
        <div class="setting-item">
          <label for="openai-endpoint">Endpoint</label>
          <input
            id="openai-endpoint"
            type="text"
            :value="llmSettings.cloud?.providers?.openai?.endpoint || ''"
            @input="handleInputChange('cloud.providers.openai.endpoint')"
          />
        </div>
        <div class="setting-item">
          <label for="openai-model">Model</label>
          <select
            id="openai-model"
            :value="llmSettings.cloud?.providers?.openai?.selected_model || ''"
            @change="handleSelectChange('cloud.providers.openai.selected_model')"
          >
            <option
              v-for="model in llmSettings.cloud?.providers?.openai?.models || []"
              :key="model"
              :value="model"
            >
              {{ model }}
            </option>
          </select>
        </div>
      </div>

      <!-- Anthropic Settings -->
      <div v-else-if="llmSettings.cloud?.provider === 'anthropic'" class="provider-config">
        <div class="setting-item">
          <label for="anthropic-api-key">API Key</label>
          <div class="input-group">
            <input
              id="anthropic-api-key"
              type="password"
              :value="llmSettings.cloud?.providers?.anthropic?.api_key || ''"
              placeholder="Enter API Key"
              @input="handleInputChangeValidated('cloud.providers.anthropic.api_key')"
              :class="{ 'validation-error': validationErrors.anthropic_api_key }"
            />
            <button @click="testAnthropicConnection" class="test-endpoint-btn">
              <i class="fas fa-key"></i> Test
            </button>
          </div>
        </div>
        <div class="setting-item">
          <label for="anthropic-model">Model</label>
          <select
            id="anthropic-model"
            :value="llmSettings.cloud?.providers?.anthropic?.selected_model || ''"
            @change="handleSelectChange('cloud.providers.anthropic.selected_model')"
          >
            <option
              v-for="model in llmSettings.cloud?.providers?.anthropic?.models || []"
              :key="model"
              :value="model"
            >
              {{ model }}
            </option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * LLM Settings Panel Component
 *
 * Extracted from BackendSettings.vue for better maintainability.
 * Issue #184: Split oversized Vue components
 */

import { ref, reactive } from 'vue'
import type { HealthStatus } from '@/types/settings'
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LLMSettingsPanel')

// Type definitions
interface ProviderConfig {
  endpoint?: string
  selected_model?: string
  models?: string[]
  api_key?: string
}

interface LocalLLMSettings {
  provider?: string
  providers?: {
    ollama?: ProviderConfig
    lmstudio?: ProviderConfig
  }
}

interface CloudLLMSettings {
  provider?: string
  providers?: {
    openai?: ProviderConfig
    anthropic?: ProviderConfig
  }
}

interface LLMSettings {
  provider_type?: string
  local?: LocalLLMSettings
  cloud?: CloudLLMSettings
}

interface Props {
  llmSettings?: LLMSettings | null
  healthStatus: HealthStatus | null
  currentLLMDisplay: string
}

interface Emits {
  (e: 'setting-changed', key: string, value: unknown): void
  (e: 'test-connection', provider: string): void
  (e: 'refresh-models'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// State
const isTestingLLM = ref(false)
const isRefreshingLLMModels = ref(false)
const validationErrors = reactive<Record<string, string>>({})

// Health icon helper
const getHealthIconClass = (status: string | undefined): string => {
  switch (status) {
    case 'healthy':
      return 'fas fa-check-circle'
    case 'degraded':
      return 'fas fa-exclamation-triangle'
    case 'unhealthy':
      return 'fas fa-times-circle'
    default:
      return 'fas fa-question-circle'
  }
}

// Event handlers
const handleSelectChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLSelectElement
  emit('setting-changed', key, target.value)
}

const handleInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('setting-changed', key, target.value)
}

const handleInputChangeValidated = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  // Clear validation error
  const errorKey = key.replace(/\./g, '_')
  delete validationErrors[errorKey]
  emit('setting-changed', key, target.value)
}

// Connection test handlers
const testLLMConnection = async () => {
  isTestingLLM.value = true
  try {
    emit('test-connection', 'llm')
  } finally {
    setTimeout(() => {
      isTestingLLM.value = false
    }, 2000)
  }
}

const testOllamaConnection = async () => {
  emit('test-connection', 'ollama')
}

const testLMStudioConnection = async () => {
  emit('test-connection', 'lmstudio')
}

const testOpenAIConnection = async () => {
  emit('test-connection', 'openai')
}

const testAnthropicConnection = async () => {
  emit('test-connection', 'anthropic')
}

const refreshLLMModels = async () => {
  isRefreshingLLMModels.value = true
  try {
    emit('refresh-models')
  } finally {
    setTimeout(() => {
      isRefreshingLLMModels.value = false
    }, 2000)
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.sub-tab-content {
  padding: var(--spacing-4) 0;
}

.llm-status-display {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-6);
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  align-items: center;
  justify-content: space-between;
}

.current-llm-info {
  font-size: var(--text-sm);
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.health-indicator.healthy {
  background: var(--color-success-bg-transparent);
  color: var(--color-success);
}

.health-indicator.degraded {
  background: var(--color-warning-bg-transparent);
  color: var(--color-warning);
}

.health-indicator.unhealthy {
  background: var(--color-error-bg-transparent);
  color: var(--color-error);
}

.health-indicator.unknown {
  background: var(--bg-tertiary-transparent);
  color: var(--text-tertiary);
}

.llm-actions {
  display: flex;
  gap: var(--spacing-2);
}

.test-llm-btn,
.refresh-models-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  transition: all var(--duration-200) var(--ease-in-out);
}

.test-llm-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.test-llm-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.refresh-models-btn {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.refresh-models-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
}

.test-llm-btn:disabled,
.refresh-models-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.setting-item {
  margin-bottom: var(--spacing-4);
}

.setting-item label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.setting-item input,
.setting-item select {
  width: 100%;
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.input-group {
  display: flex;
  gap: var(--spacing-2);
}

.input-group input {
  flex: 1;
}

.test-endpoint-btn {
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.test-endpoint-btn:hover {
  background: var(--bg-secondary);
  border-color: var(--color-primary);
}

.validation-error {
  border-color: var(--color-error) !important;
}

.provider-section {
  margin-top: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.provider-config {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.model-selection {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.model-selection select {
  flex: 1;
}

.loading-indicator {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}
</style>
