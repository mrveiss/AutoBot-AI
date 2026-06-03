// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { ChatMessage } from '@/types/api'
import { useAvailableModels } from '@/composables/useAvailableModels'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useContextWindow')

export interface ContextWindowState {
  tokensUsed: ComputedRef<number>
  contextWindow: ComputedRef<number>
  usagePercent: ComputedRef<number>
  isWarning: ComputedRef<boolean>
  isCritical: ComputedRef<boolean>
  hasData: ComputedRef<boolean>
}

// Known context windows for common models when live data is unavailable
const FALLBACK_CONTEXT_WINDOWS: Record<string, number> = {
  'claude-3-opus': 200_000,
  'claude-3-sonnet': 200_000,
  'claude-3-haiku': 200_000,
  'claude-3-5-sonnet': 200_000,
  'claude-sonnet': 200_000,
  'claude-opus': 200_000,
  'gpt-4o': 128_000,
  'gpt-4': 128_000,
  'gpt-4-turbo': 128_000,
  'gpt-3.5-turbo': 16_385,
  'gpt-3.5': 16_385,
  'llama3': 8_192,
  'llama3.1': 131_072,
  'llama3.2': 131_072,
  'mistral': 32_768,
  'mixtral': 32_768,
  'gemma': 8_192,
  'gemma2': 8_192,
  'qwen': 32_768,
  'deepseek': 32_768,
  'phi3': 4_096,
}

function lookupFallback(modelName: string): number {
  const lower = modelName.toLowerCase()
  for (const [key, value] of Object.entries(FALLBACK_CONTEXT_WINDOWS)) {
    if (lower.startsWith(key) || lower.includes(key)) return value
  }
  return 0
}

export function useContextWindow(
  messages: Ref<ChatMessage[]> | ComputedRef<ChatMessage[]>,
  modelName: Ref<string> | ComputedRef<string>,
): ContextWindowState {
  const { models, fetchModels } = useAvailableModels()

  // Fetch model list once if empty
  fetchModels().catch((err) => logger.warn('Failed to fetch models for context window:', err))

  const tokensUsed = computed<number>(() => {
    return messages.value.reduce((sum, msg) => {
      return sum + (msg.metadata?.tokens ?? 0)
    }, 0)
  })

  const contextWindow = computed<number>(() => {
    const name = modelName.value
    if (!name) return 0
    const found = models.value.find(
      (m) => m.name === name || m.name.toLowerCase() === name.toLowerCase(),
    )
    if (found?.context_window) return found.context_window
    return lookupFallback(name)
  })

  const usagePercent = computed<number>(() => {
    if (!contextWindow.value || !tokensUsed.value) return 0
    return Math.min(100, (tokensUsed.value / contextWindow.value) * 100)
  })

  const isWarning = computed<boolean>(() => usagePercent.value >= 80)
  const isCritical = computed<boolean>(() => usagePercent.value >= 95)

  const hasData = computed<boolean>(() => tokensUsed.value > 0 && contextWindow.value > 0)

  return { tokensUsed, contextWindow, usagePercent, isWarning, isCritical, hasData }
}
