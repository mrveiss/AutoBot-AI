/**
 * Global WebSocket Service - Simplified and Reliable (TypeScript)
 *
 * Provides system-wide WebSocket connectivity for RUM monitoring,
 * real-time updates, and cross-component communication.
 * Simplified from 575+ lines to focus on reliability over complexity.
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, reactive, type Ref } from 'vue'
import { DEFAULT_CONFIG } from '@/config/defaults.js'
import { createLogger } from '@/utils/debugUtils'

// ---------------------------------------------------------------------------
// Types & Interfaces
// ---------------------------------------------------------------------------

/** WebSocket connection lifecycle states */
type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'

/** Callback signature for event listeners */
type EventCallback = (data: unknown) => void

/** Shape of the reactive state exposed to Vue components */
interface WebSocketReactiveState {
  connected: boolean
  lastMessage: Record<string, unknown> | null
  lastError: string | null
  url: string
  lastConnectionAttempt: Date | null
  reconnectCount: number
}

/** Snapshot returned by getState() */
interface WebSocketStateSnapshot extends WebSocketReactiveState {
  connectionState: ConnectionState
  reconnectAttempts: number
  maxReconnectAttempts: number
  readyState: number | undefined
}

/** Data persisted in localStorage across reloads */
interface PersistedState {
  reconnectCount: number
  lastAttempt: number
}

/** Minimal RUM interface for optional window.rum tracking */
interface RumTracker {
  trackWebSocketEvent?: (name: string, data: Record<string, unknown>) => void
  trackEvent?: (category: string, data: Record<string, unknown>) => void
}

/** Debug interface exposed on window.wsDebug */
interface WsDebugInterface {
  connect: () => Promise<void>
  disconnect: () => void
  forceReconnect: () => void
  test: () => Promise<boolean>
  state: () => WebSocketStateSnapshot
  clearState: () => void
}

const logger = createLogger('GlobalWebSocketService')

// ---------------------------------------------------------------------------
// Class
// ---------------------------------------------------------------------------

class GlobalWebSocketService {
  ws: WebSocket | null
  isConnected: Ref<boolean>
  connectionState: Ref<ConnectionState>
  reconnectAttempts: number
  maxReconnectAttempts: number
  baseDelay: number
  maxDelay: number
  connectionTimeout: number
  heartbeatInterval: ReturnType<typeof setInterval> | null
  heartbeatTimeout: number
  listeners: Map<string, Set<EventCallback>>
  state: WebSocketReactiveState

  constructor() {
    this.ws = null
    this.isConnected = ref(false)
    this.connectionState = ref<ConnectionState>('disconnected')
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.baseDelay = 1000
    this.maxDelay = 16000
    this.connectionTimeout = 5000
    this.heartbeatInterval = null
    this.heartbeatTimeout = 30000
    this.listeners = new Map()

    this.state = reactive<WebSocketReactiveState>({
      connected: false,
      lastMessage: null,
      lastError: null,
      url: this.getWebSocketUrl(),
      lastConnectionAttempt: null,
      reconnectCount: 0
    })

    this.restoreConnectionState()

    logger.debug(
      'Global WebSocket Service initialized with URL:',
      this.state.url
    )
  }

  // -----------------------------------------------------------------------
  // URL Construction
  // -----------------------------------------------------------------------

