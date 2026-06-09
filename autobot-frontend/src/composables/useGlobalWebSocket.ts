// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Global WebSocket Composable
 *
 * @deprecated For channel-based event subscriptions, prefer `useEventBus`
 * from `@/composables/useEventBus` instead (#6488 Phase 2).
 * This composable is preserved for callers that need `send()` or `state`
 * access until backend endpoint unification (#8291) is complete.
 *
 * Provides easy access to the global WebSocket service for any component.
 * Use this in any Vue component to get real-time updates regardless of page/tab.
 *
 * TypeScript migration of useGlobalWebSocket.js (#819).
 */

import { computed, onUnmounted, getCurrentInstance, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import globalWebSocketService, {
  type ConnectionState,
  type EventCallback,
  type WebSocketStateSnapshot,
} from '@/services/GlobalWebSocketService'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseGlobalWebSocketReturn {
  // State
  isConnected: ComputedRef<boolean>
  connectionState: ComputedRef<ConnectionState>
  state: ComputedRef<WebSocketStateSnapshot>

  // Methods
  on: (event: string, callback: EventCallback) => () => void
  send: (data: unknown) => boolean
  testConnection: () => void
  connect: () => void
  disconnect: () => void
}

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

const logger = createLogger('useGlobalWebSocket')

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useGlobalWebSocket(): UseGlobalWebSocketReturn {
  const unsubscribers: Array<() => void> = []

  // Reactive connection state
  const isConnected = computed(() => globalWebSocketService.isConnected.value)
  const connectionState = computed(
    () => globalWebSocketService.connectionState.value,
  )
  const state = computed(() => globalWebSocketService.getState())

  // Listen for WebSocket events
  const on = (event: string, callback: EventCallback): (() => void) => {
    const unsubscribe = globalWebSocketService.on(event, callback)
    unsubscribers.push(unsubscribe)
    return unsubscribe
  }

  // Send message through WebSocket
  const send = (data: unknown): boolean => {
    return globalWebSocketService.send(data as Record<string, unknown>)
  }

  // Test WebSocket connection
  const testConnection = (): void => {
    globalWebSocketService.testConnection()
  }

  // Manual connect/disconnect
  const connect = (): void => {
    globalWebSocketService.connect()
  }

  const disconnect = (): void => {
    globalWebSocketService.disconnect()
  }

  // Cleanup on unmount - only if inside a Vue component
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsubscribers.forEach((unsubscribe) => unsubscribe())
    })
  } else {
    logger.warn(
      'useGlobalWebSocket: Not inside Vue component, manual cleanup required',
    )
  }

  return {
    // State
    isConnected,
    connectionState,
    state,

    // Methods
    on,
    send,
    testConnection,
    connect,
    disconnect,
  }
}

export default useGlobalWebSocket
