// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { computed, ref, type Ref } from 'vue'

/**
 * Pending-approval state, kept per chat (#21357, #680).
 *
 * The flag used to be one global boolean, so an approval raised or resolved in a chat that was not open
 * overwrote the open chat's. Now each chat carries its own; `hasPendingApproval` is the OPEN chat's, which is what
 * the polling guards read. Omitting `sessionId` targets the open chat.
 */
export function usePendingApproval(currentSessionId: Ref<string | null>) {
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
    const next = new Set(pendingSessionIds.value)
    if (pending) next.add(id)
    else next.delete(id)
    pendingSessionIds.value = next
  }

  return { hasPendingApproval, isPendingApproval, setPendingApproval }
}