  /**
   * Get WebSocket URL with proper environment detection.
   * CRITICAL: Uses DEFAULT_CONFIG for all defaults -- no hardcoded fallbacks.
   */
  getWebSocketUrl(): string {
    try {
      const backendHost: string = DEFAULT_CONFIG.network.backend.host
      const backendPort: string = DEFAULT_CONFIG.network.backend.port
      const wsProtocol =
        window.location.protocol === 'https:' ? 'wss:' : 'ws:'

      const isViteDevServer =
        import.meta.env.DEV &&
        window.location.port === '5173' &&
        window.location.hostname === 'localhost'

      if (isViteDevServer) {
        const wsUrl = `${wsProtocol}//${window.location.host}/api/ws`
        logger.debug('Development WebSocket URL (via Vite proxy):', wsUrl)
        return wsUrl
      }

      // Issue #916: Use window.location.host so WebSocket goes through nginx proxy at .21
      // Nginx proxies /api/ws to backend with proxy_ssl_verify off (handles self-signed cert)
      const wsUrl = `${wsProtocol}//${window.location.host}/api/ws`
      logger.debug('Production WebSocket URL (via nginx proxy):', wsUrl)
      return wsUrl
    } catch (error: unknown) {
      logger.error('Failed to construct WebSocket URL:', error)
      const message =
        error instanceof Error ? error.message : String(error)
      throw new Error(`WebSocket URL construction failed: ${message}`)
    }
  }

  // -----------------------------------------------------------------------
  // Persistence
  // -----------------------------------------------------------------------

  /** Restore connection state from localStorage */
  restoreConnectionState(): void {
    try {
      const saved = localStorage.getItem('autobot-websocket-state')
      if (saved) {
        const parsed = JSON.parse(saved) as PersistedState
        this.reconnectAttempts = Math.min(parsed.reconnectCount || 0, 2)
        this.state.reconnectCount = this.reconnectAttempts
      }
    } catch (error: unknown) {
      logger.warn('Failed to restore WebSocket state:', error)
    }
  }

  /** Save connection state to localStorage */
  saveConnectionState(): void {
    try {
      const stateToSave: PersistedState = {
        reconnectCount: this.reconnectAttempts,
        lastAttempt: Date.now()
      }
      localStorage.setItem(
        'autobot-websocket-state',
        JSON.stringify(stateToSave)
      )
    } catch (error: unknown) {
      logger.warn('Failed to save WebSocket state:', error)
    }
  }

  // -----------------------------------------------------------------------
  // Connection Lifecycle
  // -----------------------------------------------------------------------

