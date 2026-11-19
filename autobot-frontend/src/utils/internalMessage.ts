// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * A backend bookkeeping message (e.g. the `segment_complete` identity marker, #21846)
 * is flagged `metadata.internal`. It is never shown, whichever path delivered it.
 */
export function isInternalMessage(message: { metadata?: Record<string, unknown> | null } | null | undefined): boolean {
  return message?.metadata?.internal === true
}

/** The messages a chat view may show: everything except backend-internal bookkeeping. */
export function visibleMessages<T extends { metadata?: Record<string, unknown> | null }>(messages: readonly T[]): T[] {
  return messages.filter((message) => !isInternalMessage(message))
}
