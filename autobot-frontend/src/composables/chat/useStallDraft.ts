// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The answer a person is typing to a stalled turn's question, kept by message id (#21793).
 *
 * The chat list is virtualised, so scrolling a question card out of the window unmounts it; a draft held in the
 * card's own ref went with it. Here it outlives the card and is restored when the card mounts again. Bounded, oldest
 * first, so a long session of unanswered questions cannot grow it without end.
 */
import { computed, reactive, type WritableComputedRef } from 'vue'

export const MAX_STALL_DRAFTS = 100

const drafts = reactive(new Map<string, string>())

/** Remember `text` as the draft for `messageId`; empty text forgets it. Evicts the oldest draft past the bound. */
export function setStallDraft(messageId: string, text: string): void {
  drafts.delete(messageId) // re-insert so the most recently typed draft is the last to be evicted
  if (text) drafts.set(messageId, text)
  while (drafts.size > MAX_STALL_DRAFTS) {
    const oldest = drafts.keys().next().value
    if (oldest === undefined) return
    drafts.delete(oldest)
  }
}

export function getStallDraft(messageId: string): string {
  return drafts.get(messageId) ?? ''
}

/** A v-model-able draft for one question card, read and written through the shared store. */
export function useStallDraft(messageId: () => string): WritableComputedRef<string> {
  return computed({
    get: () => getStallDraft(messageId()),
    set: (text: string) => setStallDraft(messageId(), text),
  })
}
