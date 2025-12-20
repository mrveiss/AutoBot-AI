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
.sub-tab-content {
  padding: 1rem 0;
}

.embedding-status-display {
  background: var(--bg-tertiary, #334155);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
}

.current-embedding-info {
  font-size: 0.95rem;
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  font-size: 0.9rem;
}

.health-indicator.healthy {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.health-indicator.degraded {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.health-indicator.unhealthy {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.health-indicator.unknown {
  background: rgba(148, 163, 184, 0.2);
  color: #94a3b8;
}

.embedding-actions {
  display: flex;
  gap: 0.5rem;
}

.test-embedding-btn,
.refresh-models-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.test-embedding-btn {
  background: var(--primary-color, #667eea);
  color: white;
}

.test-embedding-btn:hover:not(:disabled) {
  background: var(--primary-hover, #5a6fd6);
}

.refresh-models-btn {
  background: var(--bg-secondary, #1e293b);
  color: var(--text-primary, #f8fafc);
  border: 1px solid var(--border-color, #475569);
}

.refresh-models-btn:hover:not(:disabled) {
  background: var(--bg-tertiary, #334155);
}

.test-embedding-btn:disabled,
.refresh-models-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.setting-item {
  margin-bottom: 1rem;
}

.setting-item label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: var(--text-secondary, #e2e8f0);
}

.setting-item input,
.setting-item select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--border-color, #475569);
  border-radius: 4px;
  background: var(--bg-secondary, #1e293b);
  color: var(--text-primary, #f8fafc);
  font-size: 0.95rem;
}

.setting-item input:focus,
.setting-item select:focus {
  outline: none;
  border-color: var(--primary-color, #667eea);
}

.input-group {
  display: flex;
  gap: 0.5rem;
}

.input-group input {
  flex: 1;
}

.test-endpoint-btn {
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary, #334155);
  border: 1px solid var(--border-color, #475569);
  border-radius: 4px;
  color: var(--text-primary, #f8fafc);
  cursor: pointer;
  transition: all 0.2s;
}

.test-endpoint-btn:hover {
  background: var(--bg-secondary, #1e293b);
  border-color: var(--primary-color, #667eea);
}

.validation-error {
  border-color: #ef4444 !important;
}

.provider-section {
  margin-top: 1.5rem;
  padding: 1rem;
  background: var(--bg-secondary, #1e293b);
  border-radius: 8px;
  border: 1px solid var(--border-color, #475569);
}

.model-selection {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.model-selection select {
  flex: 1;
}

.loading-indicator {
  font-size: 0.85rem;
  color: var(--text-muted, #94a3b8);
}
</style>
