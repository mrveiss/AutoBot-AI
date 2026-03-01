// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLM WebSocket Composable (Singleton)
 *
 * Provides a shared real-time WebSocket connection for fleet health updates.
 * All components share a single connection via module-level state.
 * Issue #1248: Prevents multiple simultaneous connections and thundering
 * herd reconnection during backend restarts.
 */

import { ref, onUnmounted } from 'vue'
import type { SLMWebSocketMessage, NodeHealth } from '@/types/slm'
import { getConfig } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SlmWebSocket')

// Use WebSocket URL from SSOT config
const config = getConfig()
const WS_URL = `${config.wsBaseUrl}/api/ws/events`

// --- Module-level singleton state ---
const socket = ref<WebSocket | null>(null)
const connected = ref(false)
const reconnecting = ref(false)
const lastMessage = ref<SLMWebSocketMessage | null>(null)

let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pingInterval: ReturnType<typeof setInterval> | null = null
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 30000 // 30 seconds max
const BASE_RECONNECT_DELAY = 1000 // 1 second base

// Multiple handlers per event type (supports many components)
type MessageHandler = (data: SLMWebSocketMessage) => void
const messageHandlers = new Map<string, Set<MessageHandler>>()

// Issue #988: Track subscription intent so it can be sent once socket opens
let subscribeAllPending = false
const pendingNodeSubscriptions = new Set<string>()

// Reference counting for consumer lifecycle
let consumerCount = 0

// --- Shared connection logic ---

function addHandler(key: string, handler: MessageHandler): void {
  if (!messageHandlers.has(key)) {
    messageHandlers.set(key, new Set())
  }
  messageHandlers.get(key)!.add(handler)
}

function removeHandler(key: string, handler: MessageHandler): void {
  const handlers = messageHandlers.get(key)
  if (handlers) {
    handlers.delete(handler)
    if (handlers.size === 0) {
      messageHandlers.delete(key)
    }
  }
}

function dispatchMessage(message: SLMWebSocketMessage): void {
  // Call handlers for this event type
  const handlers = messageHandlers.get(message.type)
  if (handlers) {
    for (const handler of handlers) {
      handler(message)
    }
  }

  // Call node-specific handlers
  if (message.node_id) {
    const nodeKey = `${message.type}:${message.node_id}`
    const nodeHandlers = messageHandlers.get(nodeKey)
    if (nodeHandlers) {
      for (const handler of nodeHandlers) {
        handler(message)
      }
    }
  }
}

function cleanupTimers(): void {
  if (pingInterval) {
    clearInterval(pingInterval)
    pingInterval = null
  }
}

function doConnect(): void {
  // Guard: skip if already open or connecting
  if (
    socket.value?.readyState === WebSocket.OPEN ||
    socket.value?.readyState === WebSocket.CONNECTING
  ) {
    return
  }

  try {
    socket.value = new WebSocket(WS_URL)
  } catch {
    // SecurityError when mixed content is blocked (ws:// from https:// page)
    connected.value = false
    scheduleReconnect()
    return
  }

  socket.value.onopen = () => {
    connected.value = true
    reconnecting.value = false
    reconnectAttempts = 0

    logger.debug('WebSocket connected')

    // Issue #988: Resend pending subscriptions after (re)connect
    if (subscribeAllPending) {
      socket.value?.send(JSON.stringify({ type: 'subscribe_all' }))
    }
    if (pendingNodeSubscriptions.size > 0) {
      socket.value?.send(
        JSON.stringify({
          type: 'subscribe',
          node_ids: Array.from(pendingNodeSubscriptions),
        })
      )
    }

    // Start ping interval to keep connection alive
    pingInterval = setInterval(() => {
      if (socket.value?.readyState === WebSocket.OPEN) {
        socket.value.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
  }

  socket.value.onclose = () => {
    connected.value = false
    cleanupTimers()
    // Only reconnect if there are still active consumers
    if (consumerCount > 0) {
      scheduleReconnect()
    }
  }

  socket.value.onerror = () => {
    connected.value = false
  }

  socket.value.onmessage = (event: MessageEvent) => {
    try {
      const message: SLMWebSocketMessage = JSON.parse(event.data)
      lastMessage.value = message
      dispatchMessage(message)
    } catch {
      // Skip invalid messages
    }
  }
}

function doDisconnect(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  cleanupTimers()
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
  connected.value = false
  reconnecting.value = false
}

async function checkBackendHealth(): Promise<boolean> {
  try {
    const resp = await fetch(`${config.apiBaseUrl}/api/health`, {
      signal: AbortSignal.timeout(3000),
    })
    return resp.ok
  } catch {
    return false
  }
}

function scheduleReconnect(): void {
  if (reconnectTimer) return

  reconnecting.value = true

  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, up to 30s max
  const delay = Math.min(
    BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts),
    MAX_RECONNECT_DELAY
  )
  reconnectAttempts++

  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null
    // Issue #1248: Check backend health before attempting WS connection
    // to avoid hammering a dead backend with failed WS handshakes
    const healthy = await checkBackendHealth()
    if (healthy) {
      doConnect()
    } else {
      logger.debug('Backend not healthy, deferring WebSocket reconnect')
      scheduleReconnect()
    }
  }, delay)
}

