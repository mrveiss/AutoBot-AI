// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LLM Configuration Composable
 * Issue #897 - LLM Configuration Panel
 */

import { ref, onMounted } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useLlmConfig')

// ===== Type Definitions =====

export interface LLMConfig {
  provider: string
  model: string
  api_key?: string
  endpoint?: string
  temperature?: number
  max_tokens?: number
  [key: string]: unknown
}

export interface LLMProvider {
  name: string
  display_name: string
  models: string[]
  is_active: boolean
  is_available: boolean
  config?: Record<string, unknown>
}

export interface LLMModel {
  id: string
  name: string
  provider: string
  context_window?: number
  max_tokens?: number
}

export interface ConnectionTestResult {
  success: boolean
  provider: string
  message: string
  latency_ms?: number
  error?: string
}

export interface UseLlmConfigOptions {
  autoFetch?: boolean
}

// ===== Composable Implementation =====

export function useLlmConfig(options: UseLlmConfigOptions = {}) {
  const { autoFetch = true } = options

  const config = ref<LLMConfig | null>(null)
  const providers = ref<LLMProvider[]>([])
  const models = ref<LLMModel[]>([])
  const currentProvider = ref<string | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ===== API Methods =====

  async function fetchConfig(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/llm/config')
      config.value = data
      currentProvider.value = data.provider
      logger.debug('Fetched LLM config:', data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch LLM config'
      logger.error('Failed to fetch config:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function updateConfig(newConfig: Partial<LLMConfig>): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/llm/config', newConfig)
      config.value = data
      logger.debug('Updated LLM config:', data)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update LLM config'
      logger.error('Failed to update config:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function testConnection(provider?: string): Promise<ConnectionTestResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post(
        '/api/llm/test_connection',
        provider ? { provider } : {}
      )
      logger.debug('Connection test result:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection test failed'
      logger.error('Connection test error:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function fetchModels(provider?: string): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const params = provider ? `?provider=${provider}` : ''
      const data = await ApiClient.get(`/api/llm/models${params}`)
      models.value = data.models || []
      logger.debug('Fetched models:', models.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch models'
      logger.error('Failed to fetch models:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function getCurrentProvider(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/llm/current')
      currentProvider.value = data.provider
      logger.debug('Current provider:', data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to get current provider'
      logger.error('Failed to get current provider:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function switchProvider(provider: string, model?: string): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post(
        '/api/llm/provider',
        { provider, model }
      )
      if (data.success) {
        currentProvider.value = provider
        logger.debug('Switched to provider:', provider)
        return true
      }
      return false
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to switch provider'
      logger.error('Failed to switch provider:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function fetchProviders(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/llm_providers/providers')
      providers.value = data.providers || []
      logger.debug('Fetched providers:', providers.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch providers'
      logger.error('Failed to fetch providers:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function testProviderConnection(providerName: string): Promise<ConnectionTestResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post(
        `/api/llm_providers/providers/${providerName}/test`,
        {}
      )
      logger.debug('Provider test result:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Provider test failed'
      logger.error('Provider test error:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      Promise.all([fetchProviders(), fetchConfig()])
    }
  })

  return {
    // State
    config,
    providers,
    models,
    currentProvider,
    isLoading,
    error,

    // Methods
    fetchConfig,
    updateConfig,
    testConnection,
    fetchModels,
    getCurrentProvider,
    switchProvider,
    fetchProviders,
    testProviderConnection,
  }
}

export default useLlmConfig
