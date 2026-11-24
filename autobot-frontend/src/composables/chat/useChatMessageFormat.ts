// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Memoised message HTML (#1312, #21771). Moved out of ChatMessages.vue.
 * Key: message id; a hit needs the same full content too (an equal-length edit must re-format). Oldest entry evicted first.
 * The result is NOT sanitised: the `v-html` sink wraps it in `sanitizeChatHtml` in the same file (#19118).
 */
import { formatChatMessageHtml } from '@/utils/chatMessageFormat'

export const FORMAT_CACHE_MAX = 500

export function createMessageFormatter(max: number = FORMAT_CACHE_MAX) {
  const cache = new Map<string, { content: string; html: string }>()

  /** Formatted HTML for one message; the caller sanitises it at its `v-html` sink. */
  return function formatMessageContent(content: string, messageId?: string): string {
    const key = messageId ?? content
    const cached = cache.get(key)
    if (cached !== undefined && cached.content === content) return cached.html

    const result = formatChatMessageHtml(content)
    if (!cache.has(key) && cache.size >= max) {
      const oldest = cache.keys().next().value
      if (oldest !== undefined) cache.delete(oldest)
    }
    cache.set(key, { content, html: result })
    return result
  }
}

/** One shared formatter per page: rows and content blocks hit the same cache. */
export const formatMessageContent = createMessageFormatter()
