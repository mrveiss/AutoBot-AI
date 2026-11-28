// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * REST reconcile for session presence (#16754).
 *
 * The presence WebSocket pushes joins and leaves, but a client that connects
 * late, reconnects or misses a frame only learns who is online from
 * `GET /sessions/{id}/presence`. This applies that snapshot to the same
 * presence map the socket feeds, so the collaboration panel has one source.
 *
 * The contract types `online_users` as `string[]` (annotated in #18447). The
 * elements are still narrowed, so a malformed payload can never put a non-id
 * into the presence map.
 */
import { apiService } from '@/services/api'
import { createLogger } from '@/utils/debugUtils'
import type { UserPresence } from '@/composables/useSessionCollaboration'

const logger = createLogger('sessionPresenceSync')

export async function syncOnlineUsers(
  currentSessionId: () => string | null,
  presence: Map<string, UserPresence>,
  upsert: (userId: string, patch: Partial<UserPresence>) => void,
): Promise<void> {
  const sessionId = currentSessionId()
  if (!sessionId) return
  try {
    const { online_users } = await apiService.getSessionPresence(sessionId)
    if (currentSessionId() !== sessionId) return // left or switched while in flight
    const online = new Set(online_users.filter((u): u is string => typeof u === 'string'))
    for (const userId of presence.keys()) {
      if (!online.has(userId)) presence.delete(userId)
    }
    for (const userId of online) {
      if (!presence.has(userId)) upsert(userId, {})
    }
  } catch (error) {
    logger.error('Failed to sync session presence:', error)
  }
}
