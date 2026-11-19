// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** Pure formatting helpers for the chat response stream, split out of ChatController (#21357 size ceiling). */

import i18n from '@/i18n'
import { stripProtocolTagsForDisplay } from '@/utils/llmProtocolTags'

/**
 * Issue #691: Extract a meaningful preview from streaming content.
 * Used to display real LLM content in the typing indicator instead of placeholder text.
 *
 * @param content - The full streaming content so far
 * @param messageType - The type of message (thought, planning, response, etc.)
 * @returns A short preview string (max 80 chars) or empty string if no preview available
 */
export function extractStreamingPreview(content: string, messageType?: string): string {
  if (!content || content.length < 3) return ''

  // Strip internal tags that shouldn't be shown to users
  // Handles complete tags and partial/truncated tags from streaming (e.g. [/THO)
  // The two adjacent case-variant replaces this line replaced were the fork
  // made visible: one defect, patched here and nowhere else (#18065).
  const preview = stripProtocolTagsForDisplay(content)

  if (!preview) return ''

  // Get the last meaningful portion (most recent thinking)
  // Take the last sentence or last 80 characters
  // Issue #691: Filter empty sentences to avoid blank preview when content ends with punctuation
  const sentences = preview.split(/[.!?]\s+/)
  const lastSentence = sentences.filter(s => s.trim()).pop() || preview

  // Create a concise preview
  let result = lastSentence.trim()
  if (result.length > 80) {
    // Find a good breaking point (word boundary)
    result = result.substring(0, 77)
    const lastSpace = result.lastIndexOf(' ')
    if (lastSpace > 50) {
      result = result.substring(0, lastSpace)
    }
    result += '...'
  }

  // Add type-specific prefix for context
  if (messageType === 'thought') {
    return i18n.global.t('chat.streamPreview.thought', { text: result })
  } else if (messageType === 'planning') {
    return i18n.global.t('chat.streamPreview.planning', { text: result })
  }

  return result
}

/**
 * Map backend message type to frontend message type.
 * Agent Zero Pattern: Centralized type mapping for consistency.
 */
export function mapMessageType(
  backendType?: string,
  metadataType?: string
): 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | 'human_question' | undefined {
  const type = backendType || metadataType
  if (!type) return 'response'

  if (type === 'human_question') return type // #21022
  if (type === 'thought' || type.includes('thought')) return 'thought'
  if (type.includes('planning')) return 'planning'
  if (type.includes('debug')) return 'debug'
  if (type.includes('utility')) return 'utility'
  if (type.includes('source')) return 'sources'
  if (type.includes('json')) return 'json'
  if (type === 'response' || type === 'llm_response' || type === 'llm_response_chunk') return 'response'

  // Default to response for unknown types
  return 'response'
}
