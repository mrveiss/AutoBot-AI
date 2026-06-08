// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * useEventBus — unified event composable (#6488)
 *
 * Single entry point for channel-based real-time events.  Wraps the existing
 * LiveEventService, which already handles channel-scoped subscriptions and
 * WebSocket lifecycle.  The eventual migration target when the three WebSocket
 * managers (useWebSocket, useGlobalWebSocket, useLiveEvents) are fully merged.
 *
 * Today's scope (Phase 1):
 *   - One composable replaces useLiveEvents for new code
 *   - Existing callers of useWebSocket / useGlobalWebSocket continue to work
 *   - Full consolidation deferred to Phase 2 (#6488 follow-up) once the
 *     backend bus facade (#6486) is in place and endpoint unification is done
 *
 * Usage:
 *   const { subscribe, isConnected, connectionState } = useEventBus()
 *   const unsub = subscribe('agent:abc', (event) => { ... })
 *   // Channels: 'global', 'agent:{id}', 'task:{id}', 'workflow:{id}'
 */

import { computed, onUnmounted, getCurrentInstance, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import liveEventService, {
  type LiveEvent,
  type LiveEventCallback,
} from '@/services/LiveEventService'
import type { ConnectionState } from '@/services/GlobalWebSocketService'

const logger = createLogger('useEventBus')

export type EventBusCallback = LiveEventCallback

export interface UseEventBusReturn {
  isConnected: ComputedRef<boolean>
  connectionState: ComputedRef<ConnectionState>
  /**
   * Subscribe to a channel.  Returns an unsubscribe function.
   * Auto-cleans up on component unmount.
   */
  subscribe: (channel: string, callback: EventBusCallback) => () => void
  unsubscribe: (channel: string, callback: EventBusCallback) => void
  connect: (token?: string) => Promise<void>
  disconnect: () => void
}

export function useEventBus(): UseEventBusReturn {
  const unsubscribers: Array<() => void> = []

  const isConnected = computed(() => liveEventService.isConnected.value)
  const connectionState = computed(() => liveEventService.connectionState.value)

  const subscribe = (channel: string, callback: EventBusCallback): (() => void) => {
    const unsub = liveEventService.subscribe(channel, callback)
    unsubscribers.push(unsub)
    return unsub
  }

  const unsubscribe = (channel: string, callback: EventBusCallback): void => {
    liveEventService.unsubscribe(channel, callback)
  }

  const connect = (token?: string): Promise<void> => liveEventService.connect(token)
  const disconnect = (): void => liveEventService.disconnect()

  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsubscribers.forEach((unsub) => unsub())
    })
  } else {
    logger.warn('useEventBus: Not inside Vue component, manual cleanup required')
  }

  return { isConnected, connectionState, subscribe, unsubscribe, connect, disconnect }
}

export default useEventBus
export type { LiveEvent, ConnectionState }
