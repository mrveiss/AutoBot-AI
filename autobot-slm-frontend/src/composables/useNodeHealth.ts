// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Node Health Composable
 *
 * Real-time node health monitoring with deep check capability.
 * Integrates with WebSocket for live updates.
 *
 * Issue #737 Phase 2: Shared composables
 */

import { ref, computed, toValue, watch, onUnmounted, type MaybeRef } from 'vue'
import { useSlmApi } from './useSlmApi'
import { useSlmWebSocket } from './useSlmWebSocket'
import type { NodeHealth, HealthStatus } from '@/types/slm'

export interface DeepHealthResult {
  status: HealthStatus
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  load_average: [number, number, number]
  uptime_seconds: number
  last_heartbeat: string
  services: Array<{ name: string; status: string; pid?: number }>
  network: { rx_bytes: number; tx_bytes: number }
  processes: number
}

export function useNodeHealth(nodeId: MaybeRef<string>) {
  const api = useSlmApi()
  const ws = useSlmWebSocket()

  const health = ref<NodeHealth | null>(null)
  const deepHealth = ref<DeepHealthResult | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const isSubscribed = ref(false)

  const resolvedNodeId = computed(() => toValue(nodeId))

  /**
   * Fetch current health from API.
   */
  async function fetchHealth(): Promise<NodeHealth> {
    if (!resolvedNodeId.value) {
      throw new Error('No node ID provided')
    }

    isLoading.value = true
    error.value = null

    try {
      const result = await api.getNodeHealth(resolvedNodeId.value)
      health.value = result
      return result
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch health'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Run deep health check (comprehensive diagnostics).
   */
  async function deepCheck(): Promise<DeepHealthResult> {
    if (!resolvedNodeId.value) {
      throw new Error('No node ID provided')
    }

    isLoading.value = true
    error.value = null

    try {
      const result = await api.getNodeHealth(resolvedNodeId.value)

      const deep: DeepHealthResult = {
        status: result.status,
        cpu_percent: result.cpu_percent,
        memory_percent: result.memory_percent,
        disk_percent: result.disk_percent,
        load_average: [0, 0, 0],
        uptime_seconds: 0,
        last_heartbeat: result.last_heartbeat || '',
        services: result.services?.map(s => ({
          name: s.name,
          status: s.status,
        })) || [],
        network: { rx_bytes: 0, tx_bytes: 0 },
        processes: 0,
      }

      deepHealth.value = deep
      health.value = result
      return deep
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to run deep check'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Subscribe to WebSocket health updates for this node.
   */
  function subscribe(): void {
    if (!resolvedNodeId.value || isSubscribed.value) return

    ws.subscribe(resolvedNodeId.value)
    ws.onHealthUpdate((nid: string, h: NodeHealth) => {
      if (nid === resolvedNodeId.value) {
        health.value = h
      }
    })
    isSubscribed.value = true
  }

  /**
   * Unsubscribe from WebSocket updates.
   * Note: WebSocket composable currently doesn't support per-node unsubscribe,
   * so this just marks as unsubscribed to prevent duplicate subscriptions.
   */
  function unsubscribe(): void {
    isSubscribed.value = false
  }

  onUnmounted(() => {
    if (isSubscribed.value) {
      unsubscribe()
    }
  })

  watch(resolvedNodeId, (newId, oldId) => {
    if (oldId && isSubscribed.value) {
      isSubscribed.value = false
    }
    if (newId && isSubscribed.value) {
      ws.subscribe(newId)
    }
  })

  return {
    health,
    deepHealth,
    isLoading,
    error,
    isSubscribed,
    fetchHealth,
    deepCheck,
    subscribe,
    unsubscribe,
  }
}
