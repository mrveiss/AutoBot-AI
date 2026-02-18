/**
 * useWebSocket Composable
 *
 * Generic WebSocket management for individual connections to specific endpoints.
 * Handles connection lifecycle, reconnection, and cleanup.
 *
 * NOTE: This is for individual WebSocket connections (e.g., /api/logs/stream, /api/terminal).
 * For the global singleton WebSocket, use useGlobalWebSocket instead.
 */

import { ref, onUnmounted, watch, unref, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useWebSocket
const logger = createLogger('useWebSocket')

export interface UseWebSocketOptions {
  /**
   * Auto-connect on mount
   * @default true
   */
  autoConnect?: boolean

  /**
   * Auto-reconnect on close/error
   * @default true
   */
  autoReconnect?: boolean

  /**
   * Maximum reconnection attempts (0 = infinite)
   * @default 5
   */
  maxReconnectAttempts?: number

  /**
   * Base reconnection delay in ms
   * @default 1000
   */
  reconnectDelay?: number

  /**
   * Maximum reconnection delay in ms (for exponential backoff)
   * @default 10000
   */
  maxReconnectDelay?: number

  /**
   * Connection timeout in ms
   * @default 5000
   */
  connectionTimeout?: number

  /**
   * Heartbeat/ping interval in ms (0 = disabled)
   * @default 0
   */
  heartbeatInterval?: number

  /**
   * Heartbeat/ping message
   * @default 'ping'
   */
  heartbeatMessage?: string

  /**
   * Parse incoming messages as JSON
   * @default false
   */
  parseJSON?: boolean

  /**
   * Callback when connection opens
   */
  onOpen?: (event: Event) => void

  /**
   * Callback when message received
   */
  onMessage?: (data: any) => void

  /**
   * Callback when error occurs
   */
  onError?: (event: Event) => void

  /**
   * Callback when connection closes
   */
  onClose?: (event: CloseEvent) => void
}

const DEFAULT_OPTIONS: Required<UseWebSocketOptions> = {
  autoConnect: true,
  autoReconnect: true,
  maxReconnectAttempts: 5,
  reconnectDelay: 1000,
  maxReconnectDelay: 10000, // Issue #821: Cap at 10s for better UX (was 30s)
  connectionTimeout: 5000,
  heartbeatInterval: 0,
  heartbeatMessage: 'ping',
  parseJSON: false,
  onOpen: () => {},
  onMessage: () => {},
  onError: () => {},
  onClose: () => {}
}

/**
 * Create a managed WebSocket connection
 *
 * @param url - WebSocket URL (reactive or static)
 * @param options - Configuration options
 *
 * @example
 * ```typescript
 * const { isConnected, lastMessage, send, connect, disconnect } = useWebSocket(
 *   'ws://localhost:8001/api/logs/stream',
 *   {
 *     autoReconnect: true,
 *     onMessage: (data) => console.log('Received:', data)
 *   }
 * )
 * ```
 */
export function useWebSocket(
  url: Ref<string> | string,
  options: UseWebSocketOptions = {}
) {
  const opts = { ...DEFAULT_OPTIONS, ...options }

  // Reactive state
  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const isConnecting = ref(false)
  const lastMessage = ref<any>(null)
  const error = ref<Error | null>(null)
  const reconnectAttempts = ref(0)

  // Timers
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let connectionTimeoutTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * Clear all timers
   */
  const clearTimers = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (connectionTimeoutTimer) {
      clearTimeout(connectionTimeoutTimer)
      connectionTimeoutTimer = null
    }
  }

  /**
   * Start heartbeat/ping
   */
  const startHeartbeat = () => {
    if (opts.heartbeatInterval > 0 && ws.value && ws.value.readyState === WebSocket.OPEN) {
      heartbeatTimer = setInterval(() => {
        if (ws.value && ws.value.readyState === WebSocket.OPEN) {
          ws.value.send(opts.heartbeatMessage)
        }
      }, opts.heartbeatInterval)
    }
  }

  /**
   * Connect to WebSocket
   */
  const connect = () => {
    if (isConnecting.value || (ws.value && ws.value.readyState === WebSocket.OPEN)) {
      return // Already connecting or connected
    }

    const wsUrl = unref(url)
    if (!wsUrl) {
      logger.error('Invalid URL:', wsUrl)
      return
    }

    isConnecting.value = true
    error.value = null

    try {
      ws.value = new WebSocket(wsUrl)

      // Connection timeout
      if (opts.connectionTimeout > 0) {
        connectionTimeoutTimer = setTimeout(() => {
          if (isConnecting.value) {
            logger.warn('Connection timeout')
            error.value = new Error('Connection timeout')
            ws.value?.close()
          }
        }, opts.connectionTimeout)
      }

      ws.value.onopen = (event) => {
        isConnected.value = true
        isConnecting.value = false
        reconnectAttempts.value = 0
        error.value = null
        clearTimers()

        logger.info('Connected to:', wsUrl)

        // Start heartbeat
        startHeartbeat()

        // Callback
        opts.onOpen(event)
      }

      ws.value.onmessage = (event) => {
        try {
          const data = opts.parseJSON ? JSON.parse(event.data) : event.data
          lastMessage.value = data
          opts.onMessage(data)
        } catch (err) {
          logger.error('Error parsing message:', err)
          lastMessage.value = event.data
          opts.onMessage(event.data)
        }
      }

      ws.value.onerror = (event) => {
        logger.error('Error:', event)
        error.value = new Error('WebSocket error')
        isConnecting.value = false
        // Clear heartbeat timer - dead socket should not keep sending pings (#820)
        if (heartbeatTimer) {
          clearInterval(heartbeatTimer)
          heartbeatTimer = null
        }
        opts.onError(event)
      }

      ws.value.onclose = (event) => {
        isConnected.value = false
        isConnecting.value = false
        clearTimers()

        logger.info('Closed:', { code: event.code, reason: event.reason })
        opts.onClose(event)

        // Auto-reconnect logic
        if (
          opts.autoReconnect &&
          event.code !== 1000 && // Normal closure
          (opts.maxReconnectAttempts === 0 || reconnectAttempts.value < opts.maxReconnectAttempts)
        ) {
          // Exponential backoff: delay * 2^attempts
          const delay = Math.min(
            opts.reconnectDelay * Math.pow(2, reconnectAttempts.value),
            opts.maxReconnectDelay
          )

          logger.info(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts.value + 1})`)

          reconnectTimer = setTimeout(() => {
            reconnectAttempts.value++
            connect()
          }, delay)
        } else if (opts.maxReconnectAttempts > 0 && reconnectAttempts.value >= opts.maxReconnectAttempts) {
          logger.warn('Max reconnection attempts reached')
          error.value = new Error('Max reconnection attempts reached')
        }
      }
    } catch (err) {
      logger.error('Connection error:', err)
      error.value = err instanceof Error ? err : new Error('Connection error')
      isConnecting.value = false
    }
  }

  /**
   * Disconnect from WebSocket
   */
  const disconnect = (code: number = 1000, reason: string = 'Client disconnect') => {
    clearTimers()

    if (ws.value) {
      // Disable auto-reconnect for manual disconnect
      const wasAutoReconnect = opts.autoReconnect
      opts.autoReconnect = false

      ws.value.close(code, reason)
      ws.value = null

      // Restore auto-reconnect setting
      opts.autoReconnect = wasAutoReconnect
    }

    isConnected.value = false
    isConnecting.value = false
  }

  /**
   * Send data through WebSocket
   */
  const send = (data: any): boolean => {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      logger.warn('Cannot send - not connected')
      return false
    }

    try {
      const payload = typeof data === 'string' ? data : JSON.stringify(data)
      ws.value.send(payload)
      return true
    } catch (err) {
      logger.error('Error sending data:', err)
      error.value = err instanceof Error ? err : new Error('Send error')
      return false
    }
  }

  /**
   * Manually trigger reconnection
   */
  const reconnect = () => {
    disconnect()
    reconnectAttempts.value = 0
    setTimeout(connect, 100)
  }

  // Watch URL changes and reconnect
  if (url && typeof url !== 'string') {
    watch(url, (newUrl, oldUrl) => {
      if (newUrl !== oldUrl && (isConnected.value || isConnecting.value)) {
        logger.info('URL changed, disconnecting old connection before reconnecting...')
        // Disconnect old connection first to prevent accumulating connections (#820)
        disconnect()
        reconnectAttempts.value = 0
        setTimeout(connect, 100)
      }
    })
  }

  // Auto-connect on mount
  if (opts.autoConnect) {
    connect()
  }

  // Cleanup on unmount
  onUnmounted(() => {
    disconnect()
  })

  return {
    // State
    ws,
    isConnected,
    isConnecting,
    lastMessage,
    error,
    reconnectAttempts,

    // Methods
    connect,
    disconnect,
    send,
    reconnect
  }
}
