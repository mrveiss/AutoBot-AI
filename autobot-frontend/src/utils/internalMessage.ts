// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { withoutRepeatedNarration } from './replyRedundancy'

/**
 * A backend bookkeeping message (e.g. the `segment_complete` identity marker, #21846)
 * is flagged `metadata.internal`. It is never shown, whichever path delivered it.
 */
export function isInternalMessage(message: { metadata?: Record<string, unknown> | null } | null | undefined): boolean {
  return message?.metadata?.internal === true
}

/**
 * The messages a chat view may show: everything except backend-internal bookkeeping and narration that a later
 * `respond` answer of the same turn repeats (#21880: the live view matches a reload).
 */
export function visibleMessages<
  T extends { metadata?: Record<string, unknown> | null; sender?: string; text?: string; content?: string }
>(messages: readonly T[]): T[] {
  return withoutRepeatedNarration(messages.filter((message) => !isInternalMessage(message)))
}

/** The backend records `unknown` when it cannot say which model wrote a reply (#21881); the chat shows no badge for it. */
export const UNKNOWN_MODEL = 'unknown'

/** The model name to show for a message's `metadata`, or `''` when there is none or it is unknown. */
export function shownModel(metadata: Record<string, unknown> | null | undefined): string {
  const model = metadata?.model
  return typeof model === 'string' && model !== '' && model !== UNKNOWN_MODEL ? model : ''
}
