// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Live Events Composable (#2064)
 *
 * @deprecated Use `useEventBus` from `@/composables/useEventBus` instead.
 * `useEventBus` is the canonical unified entry-point (#6488 Phase 2).
 * This composable is preserved for backward compatibility; migrate callers to
 * `useEventBus()` — the API is identical.
 *
 * Provides Vue-friendly access to the scoped LiveEventService for
 * channel-based real-time event streaming (agent:{id}, task:{id},
 * workflow:{id}, global).
 */

import { computed, onUnmounted, getCurrentInstance, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import liveEventService, {
  type LiveEvent,
  type LiveEventCallback,
  type LiveEventConnectionState,
} from '@/services/LiveEventService'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseLiveEventsReturn {
  /** Whether the WebSocket is currently connected */
  isConnected: ComputedRef<boolean>
  /** Current connection lifecycle state */
  connectionState: ComputedRef<LiveEventConnectionState>

  /**
   * Subscribe to a channel. Returns an unsubscribe function.
   * Automatically cleans up on component unmount.
   */
  subscribe: (channel: string, callback: LiveEventCallback) => () => void

  /** Manually unsubscribe a specific callback from a channel */
  unsubscribe: (channel: string, callback: LiveEventCallback) => void

  /** Manually trigger connection (normally auto-connects on import) */
  connect: (token?: string) => Promise<void>

  /** Disconnect the live event WebSocket */
  disconnect: () => void
}

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

const logger = createLogger('useLiveEvents')

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useLiveEvents(): UseLiveEventsReturn {
  const unsubscribers: Array<() => void> = []

  // Reactive connection state
  const isConnected = computed(() => liveEventService.isConnected.value)
  const connectionState = computed(
    () => liveEventService.connectionState.value,
  )

  // Subscribe to a channel with auto-cleanup tracking
  const subscribe = (
    channel: string,
    callback: LiveEventCallback,
  ): (() => void) => {
    const unsub = liveEventService.subscribe(channel, callback)
    unsubscribers.push(unsub)
    return unsub
  }

  // Unsubscribe from a channel
  const unsubscribe = (
    channel: string,
    callback: LiveEventCallback,
  ): void => {
    liveEventService.unsubscribe(channel, callback)
  }

  // Manual connect
  const connect = (token?: string): Promise<void> => {
    return liveEventService.connect(token)
  }

  // Manual disconnect
  const disconnect = (): void => {
    liveEventService.disconnect()
  }

  // Cleanup on unmount - only if inside a Vue component
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsubscribers.forEach((unsub) => unsub())
    })
  } else {
    logger.warn(
      'useLiveEvents: Not inside Vue component, manual cleanup required',
    )
  }

  return {
    isConnected,
    connectionState,
    subscribe,
    unsubscribe,
    connect,
    disconnect,
  }
}

export default useLiveEvents

// Re-export types for convenience
export type { LiveEvent, LiveEventCallback, LiveEventConnectionState }