  /** Connect to WebSocket server with simplified logic */
  async connect(): Promise<void> {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING ||
        this.ws.readyState === WebSocket.OPEN)
    ) {
      return
    }

    this.state.lastConnectionAttempt = new Date()
    this.connectionState.value = 'connecting'
    this.cleanup()

    this.quickHealthCheck().catch(() => {
      // Health check failed but continue with WebSocket attempt
    })

    const wsUrl = this.state.url
    logger.debug(
      'Connecting WebSocket (attempt',
      this.reconnectAttempts + 1,
      '):',
      wsUrl
    )
    this.trackEvent('connection_attempt', {
      url: wsUrl,
      attempt: this.reconnectAttempts + 1
    })

    return new Promise<void>((resolve, reject) => {
      try {
        this.ws = new WebSocket(wsUrl)
        this._setupEventHandlers(resolve, reject)
        this._setupConnectionTimeout(reject)
      } catch (error: unknown) {
        logger.error('Failed to create WebSocket:', error)
        this.handleConnectionError(error)
        reject(error)
      }
    })
  }

  /** Quick health check (non-blocking) */
  async quickHealthCheck(): Promise<boolean> {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2000)

    try {
      const response = await fetch('/api/health', {
        signal: controller.signal,
        cache: 'no-store'
      })
      clearTimeout(timeoutId)
      return response.ok
    } catch (error: unknown) {
      clearTimeout(timeoutId)
      throw error
    }
  }

  // -----------------------------------------------------------------------
  // Event Handler Setup (split into helpers for <=50 lines each)
  // -----------------------------------------------------------------------

  /**
   * Wire all WebSocket event handlers onto this.ws.
   * Delegates to _handleOpen, _handleMessage, _handleError, _handleClose.
   */
  private _setupEventHandlers(
    resolve: () => void,
    reject: (reason: unknown) => void
  ): void {
    if (!this.ws) return

    this.ws.onopen = () => this._handleOpen(resolve)
    this.ws.onmessage = (event: MessageEvent) =>
      this._handleMessage(event)
    this.ws.onerror = (event: Event) =>
      this._handleError(event, reject)
    this.ws.onclose = (event: CloseEvent) => this._handleClose(event)
  }

  /** Install a timeout that rejects the connect() promise if stuck */
  private _setupConnectionTimeout(
    reject: (reason: unknown) => void
  ): void {
    const timeoutId = setTimeout(() => {
      if (this.connectionState.value === 'connecting') {
        logger.error('WebSocket connection timeout')
        this.handleConnectionError(new Error('Connection timeout'))
        this.ws?.close()
        reject(new Error('Connection timeout'))
      }
    }, this.connectionTimeout)

    if (this.ws) {
      this.ws.addEventListener('open', () => clearTimeout(timeoutId), {
        once: true
      })
      this.ws.addEventListener(
        'error',
        () => clearTimeout(timeoutId),
        { once: true }
      )
    }
  }

  /** Handle successful WebSocket open event */
  private _handleOpen(resolve: () => void): void {
    logger.debug('WebSocket connected successfully')

    this.connectionState.value = 'connected'
    this.isConnected.value = true
    this.state.connected = true
    this.reconnectAttempts = 0
    this.state.reconnectCount = 0
    this.state.lastError = null

    this.saveConnectionState()
    this.startHeartbeat()

    this.trackEvent('connection_opened', { url: this.state.url })
    this.emit('connected', { url: this.state.url })

    resolve()
  }

  /** Handle incoming WebSocket message */
  private _handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data as string) as Record<
        string,
        unknown
      >
      this.state.lastMessage = data

      if (data.type === 'ping') {
        this.send({ type: 'pong', timestamp: Date.now() })
        return
      }
      if (data.type === 'pong') {
        return
      }

      this.emit('message', data)
      if (data.type) {
        this.emit(data.type as string, data)
      }

      this.trackEvent('message_received', {
        dataSize: (event.data as string).length,
        eventType: (data.type as string) || 'unknown'
      })
    } catch (error: unknown) {
      logger.error('Failed to parse WebSocket message:', error)
      const message =
        error instanceof Error ? error.message : String(error)
      this.trackEvent('message_parse_error', {
        error: message,
        rawDataLength:
          typeof event.data === 'string' ? event.data.length : 0
      })
    }
  }

  /** Handle WebSocket error event */
  private _handleError(
    event: Event,
    reject: (reason: unknown) => void
  ): void {
    logger.error('WebSocket error:', event)
    this.handleConnectionError(event)
    reject(event)
  }

  /** Handle WebSocket close event */
  private _handleClose(event: CloseEvent): void {
    logger.debug('WebSocket closed:', {
      code: event.code,
      reason: event.reason,
      wasClean: event.wasClean
    })

    this.connectionState.value = 'disconnected'
    this.isConnected.value = false
    this.state.connected = false
    this.stopHeartbeat()

    this.trackEvent('connection_closed', {
      code: event.code,
      reason: event.reason,
      wasClean: event.wasClean
    })

    this.emit('disconnected', {
      code: event.code,
      reason: event.reason,
      wasClean: event.wasClean
    })

    this.scheduleReconnect(event)
  }

  // -----------------------------------------------------------------------
  // Error Handling & Reconnect
  // -----------------------------------------------------------------------

  /** Handle connection errors */
  handleConnectionError(error: unknown): void {
    this.connectionState.value = 'error'
    this.state.lastError = String(error)

    this.trackEvent('connection_error', {
      error: String(error),
      attempt: this.reconnectAttempts
    })

    this.emit('error', error)
  }

  /** Schedule reconnection with exponential backoff */
  scheduleReconnect(event: CloseEvent): void {
    if (event.code === 1000 || event.code === 3000) {
      return
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      logger.debug('Max reconnection attempts reached')
      this.state.lastError = `Connection failed after ${this.reconnectAttempts} attempts`
      return
    }

    this.reconnectAttempts++
    this.state.reconnectCount = this.reconnectAttempts

    const backoffDelay = Math.min(
      this.baseDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxDelay
    )
    const jitter = Math.random() * 1000
    const delay = backoffDelay + jitter

    logger.debug(
      `Reconnecting in ${Math.round(delay)}ms ` +
        `(attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    )

    setTimeout(() => {
      if (this.connectionState.value !== 'connected') {
        this.connect().catch((error: unknown) => {
          logger.error('Reconnection failed:', error)
        })
      }
    }, delay)
  }

  // -----------------------------------------------------------------------
  // Send / Heartbeat
  // -----------------------------------------------------------------------

  /** Send message through WebSocket */
  send(data: Record<string, unknown>): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        const message = JSON.stringify(data)
        this.ws.send(message)

        this.trackEvent('message_sent', {
          dataType: typeof data,
          dataSize: message.length,
          messageType: (data.type as string) || 'unknown'
        })

        return true
      } catch (error: unknown) {
        logger.error('Failed to send WebSocket message:', error)
        return false
      }
    }

    logger.warn('Cannot send message - WebSocket not connected')
    return false
  }

  /** Start heartbeat to keep connection alive */
  startHeartbeat(): void {
    this.stopHeartbeat()

    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping', timestamp: Date.now() })
      } else {
        this.stopHeartbeat()
      }
    }, this.heartbeatTimeout)
  }

  /** Stop heartbeat */
  stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  // -----------------------------------------------------------------------
  // Cleanup / Disconnect
  // -----------------------------------------------------------------------

  /** Clean up WebSocket connection */
  cleanup(): void {
    this.stopHeartbeat()

    if (this.ws) {
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onerror = null
      this.ws.onclose = null

      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.close(1000, 'cleanup')
      }
      this.ws = null
    }
  }

  /** Disconnect cleanly */
  disconnect(): void {
    logger.debug('Disconnecting WebSocket')
    this.reconnectAttempts = this.maxReconnectAttempts
    this.cleanup()
    this.connectionState.value = 'disconnected'
    this.isConnected.value = false
    this.state.connected = false
  }

  /** Force reconnection */
  forceReconnect(): void {
    logger.debug('Forcing WebSocket reconnection')
    this.reconnectAttempts = 0
    this.state.reconnectCount = 0
    this.disconnect()
    setTimeout(() => this.connect(), 1000)
  }

  // -----------------------------------------------------------------------
  // Event Emitter
  // -----------------------------------------------------------------------

  /** Add event listener. Returns an unsubscribe function. */
  on(event: string, callback: EventCallback): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    // Non-null assertion safe: we just ensured the key exists above
    this.listeners.get(event)!.add(callback)

    return () => {
      const listeners = this.listeners.get(event)
      if (listeners) {
        listeners.delete(callback)
      }
    }
  }

  /**
   * Subscribe to a topic/event -- alias for on().
   * Provides compatibility with code expecting subscribe/unsubscribe API.
   */
  subscribe(topic: string, callback: EventCallback): () => void {
    return this.on(topic, callback)
  }

  /** Unsubscribe from a topic -- alias for off() */
  unsubscribe(topic: string, callback: EventCallback): void {
    this.off(topic, callback)
  }

  /** Remove event listener */
  off(event: string, callback: EventCallback): void {
    const listeners = this.listeners.get(event)
    if (listeners) {
      listeners.delete(callback)
    }
  }

  /** Emit event to listeners */
  emit(event: string, data: unknown): void {
    const listeners = this.listeners.get(event)
    if (listeners) {
      listeners.forEach((callback) => {
        try {
          callback(data)
        } catch (error: unknown) {
          logger.error('Error in WebSocket event listener:', error)
        }
      })
    }
  }

  // -----------------------------------------------------------------------
  // RUM Tracking
  // -----------------------------------------------------------------------

  /**
   * Track events with RUM if available.
   * Made resilient to RUM initialization issues.
   */
  trackEvent(eventType: string, data: Record<string, unknown>): void {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- window.rum is an optional third-party RUM global with no type definitions
      const rum = (window as any).rum as RumTracker | undefined

      if (rum && typeof rum.trackWebSocketEvent === 'function') {
        rum.trackWebSocketEvent(`global_${eventType}`, data)
      } else if (rum && typeof rum.trackEvent === 'function') {
        rum.trackEvent('websocket', {
          type: `global_${eventType}`,
          ...data
        })
      }
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : String(error)
      logger.debug(
        '[GlobalWebSocketService] RUM tracking not available:',
        message
      )
    }
  }

  // -----------------------------------------------------------------------
  // Diagnostics
  // -----------------------------------------------------------------------

  /** Get current connection state */
  getState(): WebSocketStateSnapshot {
    return {
      connected: this.isConnected.value,
      connectionState: this.connectionState.value,
      reconnectAttempts: this.reconnectAttempts,
      maxReconnectAttempts: this.maxReconnectAttempts,
      readyState: this.ws?.readyState,
      lastMessage: this.state.lastMessage,
      lastError: this.state.lastError,
      url: this.state.url,
      lastConnectionAttempt: this.state.lastConnectionAttempt,
      reconnectCount: this.state.reconnectCount
    }
  }

  /** Test connection by sending a ping and waiting for pong */
  async testConnection(): Promise<boolean> {
    logger.debug('Testing WebSocket connection...')

    if (this.isConnected.value) {
      return new Promise<boolean>((resolve) => {
        const timeout = setTimeout(() => resolve(false), 5000)

        const handlePong: EventCallback = () => {
          clearTimeout(timeout)
          this.off('pong', handlePong)
          resolve(true)
        }

        this.on('pong', handlePong)
        this.send({ type: 'ping', timestamp: Date.now(), test: true })
      })
    }

    try {
      await this.connect()
      return this.isConnected.value
    } catch (_error: unknown) {
      return false
    }
  }
}

// ---------------------------------------------------------------------------
// Singleton & Auto-connect
// ---------------------------------------------------------------------------

const globalWebSocketService = new GlobalWebSocketService()

// Auto-connect with delay to allow app initialization.
// Only connect if this is the first import and not already connected.
if (typeof window !== 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- one-time init flag on window with no type definition
  const win = window as any

  if (!win._autobotWebSocketInitialized) {
    win._autobotWebSocketInitialized = true

    setTimeout(() => {
      if (
        !globalWebSocketService.isConnected.value &&
        globalWebSocketService.connectionState.value !== 'connecting'
      ) {
        globalWebSocketService.connect().catch((error: unknown) => {
          logger.error('Initial WebSocket connection failed:', error)
        })
      }
    }, 500)
  }
}

// Global debugging interface
if (typeof window !== 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- debug helpers attached to window for console access
  const win = window as any

  win.globalWS = globalWebSocketService

  const wsDebug: WsDebugInterface = {
    connect: () => globalWebSocketService.connect(),
    disconnect: () => globalWebSocketService.disconnect(),
    forceReconnect: () => globalWebSocketService.forceReconnect(),
    test: () => globalWebSocketService.testConnection(),
    state: () => globalWebSocketService.getState(),
    clearState: () => {
      localStorage.removeItem('autobot-websocket-state')
      logger.debug('WebSocket state cleared')
    }
  }
  win.wsDebug = wsDebug
}

export default globalWebSocketService
export { GlobalWebSocketService }

// Re-export types for consumers
export type {
  ConnectionState,
  EventCallback,
  WebSocketReactiveState,
  WebSocketStateSnapshot,
  WsDebugInterface
}
