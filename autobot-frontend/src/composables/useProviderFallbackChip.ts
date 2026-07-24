// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Provider-fallback chat-chip correlation composable (#11997 / umbrella #11994)
 *
 * Consumes the canonical PROVIDER_FALLBACK live event (#11995) and correlates
 * each fallback decision to the specific assistant chat message it produced, so
 * the chat view can render an opt-in inline chip on that message.
 *
 * Reuses the same live-event seam as the admin observability panel (#11996):
 * `useProviderFallbackApi().subscribeToFallbackEvents` — no duplicate
 * subscription, no new backend.
 *
 * Correlation key: `payload.conversation_id` (the frontend chat/session id is
 * propagated to the backend as the conversation id — see ChatController). The
 * caller supplies a resolver that maps a conversation id to the id of the
 * assistant message the fallback answered (typically the last assistant message
 * of that conversation), so the chip stays pinned to that message even after
 * later successful (non-fallback) responses arrive.
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { reactive } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useProviderFallbackApi } from '@/composables/useProviderFallbackApi'
import type { ProviderFallbackPayload } from '@/constants/providerFallbackEvents'

const logger = createLogger('useProviderFallbackChip')

/**
 * Shared reactive map of assistant message id → the fallback decision that
 * produced it. Module-level so every chat message renders from one source of
 * truth regardless of which component instance started the subscription.
 */
const fallbackByMessageId = reactive(new Map<string, ProviderFallbackPayload>())

/** Maps a fallback event's conversation id to the target assistant message id. */
export type ResolveTargetMessageId = (conversationId: string) => string | null

export interface UseProviderFallbackChipReturn {
  /**
   * Start correlating live PROVIDER_FALLBACK events to chat messages.
   * @param resolve - resolves a conversation id to the assistant message id the
   *   fallback answered (return `null` to skip messages not currently rendered).
   * @returns an unsubscribe function.
   */
  start: (resolve: ResolveTargetMessageId) => () => void
  /** Fallback decision that produced a message, or `null` if none. */
  getFallbackForMessage: (messageId: string) => ProviderFallbackPayload | null
  /** Reactive map of message id → fallback payload (read-only usage). */
  fallbackByMessageId: Map<string, ProviderFallbackPayload>
}

export function useProviderFallbackChip(): UseProviderFallbackChipReturn {
  const { subscribeToFallbackEvents } = useProviderFallbackApi()

  function start(resolve: ResolveTargetMessageId): () => void {
    return subscribeToFallbackEvents((payload: ProviderFallbackPayload) => {
      const messageId = resolve(payload.conversation_id)
      if (!messageId) {
        logger.debug('PROVIDER_FALLBACK: no target message for conversation', payload.conversation_id)
        return
      }
      fallbackByMessageId.set(messageId, payload)
    })
  }

  function getFallbackForMessage(messageId: string): ProviderFallbackPayload | null {
    return fallbackByMessageId.get(messageId) ?? null
  }

  return { start, getFallbackForMessage, fallbackByMessageId }
}
