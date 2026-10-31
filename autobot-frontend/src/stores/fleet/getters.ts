// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Fleet store getters (#19834): computed views over `FleetState`. */
import { computed } from 'vue'
import type {
  FleetSummary,
  NodeEvent,
  NodeHealthStatus,
  SLMNode,
} from '@autobot/slm-contract'
import type { NodeCertificate } from '@/utils/slmApi/nodes'
import type { FleetState } from './context'

type NodeStatusCounts = Omit<FleetSummary, 'total_nodes'>

/** Buckets node statuses the way the dashboard counts them; unknown statuses count as offline. */
function countStatuses(nodes: Iterable<SLMNode>): NodeStatusCounts {
  const counts: NodeStatusCounts = { healthy_nodes: 0, degraded_nodes: 0, unhealthy_nodes: 0, offline_nodes: 0 }
  for (const node of nodes) {
    if (node.status === 'online') counts.healthy_nodes++
    else if (node.status === 'degraded') counts.degraded_nodes++
    else if (node.status === 'error') counts.unhealthy_nodes++
    else counts.offline_nodes++
  }
  return counts
}

function healthOf(summary: FleetSummary): NodeHealthStatus {
  if (summary.total_nodes === 0) return 'unknown'
  if (summary.unhealthy_nodes > 0 || summary.offline_nodes > 0) return 'unhealthy'
  if (summary.degraded_nodes > 0) return 'degraded'
  return 'healthy'
}

export function createFleetGetters(state: FleetState) {
  const nodeList = computed(() => Array.from(state.nodes.value.values()))

  const fleetSummary = computed<FleetSummary>(() => ({
    total_nodes: state.nodes.value.size,
    ...countStatuses(state.nodes.value.values()),
  }))

  const overallHealth = computed<NodeHealthStatus>(() => healthOf(fleetSummary.value))

  /** Events for the currently selected node */
  const selectedNodeEvents = computed<NodeEvent[]>(() => {
    if (!state.selectedNode.value) return []
    return state.nodeEvents.value.get(state.selectedNode.value.node_id) || []
  })

  /** Certificate for the currently selected node */
  const selectedNodeCertificate = computed<NodeCertificate | null>(() => {
    if (!state.selectedNode.value) return null
    return state.certificateStatus.value.get(state.selectedNode.value.node_id) || null
  })

  return { nodeList, fleetSummary, overallHealth, selectedNodeEvents, selectedNodeCertificate, ...npuGetters(state) }
}

/** NPU nodes and the nodes still open to the role (Issue #255), plus the update count (#682). */
function npuGetters(state: FleetState) {
  const npuNodes = computed<SLMNode[]>(() =>
    Array.from(state.nodes.value.values()).filter((node) => node.roles.includes('npu-worker')),
  )
  const nonNpuNodes = computed<SLMNode[]>(() =>
    Array.from(state.nodes.value.values()).filter((node) => !node.roles.includes('npu-worker')),
  )
  const nodesNeedingUpdates = computed(() => state.fleetUpdateSummary.value?.nodes_needing_updates ?? 0)
  return { npuNodes, nonNpuNodes, nodesNeedingUpdates }
}
