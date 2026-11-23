// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Which narration is a repeat of the final `respond` answer (#21880).
 *
 * The same rule as the backend (`autobot-backend/chat_workflow/reply_persistence.py`), pinned by the one case
 * table `replyRedundancyCases.json`. Both texts are normalised (Unicode fold, lower case, every run of
 * non-letters and non-digits, underscore included, reduced to one space). A narration is redundant when its
 * tokens are a contiguous run of whole tokens of the `respond` text ("art" is not in "party"). Narration that says
 * more than the answer is kept.
 */

import { stripProtocolTagsForDisplay } from './llmProtocolTags'
import { RESPOND_TOOL_TYPE } from './replyRedundancyConstants'

type Entry = { sender?: string; text?: string; content?: string; metadata?: Record<string, unknown> | null }

/** The text folded for comparison. A tool call is a step, not words: whole calls and markers go first (#21880). */
export function normalizeReply(text: string | null | undefined): string {
  return stripProtocolTagsForDisplay(text ?? '')
    .normalize('NFKC')
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean)
    .join(' ')
}

/** True when *narration* repeats *answer*: its tokens are a contiguous run of the answer's. */
export function isRedundantNarration(narration: string, answer: string): boolean {
  const n = normalizeReply(narration)
  return n !== '' && ` ${normalizeReply(answer)} `.includes(` ${n} `)
}

const textOf = (m: Entry): string => m.text ?? m.content ?? ''
const isRespond = (m: Entry): boolean => m.metadata?.message_type === RESPOND_TOOL_TYPE

/**
 * *messages* without the narration that a later `respond` answer of the same turn repeats, so the live view
 * matches a reload. A turn runs from a user message to the next.
 */
export function withoutRepeatedNarration<T extends Entry>(messages: readonly T[]): T[] {
  const dropped = new Set<T>()
  let turn: T[] = []
  for (const message of messages) {
    if (message.sender === 'user') {
      turn = []
    } else if (message.sender === 'assistant' && isRespond(message)) {
      turn.filter((m) => !isRespond(m) && isRedundantNarration(textOf(m), textOf(message))).forEach((m) => dropped.add(m))
    } else if (message.sender === 'assistant') {
      turn.push(message)
    }
  }
  return dropped.size ? messages.filter((m) => !dropped.has(m)) : [...messages]
}
