<template>
  <div class="sub-tab-content">
    <h3>Embedding Configuration</h3>

    <!-- Embedding Status Display -->
    <div v-if="embeddingStatus" class="embedding-status-display">
      <div class="current-embedding-info">
        <strong>Current Embedding Model:</strong> {{ currentEmbeddingModel }}
      </div>
      <div
        :class="['health-indicator', embeddingStatus.status || 'unknown']"
      >
        <i :class="getHealthIconClass(embeddingStatus.status)"></i>
        {{ embeddingStatus.message || 'Status unknown' }}
      </div>
      <div class="embedding-actions">
        <button @click="testEmbeddingConnection" :disabled="isTestingEmbedding" class="test-embedding-btn">
          <i :class="isTestingEmbedding ? 'fas fa-spinner fa-spin' : 'fas fa-vector-square'"></i>
          {{ isTestingEmbedding ? 'Testing...' : 'Test Embedding' }}
        </button>
        <button @click="handleRefreshModels" :disabled="isRefreshingModels" class="refresh-models-btn">
          <i :class="isRefreshingModels ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
          {{ isRefreshingModels ? 'Refreshing...' : 'Refresh Models' }}
        </button>
      </div>
    </div>

    <div class="setting-item">
      <label for="embedding-provider">Embedding Provider</label>
      <select
        id="embedding-provider"
        :value="embeddingSettings?.provider || 'ollama'"
        @change="handleProviderChange"
      >
        <option value="ollama">Ollama</option>
        <option value="openai">OpenAI</option>
        <option value="huggingface">Hugging Face</option>
      </select>
    </div>

    <!-- Provider-specific settings -->
    <div class="provider-section">
      <div class="setting-item">
        <label for="embedding-endpoint">Endpoint</label>
        <div class="input-group">
          <input
            id="embedding-endpoint"
            type="text"
            :value="currentEndpoint"
            @input="handleEndpointChange"
            :class="{ 'validation-error': validationErrors.embedding_endpoint }"
          />
          <button @click="testEmbeddingEndpoint" class="test-endpoint-btn">
            <i class="fas fa-plug"></i>
          </button>
        </div>
      </div>

      <div class="setting-item">
        <label for="embedding-model">Model</label>
        <div class="model-selection">
          <select
            id="embedding-model"
            :value="currentEmbeddingModel"
            @change="handleModelChange"
          >
            <option
              v-for="model in availableModels"
              :key="model"
              :value="model"
            >
              {{ model }}
            </option>
          </select>
          <div v-if="isRefreshingModels" class="loading-indicator">
            <i class="fas fa-spinner fa-spin"></i> Loading models...
          </div>
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
 * Embedding Settings Panel Component
 *
 * Manages embedding model configuration for vector operations.
 * Extracted from BackendSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, reactive, computed } from 'vue'
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('EmbeddingSettingsPanel')

// Type definitions
interface ProviderSettings {
  endpoint?: string
  selected_model?: string
  models?: string[]
}

interface EmbeddingSettings {
  provider: string
  providers: {
    [key: string]: ProviderSettings
  }
}

interface EmbeddingStatus {
  status: string
  message: string
}

interface Props {
  embeddingSettings?: EmbeddingSettings | null
  embeddingStatus?: EmbeddingStatus | null
}

interface Emits {
  (e: 'setting-changed', key: string, value: unknown): void
  (e: 'refresh-models', provider: string): void
  (e: 'test-connection'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// State
const isTestingEmbedding = ref(false)
const isRefreshingModels = ref(false)
const validationErrors = reactive<Record<string, string>>({})

// Computed properties
const currentProvider = computed(() => props.embeddingSettings?.provider || 'ollama')

const currentEndpoint = computed(() => {
  const provider = currentProvider.value
  return props.embeddingSettings?.providers?.[provider]?.endpoint || ''
})

const currentEmbeddingModel = computed(() => {
  const provider = currentProvider.value
  return props.embeddingSettings?.providers?.[provider]?.selected_model || ''
})

const availableModels = computed(() => {
  const provider = currentProvider.value
  return props.embeddingSettings?.providers?.[provider]?.models || []
})

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
const handleProviderChange = (event: Event) => {
  const target = event.target as HTMLSelectElement
  emit('setting-changed', 'provider', target.value)
}

const handleEndpointChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  delete validationErrors.embedding_endpoint
  emit('setting-changed', `providers.${currentProvider.value}.endpoint`, target.value)
}

const handleModelChange = (event: Event) => {
  const target = event.target as HTMLSelectElement
  emit('setting-changed', `providers.${currentProvider.value}.selected_model`, target.value)
}

const handleRefreshModels = async () => {
  isRefreshingModels.value = true
  try {
    emit('refresh-models', currentProvider.value)
  } finally {
    setTimeout(() => {
      isRefreshingModels.value = false
    }, 2000)
  }
}

// Connection test
const testEmbeddingConnection = async () => {
  isTestingEmbedding.value = true
  try {
    emit('test-connection')
  } finally {
    setTimeout(() => {
      isTestingEmbedding.value = false
    }, 2000)
  }
}

const testEmbeddingEndpoint = async () => {
  const endpoint = currentEndpoint.value
  if (!endpoint) {
    validationErrors.embedding_endpoint = 'Endpoint is required'
    return
  }

  try {
    const response = await fetch(endpoint, { method: 'HEAD', mode: 'no-cors' })
    logger.info('Endpoint test completed', response)
    delete validationErrors.embedding_endpoint
  } catch (error) {
    logger.error('Endpoint test failed', error)
    validationErrors.embedding_endpoint = 'Failed to connect to endpoint'
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.sub-tab-content {
  padding: var(--spacing-4) 0;
}

.embedding-status-display {
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

.current-embedding-info {
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

.embedding-actions {
  display: flex;
  gap: var(--spacing-2);
}

.test-embedding-btn,
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

.test-embedding-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.test-embedding-btn:hover:not(:disabled) {
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

.test-embedding-btn:disabled,
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
