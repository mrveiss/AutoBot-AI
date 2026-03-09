/**
 * Live Event Service - Scoped Real-Time Events (#1408)
 *
 * Channel-aware WebSocket client for entity-scoped event streaming.
 * Supports channels: agent:{id}, task:{id}, workflow:{id}, global
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'
type LiveEventCallback = (event: LiveEvent) => void

/** Parsed live event received from the server */
export interface LiveEvent {
  type: 'live_event'
  channel: string
  event_type: string
  event_id: number
  payload: Record<string, unknown>
}

type ServerMessage =
  | LiveEvent
  | { type: 'connection_established'; message: string }
  | { type: 'subscribed'; channel: string }
  | { type: 'unsubscribed'; channel: string }
  | { type: 'pong' }
  | { type: 'ping' }
  | { type: 'error'; message: string }

const logger = createLogger('LiveEventService')

class LiveEventService {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private readonly maxReconnectAttempts = 5
  private readonly baseDelay = 1000
  private readonly maxDelay = 16000
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null
  private readonly heartbeatTimeout = 30000

  private readonly subscribedChannels = new Set<string>()
  private readonly channelListeners = new Map<string, Set<LiveEventCallback>>()

  readonly isConnected: Ref<boolean> = ref(false)
  readonly connectionState: Ref<ConnectionState> = ref('disconnected')

  private getUrl(token?: string): string {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const base = `${wsProtocol}//${window.location.host}/api/ws/live`
    return token ? `${base}?token=${encodeURIComponent(token)}` : base
  }

  async connect(token?: string): Promise<void> {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING ||
        this.ws.readyState === WebSocket.OPEN)
    ) {
      return
    }
    this.connectionState.value = 'connecting'
    this._cleanup()
    const url = this.getUrl(token)
    logger.debug('Connecting LiveEventService', { attempt: this.reconnectAttempts + 1 })
    return new Promise<void>((resolve, reject) => {
      try {
        this.ws = new WebSocket(url)
      } catch (err: unknown) {
        this._handleError(err)
        reject(err)
        return
      }
      const timeout = setTimeout(() => {
        this._handleError(new Error('Connection timeout'))
        this.ws?.close()
        reject(new Error('Connection timeout'))
      }, 5000)
      this.ws.onopen = () => {
        clearTimeout(timeout)
        this._onOpen(resolve)
      }
      this.ws.onmessage = (ev: MessageEvent) => this._onMessage(ev)
      this.ws.onerror = (ev: Event) => {
        clearTimeout(timeout)
        this._handleError(ev)
        reject(ev)
      }
      this.ws.onclose = (ev: CloseEvent) => {
        clearTimeout(timeout)
        this._onClose(ev)
      }
    })
  }

  private _onOpen(resolve: () => void): void {
    logger.debug('LiveEventService connected')
    this.connectionState.value = 'connected'
    this.isConnected.value = true
    this.reconnectAttempts = 0
    this._startHeartbeat()
    for (const channel of this.subscribedChannels) {
      this._sendAction('subscribe', channel)
    }
    resolve()
  }

  private _onMessage(event: MessageEvent): void {
    let msg: ServerMessage
    try {
      msg = JSON.parse(event.data as string) as ServerMessage
    } catch {
      logger.error('Failed to parse live event message')
      return
    }
    if (msg.type === 'ping') {
      this._send({ action: 'ping' })
      return
    }
    if (msg.type === 'pong') return
    if (
      msg.type === 'error' ||
      msg.type === 'connection_established' ||
      msg.type === 'subscribed' ||
      msg.type === 'unsubscribed'
    ) {
      logger.debug('Server ack:', msg.type)
      return
    }
    if (msg.type === 'live_event') {
      this._dispatchLiveEvent(msg as LiveEvent)
    }
  }

  private _dispatchLiveEvent(event: LiveEvent): void {
    const listeners = this.channelListeners.get(event.channel)
    if (listeners) {
      listeners.forEach((cb) => {
        try {
          cb(event)
        } catch (err: unknown) {
          logger.error('Error in live event listener:', err)
        }
      })
    }
  }

  private _onClose(event: CloseEvent): void {
    logger.debug('LiveEventService closed', { code: event.code, reason: event.reason })
    this.connectionState.value = 'disconnected'
    this.isConnected.value = false
    this._stopHeartbeat()
    this._scheduleReconnect(event)
  }

  private _handleError(error: unknown): void {
    this.connectionState.value = 'error'
    logger.error('LiveEventService error:', error)
  }

  private _scheduleReconnect(event: CloseEvent): void {
    if (event.code === 1000 || event.code === 4001) return
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      logger.debug('LiveEventService: max reconnect attempts reached')
      return
    }
    this.reconnectAttempts++
    const delay = Math.min(
      this.baseDelay * Math.pow(2, this.reconnectAttempts - 1) + Math.random() * 1000,
      this.maxDelay
    )
    logger.debug(
      `LiveEventService: reconnecting in ${Math.round(delay)}ms (${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    )
    setTimeout(() => {
      if (this.connectionState.value !== 'connected') {
        this.connect().catch((err: unknown) =>
          logger.error('LiveEventService reconnect failed:', err)
        )
      }
    }, delay)
  }

  /**
   * Subscribe to a channel and register a callback.
   * Returns an unsubscribe function.
   */
  subscribe(channel: string, callback: LiveEventCallback): () => void {
    if (!this.channelListeners.has(channel)) {
      this.channelListeners.set(channel, new Set())
    }
    this.channelListeners.get(channel)!.add(callback)
    const isNew = !this.subscribedChannels.has(channel)
    this.subscribedChannels.add(channel)
    if (isNew && this.isConnected.value) {
      this._sendAction('subscribe', channel)
    }
    return () => this.unsubscribe(channel, callback)
  }

  unsubscribe(channel: string, callback: LiveEventCallback): void {
    const listeners = this.channelListeners.get(channel)
    if (!listeners) return
    listeners.delete(callback)
    if (listeners.size === 0) {
      this.channelListeners.delete(channel)
      this.subscribedChannels.delete(channel)
      if (this.isConnected.value) {
        this._sendAction('unsubscribe', channel)
      }
    }
  }

  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts
    this._cleanup()
    this.connectionState.value = 'disconnected'
    this.isConnected.value = false
  }

  private _sendAction(action: 'subscribe' | 'unsubscribe', channel: string): void {
    this._send({ action, channel })
  }

  private _send(data: Record<string, unknown>): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(data))
        return true
      } catch (err: unknown) {
        logger.error('LiveEventService send error:', err)
      }
    }
    return false
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat()
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this._send({ action: 'ping' })
      } else {
        this._stopHeartbeat()
      }
    }, this.heartbeatTimeout)
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  private _cleanup(): void {
    this._stopHeartbeat()
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
}

const liveEventService = new LiveEventService()
export default liveEventService
export { LiveEventService }
