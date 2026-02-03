/**
 * Global WebSocket Composable
 *
 * Provides easy access to the global WebSocket service for any component.
 * Use this in any Vue component to get real-time updates regardless of page/tab.
 */

import { computed, onUnmounted, getCurrentInstance } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import globalWebSocketService from '@/services/GlobalWebSocketService.js'

// Create scoped logger for useGlobalWebSocket
const logger = createLogger('useGlobalWebSocket')

export function useGlobalWebSocket() {
  const unsubscribers = []

  /**
   * Reactive connection state
   */
  const isConnected = computed(() => globalWebSocketService.isConnected.value)
  const connectionState = computed(() => globalWebSocketService.connectionState.value)
  const state = computed(() => globalWebSocketService.getState())

  /**
   * Listen for WebSocket events
   */
  const on = (event, callback) => {
    const unsubscribe = globalWebSocketService.on(event, callback)
    unsubscribers.push(unsubscribe)
    return unsubscribe
  }

  /**
   * Send message through WebSocket
   */
  const send = (data) => {
    return globalWebSocketService.send(data)
  }

  /**
   * Test WebSocket connection
   */
  const testConnection = () => {
    globalWebSocketService.testConnection()
  }

  /**
   * Manual connect/disconnect
   */
  const connect = () => {
    globalWebSocketService.connect()
  }

  const disconnect = () => {
    globalWebSocketService.disconnect()
  }

  /**
   * Cleanup on unmount - only if inside a Vue component
   */
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsubscribers.forEach(unsubscribe => unsubscribe())
    })
  } else {
    logger.warn('useGlobalWebSocket: Not inside Vue component, manual cleanup required')
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
    disconnect
  }
}

export default useGlobalWebSocket
