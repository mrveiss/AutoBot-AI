// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { watch, ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import type { ChatMessage } from '@/types/api'
import { useContextWindow, type ContextWindowState } from './useContextWindow'
import { createLogger } from '@/utils/debugUtils'
import { useApiClient } from '@/plugins/api'

const logger = createLogger('useContextOverflowProtection')

export interface ContextOverflowProtectionOptions {
  sessionId: Ref<string | null> | ComputedRef<string | null>
  messages: Ref<ChatMessage[]>
  modelName: Ref<string> | ComputedRef<string>
  enabled?: Ref<boolean> | ComputedRef<boolean>
  warningThreshold?: number // Default: 80%
  summarizationThreshold?: number // Default: 85%
  targetSummaryLength?: number // Default: 500 tokens
  onSummarize?: (summary: ChatMessage) => void
}

export interface ContextOverflowProtectionState {
  isProtectionActive: ComputedRef<boolean>
  isSummarizing: Ref<boolean>
  lastSummarizedAt: Ref<Date | null>
  summarizedMessageCount: Ref<number>
  contextWindowState: ContextWindowState
}

/**
 * Context overflow protection composable (GH#9043)
 *
 * Automatically summarizes early conversation history when approaching
 * the model's context window limit, enabling a rolling window approach
 * without losing essential context.
 *
 * @example
 * ```ts
 * const { isProtectionActive, isSummarizing, contextWindowState } =
 *   useContextOverflowProtection({
 *     sessionId: computed(() => currentSession.value?.id ?? null),
 *     messages: computed(() => currentSession.value?.messages ?? []),
 *     modelName: computed(() => settings.value.model),
 *     onSummarize: (summary) => {
 *       // Replace old messages with summary
 *       currentSession.value.messages = [summary, ...recentMessages]
 *     }
 *   })
 * ```
 */
export function useContextOverflowProtection(
  options: ContextOverflowProtectionOptions,
): ContextOverflowProtectionState {
  const api = useApiClient()

  // State
  const isSummarizing = ref(false)
  const lastSummarizedAt = ref<Date | null>(null)
  const summarizedMessageCount = ref(0)

  // Get context window state from useContextWindow
  const contextWindowState = useContextWindow(options.messages, options.modelName)

  // Configuration
  const warningThreshold = options.warningThreshold ?? 80
  const summarizationThreshold = options.summarizationThreshold ?? 85
  const targetSummaryLength = options.targetSummaryLength ?? 500
  const enabled = options.enabled ?? ref(true)

  // Computed
  const isProtectionActive = computed(() => {
    return (
      enabled.value &&
      contextWindowState.usagePercent.value >= warningThreshold &&
      !isSummarizing.value
    )
  })

  /**
   * Summarize the earliest messages to free up context window space
   */
  async function summarizeEarliestMessages(): Promise<void> {
    const sessionId = options.sessionId.value
    if (!sessionId) {
      logger.warn('Cannot summarize: no session ID')
      return
    }

    const messages = options.messages.value
    if (messages.length < 5) {
      logger.info('Too few messages to summarize (need at least 5)')
      return
    }

    isSummarizing.value = true

    try {
      // Determine how many messages to summarize
      // Target: reduce context usage to ~50% to give room for new messages
      const currentUsage = contextWindowState.usagePercent.value
      const targetUsage = 50
      const usageReduction = currentUsage - targetUsage

      // Estimate: reduce by removing the oldest ~40% of messages
      const messagesToSummarizeCount = Math.max(
        3,
        Math.floor(messages.length * (usageReduction / 100))
      )

      // Get the oldest messages (excluding system messages)
      const oldestMessages = messages
        .filter(msg => msg.role !== 'system')
        .slice(0, messagesToSummarizeCount)

      if (oldestMessages.length === 0) {
        logger.warn('No user/assistant messages to summarize')
        return
      }

      const messageIds = oldestMessages
        .map(msg => msg.message_id)
        .filter((id): id is string => !!id)

      if (messageIds.length === 0) {
        logger.warn('No message IDs found for summarization')
        return
      }

      logger.info(
        'Summarizing %d messages (context at %d%%, targeting %d%%)',
        messageIds.length,
        currentUsage,
        targetUsage
      )

      // Call backend summarization endpoint
      const response = await api.post<{
        summary: string
        original_message_count: number
        summary_token_count: number
        timestamp: string
      }>('/chat/summarize', {
        session_id: sessionId,
        message_ids: messageIds,
        target_length: targetSummaryLength,
      })

      // Create summary message
      const summaryMessage: ChatMessage = {
        role: 'system',
        content: `[Context Summary] The following summarizes the conversation from ${oldestMessages[0].timestamp || 'earlier'}:\n\n${response.summary}`,
        message_id: `summary_${Date.now()}`,
        timestamp: response.timestamp,
        metadata: {
          is_summary: true,
          original_message_count: response.original_message_count,
          summary_token_count: response.summary_token_count,
          summarized_message_ids: messageIds,
        },
      }

      // Update state
      lastSummarizedAt.value = new Date()
      summarizedMessageCount.value += response.original_message_count

      logger.info(
        'Summary complete: %d messages → %d tokens',
        response.original_message_count,
        response.summary_token_count || 0
      )

      // Notify caller to replace messages
      if (options.onSummarize) {
        options.onSummarize(summaryMessage)
      }

    } catch (error) {
      logger.error('Failed to summarize messages:', error)
      throw error
    } finally {
      isSummarizing.value = false
    }
  }

  // Watch for context overflow and trigger summarization
  watch(
    () => contextWindowState.usagePercent.value,
    (usagePercent) => {
      if (
        enabled.value &&
        usagePercent >= summarizationThreshold &&
        !isSummarizing.value
      ) {
        logger.warn(
          'Context window at %d%% (threshold: %d%%) — triggering auto-summarization',
          usagePercent,
          summarizationThreshold
        )
        summarizeEarliestMessages().catch((error) => {
          logger.error('Auto-summarization failed:', error)
        })
      }
    },
    { immediate: false }
  )

  return {
    isProtectionActive,
    isSummarizing,
    lastSummarizedAt,
    summarizedMessageCount,
    contextWindowState,
  }
}
