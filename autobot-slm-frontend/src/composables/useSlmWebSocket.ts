// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLM WebSocket Composable
 *
 * Provides real-time WebSocket connection for fleet health updates.
 */

import { ref, onUnmounted } from 'vue'
import type { SLMWebSocketMessage, NodeHealth } from '@/types/slm'
import { getConfig } from '@/config/ssot-config'

// Use WebSocket URL from SSOT config
const config = getConfig()
const WS_URL = `${config.wsBaseUrl}/api/ws/events`

export function useSlmWebSocket() {
  const socket = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnecting = ref(false)
  const lastMessage = ref<SLMWebSocketMessage | null>(null)

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pingInterval: ReturnType<typeof setInterval> | null = null
  let reconnectAttempts = 0
  const MAX_RECONNECT_DELAY = 30000 // 30 seconds max
  const BASE_RECONNECT_DELAY = 1000 // 1 second base

  const messageHandlers = new Map<string, (data: SLMWebSocketMessage) => void>()

  function connect(): void {
    if (socket.value?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      socket.value = new WebSocket(WS_URL)
    } catch (err) {
      // SecurityError when mixed content is blocked (ws:// from https:// page)
      connected.value = false
      scheduleReconnect()
      return
    }

    socket.value.onopen = () => {
      connected.value = true
      reconnecting.value = false
      reconnectAttempts = 0 // Reset on successful connection

      // Start ping interval to keep connection alive
      pingInterval = setInterval(() => {
        if (socket.value?.readyState === WebSocket.OPEN) {
          socket.value.send(JSON.stringify({ type: 'ping' }))
        }
      }, 30000)
    }

    socket.value.onclose = () => {
      connected.value = false
      cleanup()
      scheduleReconnect()
    }

    socket.value.onerror = () => {
      connected.value = false
    }

    socket.value.onmessage = (event: MessageEvent) => {
      try {
        const message: SLMWebSocketMessage = JSON.parse(event.data)
        lastMessage.value = message

        // Call registered handlers
        const handler = messageHandlers.get(message.type)
        if (handler) {
          handler(message)
        }

        // Call node-specific handlers
        const nodeHandler = messageHandlers.get(`${message.type}:${message.node_id}`)
        if (nodeHandler) {
          nodeHandler(message)
        }
      } catch {
        // Skip invalid messages
      }
    }
  }

  function disconnect(): void {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    cleanup()
    if (socket.value) {
      socket.value.close()
      socket.value = null
    }
    connected.value = false
  }

  function cleanup(): void {
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
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

    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function subscribe(nodeId: string): void {
    if (socket.value?.readyState === WebSocket.OPEN) {
      socket.value.send(
        JSON.stringify({
          type: 'subscribe',
          node_ids: [nodeId],
        })
      )
    }
  }

  function subscribeAll(): void {
    if (socket.value?.readyState === WebSocket.OPEN) {
      socket.value.send(
        JSON.stringify({
          type: 'subscribe_all',
        })
      )
    }
  }

  function onHealthUpdate(handler: (nodeId: string, health: NodeHealth) => void): void {
    messageHandlers.set('health_update', (message) => {
      handler(message.node_id, message.data as unknown as NodeHealth)
    })
  }

  function onNodeStatus(
    handler: (nodeId: string, status: string) => void
  ): void {
    messageHandlers.set('node_status', (message) => {
      handler(message.node_id, message.data.status as string)
    })
  }

  function onDeploymentStatus(
    handler: (nodeId: string, deployment: Record<string, unknown>) => void
  ): void {
    messageHandlers.set('deployment_status', (message) => {
      handler(message.node_id, message.data)
    })
  }

  function onBackupStatus(
    handler: (nodeId: string, backup: Record<string, unknown>) => void
  ): void {
    messageHandlers.set('backup_status', (message) => {
      handler(message.node_id, message.data)
    })
  }

  function onRemediationEvent(
    handler: (nodeId: string, event: { event_type: string; success?: boolean; message?: string }) => void
  ): void {
    messageHandlers.set('remediation_event', (message) => {
      handler(message.node_id, message.data as { event_type: string; success?: boolean; message?: string })
    })
  }

  function onServiceStatus(
    handler: (nodeId: string, data: {
      service_name: string
      status: string
      action?: string
      success: boolean
      message?: string
    }) => void
  ): void {
    messageHandlers.set('service_status', (message) => {
      handler(message.node_id, message.data as {
        service_name: string
        status: string
        action?: string
        success: boolean
        message?: string
      })
    })
  }

  function onRollbackEvent(
    handler: (nodeId: string, data: {
      deployment_id: string
      event_type: string
      success?: boolean
      message?: string
    }) => void
  ): void {
    messageHandlers.set('rollback_event', (message) => {
      handler(message.node_id, message.data as {
        deployment_id: string
        event_type: string
        success?: boolean
        message?: string
      })
    })
  }

  // Cleanup on component unmount
  onUnmounted(() => {
    disconnect()
  })

  return {
    // State
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
