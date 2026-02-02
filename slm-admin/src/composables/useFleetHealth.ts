// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Fleet Health Composable
 *
 * Provides aggregated fleet health state management.
 *
 * @deprecated Issue #737 Phase 2 - This composable is deprecated.
 * Use the following specialized composables instead:
 * - useNodeHealth: For individual node health monitoring with WebSocket
 * - useNodeConnectionTest: For connection testing
 * - useNodeServices: For service management
 *
 * This composable will be removed in a future release.
 * Migrate to the fleet store (useFleetStore) for fleet-wide health aggregation.
 */

import { ref, computed } from 'vue'
import type { SLMNode, NodeHealth, FleetSummary, HealthStatus } from '@/types/slm'

/**
 * @deprecated Use useNodeHealth, useNodeConnectionTest, or useNodeServices instead.
 * See Issue #737 for migration details.
 */
export function useFleetHealth() {
  const nodes = ref<Map<string, SLMNode>>(new Map())
  const healthData = ref<Map<string, NodeHealth>>(new Map())
  const isLoading = ref(false)
  const error = ref<string | null>(null)

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

  function setNodes(nodeArray: SLMNode[]): void {
    nodes.value.clear()
    for (const node of nodeArray) {
      nodes.value.set(node.node_id, node)
    }
  }

  function updateNode(node: SLMNode): void {
    nodes.value.set(node.node_id, node)
  }

  function updateNodeHealth(nodeId: string, health: NodeHealth): void {
    healthData.value.set(nodeId, health)

    // Update node status based on health
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

  function getNodeHealth(nodeId: string): NodeHealth | undefined {
    return healthData.value.get(nodeId)
  }

  function getNode(nodeId: string): SLMNode | undefined {
    return nodes.value.get(nodeId)
  }

  function removeNode(nodeId: string): void {
    nodes.value.delete(nodeId)
    healthData.value.delete(nodeId)
  }

  function clear(): void {
    nodes.value.clear()
    healthData.value.clear()
    error.value = null
  }

  return {
    // State
    nodes,
    nodeList,
    healthData,
    isLoading,
    error,
    // Computed
    fleetSummary,
    overallHealth,
    // Methods
    setNodes,
    updateNode,
    updateNodeHealth,
    updateNodeStatus,
    getNodeHealth,
    getNode,
    removeNode,
    clear,
  }
}