function doSubscribe(nodeId: string): void {
  pendingNodeSubscriptions.add(nodeId)
  if (socket.value?.readyState === WebSocket.OPEN) {
    socket.value.send(
      JSON.stringify({ type: 'subscribe', node_ids: [nodeId] })
    )
  }
}

function doSubscribeAll(): void {
  subscribeAllPending = true
  if (socket.value?.readyState === WebSocket.OPEN) {
    socket.value.send(JSON.stringify({ type: 'subscribe_all' }))
  }
}

// --- Per-component composable ---

export function useSlmWebSocket() {
  // Track this instance's handlers for cleanup on unmount
  const instanceHandlers: Array<{ key: string; fn: MessageHandler }> = []

  consumerCount++

  function registerHandler(
    key: string,
    fn: MessageHandler
  ): void {
    addHandler(key, fn)
    instanceHandlers.push({ key, fn })
  }

  function connect(): void {
    doConnect()
  }

  function disconnect(): void {
    doDisconnect()
  }

  function subscribe(nodeId: string): void {
    doSubscribe(nodeId)
  }

  function subscribeAll(): void {
    doSubscribeAll()
  }

  function onHealthUpdate(
    handler: (nodeId: string, health: NodeHealth) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(
        message.node_id,
        message.data as unknown as NodeHealth
      )
    }
    registerHandler('health_update', fn)
  }

  function onNodeStatus(
    handler: (nodeId: string, status: string) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(message.node_id, message.data.status as string)
    }
    registerHandler('node_status', fn)
  }

  function onDeploymentStatus(
    handler: (
      nodeId: string,
      deployment: Record<string, unknown>
    ) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(message.node_id, message.data)
    }
    registerHandler('deployment_status', fn)
  }

  function onBackupStatus(
    handler: (
      nodeId: string,
      backup: Record<string, unknown>
    ) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(message.node_id, message.data)
    }
    registerHandler('backup_status', fn)
  }

  function onRemediationEvent(
    handler: (
      nodeId: string,
      event: {
        event_type: string
        success?: boolean
        message?: string
      }
    ) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(message.node_id, message.data as {
        event_type: string
        success?: boolean
        message?: string
      })
    }
    registerHandler('remediation_event', fn)
  }

  function onServiceStatus(
    handler: (
      nodeId: string,
      data: {
        service_name: string
        status: string
        action?: string
        success: boolean
        message?: string
      }
    ) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(message.node_id, message.data as {
        service_name: string
        status: string
        action?: string
        success: boolean
        message?: string
      })
    }
    registerHandler('service_status', fn)
  }

  function onRollbackEvent(
    handler: (
      nodeId: string,
      data: {
        deployment_id: string
        event_type: string
        success?: boolean
        message?: string
      }
    ) => void
  ): void {
    const fn: MessageHandler = (message) => {
      handler(message.node_id, message.data as {
        deployment_id: string
        event_type: string
        success?: boolean
        message?: string
      })
    }
    registerHandler('rollback_event', fn)
  }

  // Cleanup on component unmount
  onUnmounted(() => {
    // Remove this instance's handlers
    for (const { key, fn } of instanceHandlers) {
      removeHandler(key, fn)
    }
    consumerCount--
    // Only disconnect when no consumers remain
    if (consumerCount <= 0) {
      doDisconnect()
      consumerCount = 0
    }
  })

  return {
    // State (shared refs — reactive across all consumers)
    connected,
    reconnecting,
    lastMessage,
    // Methods
    connect,
    disconnect,
    subscribe,
    subscribeAll,
    // Event handlers
    onHealthUpdate,
    onNodeStatus,
    onDeploymentStatus,
    onBackupStatus,
    onRemediationEvent,
    onServiceStatus,
    onRollbackEvent,
  }
}
