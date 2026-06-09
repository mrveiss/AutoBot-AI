// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useLLCNotifications (GH#8255)
 *
 * Subscribes to LLC real-time events arriving via the global WebSocket and
 * exposes a reactive stream of events filtered to the given company_id.
 *
 * Events relayed:
 *   llc:budget:*    — budget_warning_80, budget_warning_95, budget_exhausted
 *   llc:agent:*     — agent_paused, agent_resumed, heartbeat_ok, heartbeat_missed
 *   llc:approval:*  — approval_created, approval_resolved
 *   llc:sprint:*    — sprint_started, sprint_closed
 *   llc:company:*   — company-level lifecycle events
 *
 * Usage:
 *   const { events, on, clear } = useLLCNotifications(companyId)
 *   on('budget_exhausted', (e) => showAlert(e.payload))
 */

import { ref, onUnmounted, getCurrentInstance, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import globalWebSocketService from '@/services/GlobalWebSocketService'

const logger = createLogger('useLLCNotifications')

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LLCNotificationEvent {
  event_type: string
  company_id: string
  entity_type: string
  entity_id: string
  payload: Record<string, unknown>
  actor_id?: string
  ts: string
}

type LLCEventHandler = (event: LLCNotificationEvent) => void

// Event types that carry the llc event_type directly on msg.type
const LLC_EVENT_TYPES = [
  'budget_warning_80',
  'budget_warning_95',
  'budget_exhausted',
  'agent_paused',
  'agent_resumed',
  'heartbeat_ok',
  'heartbeat_missed',
  'approval_created',
  'approval_resolved',
  'sprint_started',
  'sprint_closed',
]

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useLLCNotifications(companyId: string) {
  const events: Ref<LLCNotificationEvent[]> = ref([])
  const handlers = new Map<string, Set<LLCEventHandler>>()
  const unsubscribers: Array<() => void> = []

  function _handleMessage(data: unknown) {
    const msg = data as Record<string, unknown>
    if (typeof msg !== 'object' || msg === null) return

    // LiveEventManager wraps the publisher envelope in a "payload" key (GH#8545).
    // Check both the wrapper level and the payload level for company_id.
    const payloadData = (msg.payload as Record<string, unknown> | null | undefined) ?? msg
    const eventCompanyId = (payloadData.company_id ?? msg.company_id) as string | undefined
    if (!eventCompanyId || eventCompanyId !== companyId) return

    const eventType = (msg.event_type ?? payloadData.event_type) as string
    if (!eventType || !LLC_EVENT_TYPES.includes(eventType)) return

    const event: LLCNotificationEvent = {
      event_type: eventType,
      company_id: eventCompanyId,
      entity_type: (payloadData.entity_type ?? '') as string,
      entity_id: String(payloadData.entity_id ?? ''),
      payload: (payloadData.payload ?? {}) as Record<string, unknown>,
      actor_id: payloadData.actor_id as string | undefined,
      ts: (payloadData.ts ?? new Date().toISOString()) as string,
    }

    events.value.push(event)

    const specific = handlers.get(event.event_type)
    if (specific) specific.forEach((cb) => cb(event))

    const wildcards = handlers.get('*')
    if (wildcards) wildcards.forEach((cb) => cb(event))
  }

  // LiveEventManager emits WS messages with type="live_event"; subscribe there
  // and also on generic "message" for any LLC events forwarded without wrapping.
  unsubscribers.push(globalWebSocketService.on('live_event', _handleMessage))
  unsubscribers.push(
    globalWebSocketService.on('message', (data: unknown) => {
      const msg = data as Record<string, unknown>
      if (typeof msg !== 'object' || msg === null) return
      // Skip if already handled via the live_event path
      if (msg.type === 'live_event') return
      _handleMessage(data)
    }),
  )

  function on(eventType: string, handler: LLCEventHandler): () => void {
    if (!handlers.has(eventType)) handlers.set(eventType, new Set())
    handlers.get(eventType)!.add(handler)
    return () => handlers.get(eventType)?.delete(handler)
  }

  function clear() {
    events.value = []
  }

  function cleanup() {
    unsubscribers.forEach((unsub) => unsub())
    handlers.clear()
  }

  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(cleanup)
  } else {
    logger.warn('useLLCNotifications called outside Vue component — manual cleanup required')
  }

  return { events, on, clear, cleanup }
}

export default useLLCNotifications
