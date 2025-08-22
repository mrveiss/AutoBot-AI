/**
 * Global WebSocket Service
 *
 * Provides system-wide WebSocket connectivity for RUM monitoring,
 * real-time updates, and cross-component communication.
 * Works on any page/tab, not limited to chat interface.
 */

import { ref, reactive } from 'vue'
import { API_CONFIG } from '@/config/environment.js'

class GlobalWebSocketService {
  constructor() {
    this.ws = null
    this.isConnected = ref(false)
    this.connectionState = ref('disconnected') // disconnected, connecting, connected, error
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 10  // Increased from 5
    this.reconnectDelay = 2000      // Increased from 1000ms
    this.connectionTimeout = 15000  // Increased from 10s to 15s
    this.heartbeatInterval = null   // For keepalive pings
    this.heartbeatTimeout = 30000   // Send ping every 30 seconds
    this.listeners = new Map() // event -> Set of callback functions

    // Reactive state for components to monitor
    this.state = reactive({
      connected: false,
      lastMessage: null,
      lastError: null,
      url: API_CONFIG.WS_BASE_URL
    })

    console.log('🌐 Global WebSocket Service initialized')
  }

  /**
   * Connect to WebSocket server
   */
  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('🔌 WebSocket already connected')
      return
    }

    const wsUrl = API_CONFIG.WS_BASE_URL
    console.log('🔌 Connecting to WebSocket:', wsUrl)

    this.connectionState.value = 'connecting'

    // Track connection attempt with RUM
    if (window.rum) {
      window.rum.trackWebSocketEvent('global_connection_attempt', { url: wsUrl })
    }

    try {
      this.ws = new WebSocket(wsUrl)
      this.setupEventHandlers()

      // Set connection timeout
      this.connectionTimeoutId = setTimeout(() => {
        if (this.connectionState.value === 'connecting') {
          console.error('❌ WebSocket connection timeout after', this.connectionTimeout + 'ms')
          this.handleConnectionError(new Error('Connection timeout'))
          if (this.ws) {
            this.ws.close()
          }
        }
      }, this.connectionTimeout)

    } catch (error) {
      console.error('❌ Failed to create WebSocket connection:', error)
      this.handleConnectionError(error)
    }
  }

  /**
   * Setup WebSocket event handlers
   */
  setupEventHandlers() {
    if (!this.ws) return

    this.ws.onopen = () => {
      console.log('✅ Global WebSocket connected successfully')

      // Clear connection timeout
      if (this.connectionTimeoutId) {
        clearTimeout(this.connectionTimeoutId)
        this.connectionTimeoutId = null
      }

      this.connectionState.value = 'connected'
      this.isConnected.value = true
      this.state.connected = true
      this.reconnectAttempts = 0

      // Start heartbeat to keep connection alive
      this.startHeartbeat()

      // Track with RUM
      if (window.rum) {
        window.rum.trackWebSocketEvent('global_connection_opened', {
          url: this.state.url
        })
      }

      // Notify listeners
      this.emit('connected', { url: this.state.url })
    }

    this.ws.onmessage = (event) => {
      try {
        const eventData = JSON.parse(event.data)
        console.log('📨 Global WebSocket message:', eventData.type || 'unknown', eventData)

        this.state.lastMessage = eventData

        // Track with RUM
        if (window.rum) {
          window.rum.trackWebSocketEvent('global_message_received', {
            dataSize: event.data.length,
            eventType: eventData.type || 'unknown'
          })
        }

        // Notify listeners
        this.emit('message', eventData)

        // Emit specific event type if available
        if (eventData.type) {
          this.emit(eventData.type, eventData)
        }

      } catch (error) {
        console.error('❌ Failed to parse WebSocket message:', error)
        if (window.rum) {
          window.rum.trackWebSocketEvent('global_message_parse_error', {
            error: error.message
          })
        }
      }
    }

    this.ws.onerror = (error) => {
      console.error('❌ Global WebSocket error:', error)
      this.handleConnectionError(error)
    }

    this.ws.onclose = (event) => {
      console.log('🔌 Global WebSocket closed:', event.code, event.reason)

      this.connectionState.value = 'disconnected'
      this.isConnected.value = false
      this.state.connected = false

      // Stop heartbeat
      this.stopHeartbeat()

      // Track with RUM
      if (window.rum) {
        window.rum.trackWebSocketEvent('global_connection_closed', {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean
        })
      }

      // Notify listeners
      this.emit('disconnected', {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean
      })

      // Auto-reconnect if not a clean close and not due to server shutdown
      if (!event.wasClean && event.code !== 1006 && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.scheduleReconnect()
      } else if (event.code === 1006) {
        // Connection lost unexpectedly - wait longer before reconnecting
        setTimeout(() => {
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect()
          }
        }, 5000)
      }
    }
  }

  /**
   * Handle connection errors
   */
  handleConnectionError(error) {
    console.error('❌ WebSocket connection error:', error)

    this.connectionState.value = 'error'
    this.state.lastError = error.toString()

    // Track with RUM
    if (window.rum) {
      window.rum.trackWebSocketEvent('global_connection_error', {
        error: error.toString()
      })
      window.rum.reportCriticalIssue('global_websocket_error', {
        url: this.state.url,
        error: error.toString(),
        attempts: this.reconnectAttempts
      })
    }

    // Notify listeners
    this.emit('error', error)

    // Schedule reconnect
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.scheduleReconnect()
    }
  }

  /**
   * Schedule reconnection attempt
   */
  scheduleReconnect() {
    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1) // Exponential backoff

    console.log(`🔄 Scheduling WebSocket reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`)

    setTimeout(() => {
      this.connect()
    }, delay)
  }

  /**
   * Send message through WebSocket
   */
  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = JSON.stringify(data)
      this.ws.send(message)

      // Track with RUM
      if (window.rum) {
        window.rum.trackWebSocketEvent('global_message_sent', {
          dataType: typeof data,
          dataSize: message.length
        })
      }

      return true
    } else {
      console.warn('⚠️ Cannot send WebSocket message - not connected')
      return false
    }
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
          console.error('❌ Error in WebSocket event listener:', error)
        }
      })
    }
  }

  /**
   * Test connection manually
   */
  testConnection() {
    console.log('🧪 Testing WebSocket connection...')

    if (window.rum) {
      window.rum.trackWebSocketEvent('global_test_initiated', {
        url: this.state.url
      })
    }

    if (this.isConnected.value) {
      // Send ping if connected
      this.send({ type: 'ping', timestamp: Date.now() })
    } else {
      // Attempt connection if disconnected
      this.connect()
    }
  }

  /**
   * Start heartbeat to keep connection alive
   */
  startHeartbeat() {
    this.stopHeartbeat() // Clear any existing heartbeat

    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        console.log('💓 Sending WebSocket heartbeat ping')
        this.send({
          type: 'ping',
          timestamp: Date.now(),
          source: 'global_websocket_service'
        })
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
   * Disconnect WebSocket
   */
  disconnect() {
    this.stopHeartbeat() // Stop heartbeat first

    if (this.ws) {
      console.log('🔌 Disconnecting WebSocket')
      this.ws.close(1000, 'manual disconnect')
      this.ws = null
    }
    this.reconnectAttempts = this.maxReconnectAttempts // Prevent auto-reconnect
  }

  /**
   * Get current connection state
   */
  getState() {
    return {
      connected: this.isConnected.value,
      connectionState: this.connectionState.value,
      reconnectAttempts: this.reconnectAttempts,
      ...this.state
    }
  }
}

// Create singleton instance
const globalWebSocketService = new GlobalWebSocketService()

// Auto-connect when service is created
globalWebSocketService.connect()

// Make available globally for debugging
if (typeof window !== 'undefined') {
  window.globalWS = globalWebSocketService
}

export default globalWebSocketService
export { GlobalWebSocketService }
