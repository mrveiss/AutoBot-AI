// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Memoised, sanitised message HTML (#1312, #19118, #21771). Moved out of ChatMessages.vue.
 * Key: message id + content length (a cheap proxy for content identity), oldest entry evicted first.
 */
import { formatChatMessageHtml } from '@/utils/chatMessageFormat'
import { sanitizeChatHtml } from '@/utils/sanitize'

export const FORMAT_CACHE_MAX = 500

export function createMessageFormatter(max: number = FORMAT_CACHE_MAX) {
  const cache = new Map<string, string>()

  /** Sanitised at the sink: every v-html binding reads this function. */
  return function formatMessageContent(content: string, messageId?: string): string {
    const key = messageId ? `${messageId}:${content.length}` : content
    const cached = cache.get(key)
    if (cached !== undefined) return cached

    const result = sanitizeChatHtml(formatChatMessageHtml(content))
    if (cache.size >= max) {
      const oldest = cache.keys().next().value
      if (oldest !== undefined) cache.delete(oldest)
    }
    cache.set(key, result)
    return result
  }
}

/** One shared formatter per page: rows and content blocks hit the same cache. */
export const formatMessageContent = createMessageFormatter()
