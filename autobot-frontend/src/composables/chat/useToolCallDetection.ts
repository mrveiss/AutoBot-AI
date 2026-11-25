// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * TOOL_CALL marker detection, moved unchanged out of ChatMessages.vue (#18243).
 *
 * DISABLED as an automatic watcher: it produced duplicate approval dialogs for auto-approved SAFE
 * commands. Only `requires_approval` metadata from the backend drives the approval UI. ChatMessages
 * exposes `detectToolCalls` so the path stays reachable instead of being deleted.
 */
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useToolCallDetection')
const TOOL_CALL_REGEX = /<TOOL_CALL\s+name="execute_command"\s+params='({.*?})'>(.*?)<\/TOOL_CALL>/gs
const RECENT_ASSISTANT_MESSAGES = 10

export interface DetectedToolCall {
  command: string
  host: string
  purpose: string
  params: Record<string, unknown>
  terminal_session_id: string | null
}

/** The session id may sit on a recent streaming chunk instead of the message with the marker. */
export function findTerminalSessionId(message: ChatMessage, recent: ChatMessage[]): string | null {
  const own = (message.metadata?.terminal_session_id as string) || null
  if (own) return own
  const assistants = recent.filter((m) => m.sender === 'assistant').reverse().slice(0, RECENT_ASSISTANT_MESSAGES)
  for (const msg of assistants) {
    const found = msg.metadata?.terminal_session_id as string | null
    if (found) return found
  }
  logger.warn('No terminal_session_id found in recent messages')
  return null
}

export function useToolCallDetection(emit: (toolCall: DetectedToolCall) => void) {
  const store = useChatStore()

  function detectToolCalls(message: ChatMessage) {
    for (const match of message.content.matchAll(TOOL_CALL_REGEX)) {
      try {
        const params = JSON.parse(match[1])
        const purpose = match[2].trim()
        logger.debug('TOOL_CALL detected:', { command: params.command, host: params.host, purpose })
        emit({
          command: params.command,
          host: params.host || 'main',
          purpose,
          params,
          terminal_session_id: findTerminalSessionId(message, store.currentMessages),
        })
      } catch (error) {
        logger.error('Failed to parse TOOL_CALL:', error)
      }
    }
  }

  return { detectToolCalls }
}
