// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { computed, ref, watch, type Ref } from 'vue'

/**
 * Pending-approval state, kept per chat (#21357, #680).
 *
 * The flag used to be one global boolean, so an approval raised or resolved in a chat that was not open
 * overwrote the open chat's. Now each chat carries its own; `hasPendingApproval` is the OPEN chat's, which is what
 * the polling guards read. Omitting `sessionId` targets the open chat.
 */
export function usePendingApproval(currentSessionId: Ref<string | null>, sessions: Ref<{ id: string }[]>) {
  const pendingSessionIds = ref<Set<string>>(new Set())

  const hasPendingApproval = computed(
    () => currentSessionId.value !== null && pendingSessionIds.value.has(currentSessionId.value)
  )

  function isPendingApproval(sessionId: string): boolean {
    return pendingSessionIds.value.has(sessionId)
  }

  function setPendingApproval(pending: boolean, sessionId?: string): void {
    const id = sessionId ?? currentSessionId.value
    if (!id) return
    if (pending && !sessions.value.some(x => x.id === id)) return // a late event for a deleted chat adds nothing
    const next = new Set(pendingSessionIds.value)
    if (pending) next.add(id)
    else next.delete(id)
    pendingSessionIds.value = next
  }

  /** A chat that is deleted, cleared or replaced by a sync takes its flag with it. */
  watch(
    () => sessions.value.map(s => s.id),
    ids => {
      const live = new Set(ids)
      const kept = [...pendingSessionIds.value].filter(id => live.has(id))
      if (kept.length !== pendingSessionIds.value.size) pendingSessionIds.value = new Set(kept)
    },
    { flush: 'sync' }
  )

  return { hasPendingApproval, isPendingApproval, setPendingApproval }
}
