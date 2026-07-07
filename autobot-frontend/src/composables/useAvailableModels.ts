// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useAvailableModels — dynamic LLM model list from the live system (#3280).
 *
 * Fetches GET /api/models/available which returns models from all configured
 * providers (Ollama, OpenAI, Anthropic, vLLM) with provider, context_window,
 * and capabilities metadata. Results are cached server-side for 60 seconds.
 */

import { ref, computed } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from './useLoadingState'

const logger = createLogger('useAvailableModels')

// ===== Type Definitions =====

export interface AvailableModel {
  name: string
  provider: string
  available: boolean
  context_window: number
  capabilities: string[]
}

export interface AvailableModelsResult {
  models: AvailableModel[]
  total_count: number
  providers_queried: string[]
  providers_errored: string[]
  cached: boolean
}

// ===== Composable =====

export function useAvailableModels() {
  const models = ref<AvailableModel[]>([])
  const providersQueried = ref<string[]>([])
  const providersErrored = ref<string[]>([])
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  const modelNames = computed(() => models.value.map((m) => m.name))

  const availableModelNames = computed(() =>
    models.value.filter((m) => m.available).map((m) => m.name),
  )

  const hasErrors = computed(() => providersErrored.value.length > 0)

  async function fetchModels(): Promise<void> {
    error.value = null
    return wrap(async () => {
      try {
        const data = await ApiClient.get<AvailableModelsResult>(
          `${getApiBase()}/models/available`,
        )
        models.value = data.models ?? []
        providersQueried.value = data.providers_queried ?? []
        providersErrored.value = data.providers_errored ?? []
        logger.debug(
          'Fetched %d models from providers: %s',
          models.value.length,
          data.providers_queried?.join(', '),
        )
        if (data.providers_errored?.length) {
          logger.warn('Providers with errors: %s', data.providers_errored.join(', '))
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        error.value = msg
        logger.error('Failed to fetch available models: %s', msg)
      }
    })
  }

  return {
    models,
    modelNames,
    availableModelNames,
    providersQueried,
    providersErrored,
    isLoading,
    error,
    hasErrors,
    fetchModels,
  }
}
