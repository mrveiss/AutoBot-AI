// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useChatModelSelection — per-request/per-conversation model & provider
 * override for the chat composer (#11585).
 *
 * Wraps useAvailableModels (GET /api/models/available) and holds the user's
 * model choice. The empty string means "auto" — no override is sent and the
 * backend uses its per-conversation/global default. When a model is chosen,
 * its provider is derived from the live model metadata so the backend can
 * validate and pin it via the provider-registry seam.
 *
 * The choice is persisted in localStorage so it survives reloads; the backend
 * additionally pins the provider per conversation once a message is sent.
 */

import { ref, computed, watch } from 'vue'
import { useAvailableModels, type AvailableModel } from '../useAvailableModels'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useChatModelSelection')

const STORAGE_KEY = 'autobot-chat-model-override'

/** '' = auto (no override sent). Module-level so all composer instances agree. */
const selectedModel = ref<string>('')
let _initialized = false

function loadPersistedSelection(): void {
  try {
    selectedModel.value = localStorage.getItem(STORAGE_KEY) ?? ''
  } catch (err) {
    logger.warn('Failed to load persisted model selection:', err)
  }
}

function persistSelection(model: string): void {
  try {
    if (model) {
      localStorage.setItem(STORAGE_KEY, model)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch (err) {
    logger.warn('Failed to persist model selection:', err)
  }
}

export interface ModelOverrideFields {
  model?: string
  provider?: string
}

export function useChatModelSelection() {
  const { models, isLoading, error, fetchModels } = useAvailableModels()

  if (!_initialized) {
    _initialized = true
    loadPersistedSelection()
    watch(selectedModel, (model) => {
      persistSelection(model)
      logger.debug('Chat model override set to: %s', model || '(auto)')
    })
  }

  /** Picker options: live models plus the persisted choice (stays selectable
   *  even if its provider is briefly down — mirrors useModelPicker). */
  const pickerModels = computed<AvailableModel[]>(() => {
    if (!selectedModel.value || models.value.some((m) => m.name === selectedModel.value)) {
      return models.value
    }
    return [
      ...models.value,
      { name: selectedModel.value, provider: '', available: false, context_window: 0, capabilities: [] },
    ]
  })

  /** Provider of the selected model, derived from live metadata. */
  const selectedProvider = computed<string>(() => {
    if (!selectedModel.value) return ''
    return models.value.find((m) => m.name === selectedModel.value)?.provider ?? ''
  })

  /** Request fields to spread into sendMessage options — empty when auto. */
  const overrideFields = computed<ModelOverrideFields>(() => {
    if (!selectedModel.value) return {}
    const fields: ModelOverrideFields = { model: selectedModel.value }
    if (selectedProvider.value) fields.provider = selectedProvider.value
    return fields
  })

  return {
    models,
    pickerModels,
    selectedModel,
    selectedProvider,
    overrideFields,
    isLoading,
    error,
    fetchModels,
  }
}
