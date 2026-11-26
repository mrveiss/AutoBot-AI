// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Keeps a list honest after a proposed deletion is approved (#21886).
 *
 * STOPGAP. The server publishes `approval_approved` on the `global` live-event channel when the approval is decided,
 * BEFORE it runs the approved deletion (`approval_gate_service.py`, `_transition` then `run_post_approval_actions`), and
 * publishes nothing when the deletion finishes or is refused. #21946 adds the proper completion event; this module
 * is replaced by it. Until then, on `approval_approved` for a watched `approval_id` the rows are dropped at once and
 * the list is re-read at each of `RESYNC_DELAYS_MS` until a read shows the deletion settled (`resync` resolves true),
 * so a refused or failed deletion puts its rows back and a slow one is still observed after the first read. A
 * deletion that finishes by the first read costs one read. A rejected, withdrawn or expired approval drops the watch
 * without touching the list. A watch also expires after `WATCH_TTL_MS`, so no entry outlives a page that never
 * receives the event (navigation, a missed WebSocket).
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
/** When, after the approval event, the list is re-read (the server runs the deletion right after publishing it). */
export const RESYNC_DELAYS_MS = [3000, 10000, 30000]
/** How long a watch waits for its approval to be decided before it is forgotten. */
export const WATCH_TTL_MS = 15 * 60 * 1000

interface Watch {
  onApproved: () => void
  resync: () => Promise<boolean>
  expiry: ReturnType<typeof setTimeout>
}

const waiting = new Map<string, Watch>()
let unsubscribe: (() => void) | null = null

function forget(approvalId: string): Watch | undefined {
  const watch = waiting.get(approvalId)
  if (!watch) return undefined
  clearTimeout(watch.expiry)
  waiting.delete(approvalId)
  if (waiting.size === 0) {
    unsubscribe?.()
    unsubscribe = null
  }
  return watch
}

function reconcile(resync: () => Promise<boolean>, attempt = 0): void {
  if (attempt >= RESYNC_DELAYS_MS.length) return
  setTimeout(async () => {
    const settled = await resync().catch(() => false)
    if (!settled) reconcile(resync, attempt + 1)
  }, RESYNC_DELAYS_MS[attempt])
}

function onEvent(event: LiveEvent): void {
  const id = event.payload?.approval_id
  if (typeof id !== 'string' || !DECIDED_EVENTS.has(event.event_type)) return
  const watch = forget(id)
  if (watch && event.event_type === 'approval_approved') {
    watch.onApproved()
    reconcile(watch.resync)
  }
}

/** Run `onApproved` now, then `resync` until it resolves true, when approval `approvalId` is approved. */
export function watchApprovedDelete(approvalId: string, onApproved: () => void, resync: () => Promise<boolean>): void {
  forget(approvalId)
  const expiry = setTimeout(() => forget(approvalId), WATCH_TTL_MS)
  waiting.set(approvalId, { onApproved, resync, expiry })
  if (!unsubscribe) unsubscribe = liveEventService.subscribe(GLOBAL_CHANNEL, onEvent)
}
