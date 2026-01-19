/**
 * Global WebSocket Service - Simplified and Reliable
 *
 * Provides system-wide WebSocket connectivity for RUM monitoring,
 * real-time updates, and cross-component communication.
 * Simplified from 575+ lines to focus on reliability over complexity.
 */

import { ref, reactive } from 'vue'
import { DEFAULT_CONFIG } from '@/config/defaults.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('GlobalWebSocketService')

class GlobalWebSocketService {
  constructor() {
    this.ws = null
    this.isConnected = ref(false)
    this.connectionState = ref('disconnected') // disconnected, connecting, connected, error
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5 // Reduced from 10
    this.baseDelay = 1000 // Base delay for exponential backoff
    this.maxDelay = 16000 // Cap at 16 seconds
    this.connectionTimeout = 5000 // Reduced from 10s
    this.heartbeatInterval = null
    this.heartbeatTimeout = 30000 // Send ping every 30 seconds
    this.listeners = new Map()

    // Reactive state for components
    this.state = reactive({
      connected: false,
      lastMessage: null,
      lastError: null,
      url: this.getWebSocketUrl(),
      lastConnectionAttempt: null,
      reconnectCount: 0
    })

    // Persist connection state across reloads
    this.restoreConnectionState()

    logger.debug('🌐 Global WebSocket Service initialized with URL:', this.state.url)
  }

  /**
   * Get WebSocket URL with proper environment detection
   * CRITICAL: Uses DEFAULT_CONFIG for all defaults - no hardcoded fallbacks
   */
  getWebSocketUrl() {
    try {
      // Get backend config from defaults.js (which reads from .env with fallbacks)
      const backendHost = DEFAULT_CONFIG.network.backend.host
      const backendPort = DEFAULT_CONFIG.network.backend.port
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

      // CRITICAL: Only use Vite proxy when actually running on Vite dev server
      // Vite dev server runs on port 5173, but in production build on VM1,
      // we need to connect directly to backend
      const isViteDevServer = import.meta.env.DEV && window.location.port === '5173' &&
                               window.location.hostname === 'localhost'

      if (isViteDevServer) {
        // Development mode with Vite dev server - use proxy
        // FIXED: WebSocket is at /api/ws not /ws
        const wsUrl = `${wsProtocol}//${window.location.host}/api/ws`
        logger.debug('🔗 Development WebSocket URL (via Vite proxy):', wsUrl)
        return wsUrl
      }

      // Production mode or when frontend is on VM1 - connect directly to backend
      // FIXED: WebSocket is at /api/ws not /ws
      const wsUrl = `${wsProtocol}//${backendHost}:${backendPort}/api/ws`
      logger.debug('🔗 Production WebSocket URL (direct to backend):', wsUrl)
      return wsUrl

    } catch (error) {
      logger.error('Failed to construct WebSocket URL:', error)
      // CRITICAL: Error in URL construction - this should never happen
      // If DEFAULT_CONFIG fails, something is fundamentally wrong
      throw new Error(`WebSocket URL construction failed: ${error.message}`)
    }
  }

  /**
   * Restore connection state from localStorage
   */
  restoreConnectionState() {
    try {
      const saved = localStorage.getItem('autobot-websocket-state')
      if (saved) {
        const state = JSON.parse(saved)
        this.reconnectAttempts = Math.min(state.reconnectCount || 0, 2) // Limit on restore
        this.state.reconnectCount = this.reconnectAttempts
      }
    } catch (error) {
      logger.warn('Failed to restore WebSocket state:', error)
    }
  }

  /**
   * Save connection state to localStorage
   */
  saveConnectionState() {
    try {
      const stateToSave = {
        reconnectCount: this.reconnectAttempts,
        lastAttempt: Date.now()
      }
      localStorage.setItem('autobot-websocket-state', JSON.stringify(stateToSave))
    } catch (error) {
      logger.warn('Failed to save WebSocket state:', error)
    }
  }

  /**
   * Connect to WebSocket server with simplified logic
   */
  async connect() {
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      return
    }

    this.state.lastConnectionAttempt = new Date()
    this.connectionState.value = 'connecting'

    // Clean up existing WebSocket
    this.cleanup()

    // Quick health check (optional, don't block on failure)
    this.quickHealthCheck().catch(() => {
      // Health check failed but continue with WebSocket attempt
    })

    const wsUrl = this.state.url
    logger.debug('🔌 Connecting WebSocket (attempt', this.reconnectAttempts + 1, '):', wsUrl)

    // Track with RUM if available
    this.trackEvent('connection_attempt', {
      url: wsUrl,
      attempt: this.reconnectAttempts + 1
    })

    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(wsUrl)
        this.setupEventHandlers(resolve, reject)

