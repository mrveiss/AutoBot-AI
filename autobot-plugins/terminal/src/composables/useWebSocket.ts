// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

import { ref, computed, onScopeDispose, toValue, unref, type MaybeRefOrGetter, type Ref } from 'vue'
import { createLogger, redactUrlForLogging, redactErrorForLogging } from '../utils'

const logger = createLogger('useWebSocket')

export interface UseWebSocketOptions {
  autoConnect?: boolean
  autoReconnect?: boolean
  maxReconnectAttempts?: number
  reconnectDelay?: number
  maxReconnectDelay?: number
  connectionTimeout?: number
  parseJSON?: boolean
  /** Heartbeat interval in ms (0 = disabled). Sent while the socket is open. */
  heartbeatInterval?: number
  /** Heartbeat payload; non-strings are JSON-encoded. */
  heartbeatMessage?: unknown
  /**
   * WebSocket subprotocols to offer on the handshake -- e.g. `['bearer', '<jwt>']`
   * so the token travels in Sec-WebSocket-Protocol and never in the URL (#16457,
   * #18550). Read at connect time, so a ref or getter picks up the current token
   * on every (re)connect. Omitted/undefined keeps the single-argument form.
   */
  protocols?: MaybeRefOrGetter<string[] | undefined>
  onOpen?: (event: Event) => void
  onMessage?: (data: unknown) => void
  onError?: (event: Event) => void
  onClose?: (event: CloseEvent) => void
}

export function useWebSocket(url: Ref<string> | string, options: UseWebSocketOptions = {}) {
  const opts = {
    autoConnect: true,
    autoReconnect: true,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    maxReconnectDelay: 10000,
    connectionTimeout: 5000,
    parseJSON: false,
    heartbeatInterval: 0,
    heartbeatMessage: 'ping' as unknown,
    protocols: undefined as MaybeRefOrGetter<string[] | undefined>,
    onOpen: (_e: Event) => {},
    onMessage: (_d: unknown) => {},
    onError: (_e: Event) => {},
    onClose: (_e: CloseEvent) => {},
    ...options,
  }

  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const isConnecting = ref(false)
  const lastMessage = ref<unknown>(null)
  const errorList = ref<Error[]>([])
  const error = computed<Error | null>(() =>
    errorList.value.length === 0 ? null : errorList.value[errorList.value.length - 1]
  )
  const reconnectAttempts = ref(0)

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let connectionTimeoutTimer: ReturnType<typeof setTimeout> | null = null

  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  const stopHeartbeat = () => {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  }

  const startHeartbeat = () => {
    stopHeartbeat()
    if (opts.heartbeatInterval <= 0) return
    heartbeatTimer = setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        const msg = opts.heartbeatMessage
        ws.value.send(typeof msg === 'string' ? msg : JSON.stringify(msg))
      }
    }, opts.heartbeatInterval)
  }

  const clearTimers = () => {
    stopHeartbeat()
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (connectionTimeoutTimer) { clearTimeout(connectionTimeoutTimer); connectionTimeoutTimer = null }
  }

  const connect = () => {
    if (isConnecting.value || (ws.value && ws.value.readyState === WebSocket.OPEN)) return

    const wsUrl = unref(url)
    if (!wsUrl) { logger.error('Invalid URL:', redactUrlForLogging(wsUrl)); return }

    isConnecting.value = true
    errorList.value = []

    try {
      const subprotocols = toValue(opts.protocols)
      ws.value = subprotocols ? new WebSocket(wsUrl, subprotocols) : new WebSocket(wsUrl)

      if (opts.connectionTimeout > 0) {
        connectionTimeoutTimer = setTimeout(() => {
          if (isConnecting.value) {
            errorList.value = [...errorList.value, new Error('Connection timeout')]
            ws.value?.close()
          }
        }, opts.connectionTimeout)
      }

      ws.value.onopen = (event) => {
        isConnected.value = true
        isConnecting.value = false
        reconnectAttempts.value = 0
        errorList.value = []
        clearTimers()
        startHeartbeat()
        logger.info('Connected to:', redactUrlForLogging(wsUrl))
        opts.onOpen(event)
      }

      ws.value.onmessage = (event) => {
        try {
          const data = opts.parseJSON ? JSON.parse(event.data as string) : event.data
          lastMessage.value = data
          opts.onMessage(data)
        } catch {
          lastMessage.value = event.data
          opts.onMessage(event.data)
        }
      }

      ws.value.onerror = (event) => {
        logger.error('Error:', event)
        errorList.value = [...errorList.value, new Error('WebSocket error')]
        isConnecting.value = false
        opts.onError(event)
      }

      ws.value.onclose = (event) => {
        isConnected.value = false
        isConnecting.value = false
        clearTimers()
        logger.info('Closed:', { code: event.code, reason: event.reason })
        opts.onClose(event)

        if (
          opts.autoReconnect &&
          event.code !== 1000 &&
          (opts.maxReconnectAttempts === 0 || reconnectAttempts.value < opts.maxReconnectAttempts)
        ) {
          const delay = Math.min(opts.reconnectDelay * Math.pow(2, reconnectAttempts.value), opts.maxReconnectDelay)
          reconnectTimer = setTimeout(() => { reconnectAttempts.value++; connect() }, delay)
        }
      }
    } catch (err) {
      // #14989: same defensive redaction as the autobot-frontend copy --
      // a wrong-scheme new WebSocket() throw can embed the raw URL.
      // createLogger() is a no-op today, so this is not live yet either,
      // same as the two log calls above.
      logger.error('Failed to create WebSocket:', redactErrorForLogging(err))
      isConnecting.value = false
      errorList.value = [...errorList.value, err instanceof Error ? err : new Error(String(err))]
    }
  }

  const disconnect = () => {
    clearTimers()
    if (ws.value) {
      ws.value.close(1000, 'Manual disconnect')
      ws.value = null
    }
    isConnected.value = false
    isConnecting.value = false
  }

  const send = (data: unknown) => {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      logger.warn('Cannot send: not connected')
      return
    }
    const payload = typeof data === 'string' ? data : JSON.stringify(data)
    ws.value.send(payload)
  }

  if (opts.autoConnect) connect()

  onScopeDispose(() => {
    clearTimers()
    if (ws.value) { ws.value.onclose = null; ws.value.close(1000, 'Scope disposed') }
  })

  return { isConnected, isConnecting, lastMessage, error, reconnectAttempts, connect, disconnect, send }
}
