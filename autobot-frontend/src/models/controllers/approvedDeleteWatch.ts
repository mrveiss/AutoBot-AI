// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Runs a callback when a proposed deletion is APPROVED (#21886), so a list that still shows the rows does not stay stale.
 *
 * The signal is the `approval_approved` event on the `global` live-event channel, the same one
 * `useApprovalGatesStore` listens to; its payload carries the `approval_id` the proposal reply returned. The event
 * is published when the approval is decided, just before the server runs the approved deletion, so a refetch on it
 * can race the deletion: the callback should update local state, not reload. A rejected, withdrawn or expired
 * approval drops the watch without running it.
 */
import liveEventService, { type LiveEvent } from '@/services/LiveEventService'

const GLOBAL_CHANNEL = 'global'
const DECIDED_EVENTS = new Set([
  'approval_approved',
  'approval_rejected',
  'approval_revision_requested',
  'approval_withdrawn',
  'approval_expired',
])

const waiting = new Map<string, () => void>()
let unsubscribe: (() => void) | null = null

function onEvent(event: LiveEvent): void {
  const id = event.payload?.approval_id
  if (typeof id !== 'string' || !DECIDED_EVENTS.has(event.event_type)) return
  const onApproved = waiting.get(id)
  if (!onApproved) return
  waiting.delete(id)
  if (event.event_type === 'approval_approved') onApproved()
  if (waiting.size === 0) {
    unsubscribe?.()
    unsubscribe = null
  }
}

/** Call `onApproved` once when approval `approvalId` is approved; forget it when it is decided otherwise. */
export function watchApprovedDelete(approvalId: string, onApproved: () => void): void {
  waiting.set(approvalId, onApproved)
  if (!unsubscribe) unsubscribe = liveEventService.subscribe(GLOBAL_CHANNEL, onEvent)
}