        // Connection timeout
        const timeoutId = setTimeout(() => {
          if (this.connectionState.value === 'connecting') {
            logger.error('❌ WebSocket connection timeout')
            this.handleConnectionError(new Error('Connection timeout'))
            this.ws?.close()
            reject(new Error('Connection timeout'))
          }
        }, this.connectionTimeout)

        // Clear timeout on connection success/failure
        this.ws.addEventListener('open', () => clearTimeout(timeoutId), { once: true })
        this.ws.addEventListener('error', () => clearTimeout(timeoutId), { once: true })

      } catch (error) {
        logger.error('❌ Failed to create WebSocket:', error)
        this.handleConnectionError(error)
        reject(error)
      }
    })
  }

  /**
   * Quick health check (non-blocking)
   */
  async quickHealthCheck() {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2000)

    try {
      // Use relative URL to go through Vite proxy in development
      const response = await fetch('/api/health', {
        signal: controller.signal,
        cache: 'no-store'
      })
      clearTimeout(timeoutId)
      return response.ok
    } catch (error) {
      clearTimeout(timeoutId)
      throw error
    }
  }

  /**
   * Setup WebSocket event handlers
   */
  setupEventHandlers(resolve, reject) {
    if (!this.ws) return

    this.ws.onopen = () => {
      logger.debug('✅ WebSocket connected successfully')

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

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.state.lastMessage = data

        // Handle ping/pong
        if (data.type === 'ping') {
          this.send({ type: 'pong', timestamp: Date.now() })
          return
        }

        if (data.type === 'pong') {
          return // Heartbeat response
        }

        // Emit to listeners
        this.emit('message', data)
        if (data.type) {
          this.emit(data.type, data)
        }

        this.trackEvent('message_received', {
          dataSize: event.data.length,
          eventType: data.type || 'unknown'
        })

      } catch (error) {
        logger.error('❌ Failed to parse WebSocket message:', error)
        this.trackEvent('message_parse_error', {
          error: error.message,
          rawDataLength: event.data?.length || 0
        })
      }
    }

    this.ws.onerror = (error) => {
      logger.error('❌ WebSocket error:', error)
      this.handleConnectionError(error)
      reject(error)
    }

    this.ws.onclose = (event) => {
      logger.debug('🔌 WebSocket closed:', {
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

      // Auto-reconnect logic
      this.scheduleReconnect(event)
    }
  }

  /**
   * Handle connection errors
   */
  handleConnectionError(error) {
    this.connectionState.value = 'error'
    this.state.lastError = error.toString()
    
    this.trackEvent('connection_error', {
      error: error.toString(),
      attempt: this.reconnectAttempts
    })

    this.trackEvent('connection_error', {
      error: error.toString(),
      attempt: this.reconnectAttempts
    })

    this.emit('error', error)
  }

  /**
   * Schedule reconnection with exponential backoff
   */
  scheduleReconnect(event) {
    // Don't reconnect on normal closure or manual disconnect
    if (event.code === 1000 || event.code === 3000) {
      return
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      logger.debug('❌ Max reconnection attempts reached')
      this.state.lastError = `Connection failed after ${this.reconnectAttempts} attempts`
      return
    }

    this.reconnectAttempts++
    this.state.reconnectCount = this.reconnectAttempts

    // Exponential backoff with jitter
    const backoffDelay = Math.min(
      this.baseDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxDelay
    )
    const jitter = Math.random() * 1000 // Add up to 1s of jitter
    const delay = backoffDelay + jitter

    logger.debug(`🔄 Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`)

    setTimeout(() => {
      if (this.connectionState.value !== 'connected') {
        this.connect().catch(error => {
          logger.error('Reconnection failed:', error)
        })
      }
    }, delay)
  }

  /**
   * Send message through WebSocket
   */
  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        const message = JSON.stringify(data)
        this.ws.send(message)

        this.trackEvent('message_sent', {
          dataType: typeof data,
          dataSize: message.length,
          messageType: data.type || 'unknown'
        })

        return true
      } catch (error) {
        logger.error('❌ Failed to send WebSocket message:', error)
        return false
      }
    } else {
      logger.warn('⚠️ Cannot send message - WebSocket not connected')
      return false
    }
  }

  /**
   * Start heartbeat to keep connection alive
   */
  startHeartbeat() {
    this.stopHeartbeat()

    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping', timestamp: Date.now() })
      } else {
        this.stopHeartbeat()
      }
    }, this.heartbeatTimeout)
  }

  /**
   * Stop heartbeat
   */
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  /**
   * Clean up WebSocket connection
   */
  cleanup() {
    this.stopHeartbeat()

    if (this.ws) {
      // Remove event listeners to prevent memory leaks
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

  /**
   * Disconnect cleanly
   */
  disconnect() {
    logger.debug('🔌 Disconnecting WebSocket')
    this.reconnectAttempts = this.maxReconnectAttempts // Prevent auto-reconnect
    this.cleanup()
    this.connectionState.value = 'disconnected'
    this.isConnected.value = false
    this.state.connected = false
  }

  /**
   * Force reconnection
   */
  forceReconnect() {
    logger.debug('🔄 Forcing WebSocket reconnection')
    this.reconnectAttempts = 0
    this.state.reconnectCount = 0
    this.disconnect()
    setTimeout(() => this.connect(), 1000)
  }

  /**
   * Add event listener
   */
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event).add(callback)

    // Return unsubscribe function
    return () => {
      const listeners = this.listeners.get(event)
      if (listeners) {
        listeners.delete(callback)
      }
    }
  }

  /**
   * Subscribe to a topic/event - alias for on() method
   * Provides compatibility with code expecting subscribe/unsubscribe API pattern
   * @param {string} topic - The topic/event to subscribe to
   * @param {Function} callback - Callback function for messages
   * @returns {Function} Unsubscribe function
   */
  subscribe(topic, callback) {
    return this.on(topic, callback)
  }

  /**
   * Unsubscribe from a topic - alias for off() method
   * @param {string} topic - The topic/event to unsubscribe from
   * @param {Function} callback - The callback to remove
   */
  unsubscribe(topic, callback) {
    this.off(topic, callback)
  }

  /**
   * Remove event listener
   */
  off(event, callback) {
    const listeners = this.listeners.get(event)
    if (listeners) {
      listeners.delete(callback)
    }
  }

  /**
   * Emit event to listeners
   */
  emit(event, data) {
    const listeners = this.listeners.get(event)
    if (listeners) {
      listeners.forEach(callback => {
        try {
          callback(data)
        } catch (error) {
          logger.error('❌ Error in WebSocket event listener:', error)
        }
      })
    }
  }

  /**
   * Track events with RUM if available
   * Made resilient to RUM initialization issues
   */
  trackEvent(eventType, data) {
    try {
      if (window.rum && typeof window.rum.trackWebSocketEvent === 'function') {
        window.rum.trackWebSocketEvent(`global_${eventType}`, data)
      } else if (window.rum && typeof window.rum.trackEvent === 'function') {
        // Fallback to generic trackEvent if trackWebSocketEvent doesn't exist
        window.rum.trackEvent('websocket', {
          type: `global_${eventType}`,
          ...data
        })
      }
    } catch (error) {
      // Silently fail - RUM tracking is optional and shouldn't break WebSocket
      logger.debug('[GlobalWebSocketService] RUM tracking not available:', error.message)
    }
  }

  /**
   * Get current connection state
   */
  getState() {
    return {
      connected: this.isConnected.value,
      connectionState: this.connectionState.value,
      reconnectAttempts: this.reconnectAttempts,
      maxReconnectAttempts: this.maxReconnectAttempts,
      readyState: this.ws?.readyState,
      ...this.state
    }
  }

  /**
   * Test connection
   */
  async testConnection() {
    logger.debug('🧪 Testing WebSocket connection...')

    if (this.isConnected.value) {
      return new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(false), 5000)

        const handlePong = () => {
          clearTimeout(timeout)
          this.off('pong', handlePong)
          resolve(true)
        }

        this.on('pong', handlePong)
        this.send({ type: 'ping', timestamp: Date.now(), test: true })
      })
    } else {
      try {
        await this.connect()
        return this.isConnected.value
      } catch (_error) {
        return false
      }
    }
  }
}

// Create singleton instance
const globalWebSocketService = new GlobalWebSocketService()

// Auto-connect with delay to allow app initialization
// Only connect if this is the first import and not already connected
if (typeof window !== 'undefined' && !window._autobotWebSocketInitialized) {
  window._autobotWebSocketInitialized = true

  setTimeout(() => {
    if (!globalWebSocketService.isConnected.value && globalWebSocketService.connectionState.value !== 'connecting') {
      globalWebSocketService.connect().catch(error => {
        logger.error('Initial WebSocket connection failed:', error)
      })
    }
  }, 500) // Reduced delay
}

// Global debugging interface
if (typeof window !== 'undefined') {
  window.globalWS = globalWebSocketService

  window.wsDebug = {
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
}

export default globalWebSocketService
export { GlobalWebSocketService }