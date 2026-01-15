// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Fleet Store
 *
 * Pinia store for global fleet state management.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SLMNode, NodeHealth, FleetSummary, HealthStatus } from '@/types/slm'
import { useSlmApi } from '@/composables/useSlmApi'

export const useFleetStore = defineStore('fleet', () => {
  const api = useSlmApi()

  // State
  const nodes = ref<Map<string, SLMNode>>(new Map())
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastRefresh = ref<Date | null>(null)

  // Getters
  const nodeList = computed(() => Array.from(nodes.value.values()))

  const fleetSummary = computed<FleetSummary>(() => {
    let healthy = 0
    let degraded = 0
    let unhealthy = 0
    let offline = 0

    for (const node of nodes.value.values()) {
      switch (node.status) {
        case 'healthy':
          healthy++
          break
        case 'degraded':
          degraded++
          break
        case 'unhealthy':
          unhealthy++
          break
        case 'offline':
          offline++
          break
        default:
          offline++
      }
    }

    return {
      total_nodes: nodes.value.size,
      healthy_nodes: healthy,
      degraded_nodes: degraded,
      unhealthy_nodes: unhealthy,
      offline_nodes: offline,
    }
  })

  const overallHealth = computed<HealthStatus>(() => {
    const summary = fleetSummary.value
    if (summary.total_nodes === 0) return 'unknown'
    if (summary.unhealthy_nodes > 0 || summary.offline_nodes > 0) return 'unhealthy'
    if (summary.degraded_nodes > 0) return 'degraded'
    return 'healthy'
  })

  // Actions
  async function fetchNodes(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const nodeArray = await api.getNodes()
      nodes.value.clear()
      for (const node of nodeArray) {
        nodes.value.set(node.node_id, node)
      }
      lastRefresh.value = new Date()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch nodes'
    } finally {
      isLoading.value = false
    }
  }

  function updateNode(node: SLMNode): void {
    nodes.value.set(node.node_id, node)
  }

  function updateNodeHealth(nodeId: string, health: NodeHealth): void {
    const node = nodes.value.get(nodeId)
    if (node) {
      node.health = health
      node.status = health.status === 'healthy' ? 'healthy' :
                    health.status === 'degraded' ? 'degraded' :
                    health.status === 'unhealthy' ? 'unhealthy' : 'offline'
      nodes.value.set(nodeId, { ...node })
    }
  }

  function updateNodeStatus(nodeId: string, status: string): void {
    const node = nodes.value.get(nodeId)
    if (node) {
      node.status = status as SLMNode['status']
      nodes.value.set(nodeId, { ...node })
    }
  }

  function getNode(nodeId: string): SLMNode | undefined {
    return nodes.value.get(nodeId)
  }

  function removeNode(nodeId: string): void {
    nodes.value.delete(nodeId)
  }

  return {
    // State
    nodes,
    isLoading,
    error,
    lastRefresh,
    // Getters
    nodeList,
    fleetSummary,
    overallHealth,
    // Actions
    fetchNodes,
    updateNode,
    updateNodeHealth,
    updateNodeStatus,
    getNode,
    removeNode,
  }
})
