// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Fleet store NPU slice (#19834): NPU fleet integration (#255) and metrics/config (#590). */
import type {
  NodeRole,
  NPUFleetMetrics,
  NPULoadBalancingConfig,
  NPUNodeStatus,
  NPUWorkerConfig,
  NPUWorkerMetrics,
  SLMNode,
} from '@autobot/slm-contract'
import { reportError, type FleetCtx } from './context'

/** Fetch every NPU node with its status; the cache is replaced. A failure yields []. */
export async function fetchNpuNodes(ctx: FleetCtx): Promise<NPUNodeStatus[]> {
  try {
    const npuStatuses = await ctx.api.getNpuNodes()
    ctx.state.npuCapabilities.value.clear()
    for (const status of npuStatuses) {
      ctx.state.npuCapabilities.value.set(status.node_id, status)
    }
    return npuStatuses
  } catch (err) {
    reportError(ctx, err, 'Failed to fetch NPU nodes')
    return []
  }
}

/** Fetch the NPU status of one node. A failure yields null. */
export async function fetchNpuStatus(ctx: FleetCtx, nodeId: string): Promise<NPUNodeStatus | null> {
  try {
    const status = await ctx.api.getNpuStatus(nodeId)
    ctx.state.npuCapabilities.value.set(nodeId, status)
    return status
  } catch (err) {
    reportError(ctx, err, `Failed to fetch NPU status for node ${nodeId}`)
    return null
  }
}

/** Fetch the NPU status of every node holding the npu-worker role. */
export async function fetchAllNpuStatus(ctx: FleetCtx): Promise<void> {
  const npuNodeList = Array.from(ctx.state.nodes.value.values()).filter((node) => node.roles.includes('npu-worker'))
  await Promise.all(npuNodeList.map((node) => fetchNpuStatus(ctx, node.node_id)))
}

/** Trigger NPU capability detection for a node. A failure yields false. */
export async function triggerNpuDetection(ctx: FleetCtx, nodeId: string, force: boolean = false): Promise<boolean> {
  try {
    const result = await ctx.api.triggerNpuDetection(nodeId, force)
    if (result.success && result.capabilities) {
      const existing = ctx.state.npuCapabilities.value.get(nodeId)
      if (existing) {
        ctx.state.npuCapabilities.value.set(nodeId, {
          ...existing,
          capabilities: result.capabilities,
          detectionStatus: 'detected',
        })
      }
    }
    return result.success
  } catch (err) {
    reportError(ctx, err, `Failed to trigger NPU detection for node ${nodeId}`)
    return false
  }
}

/** The cached NPU status of a node. */
export function getNpuStatus(ctx: FleetCtx, nodeId: string): NPUNodeStatus | undefined {
  return ctx.state.npuCapabilities.value.get(nodeId)
}

function requireNode(ctx: FleetCtx, nodeId: string): SLMNode {
  const node = ctx.state.nodes.value.get(nodeId)
  if (!node) {
    throw new Error(`Node ${nodeId} not found`)
  }
  return node
}

/** Assign the npu-worker role through the dedicated NPU endpoint, which also triggers detection. */
export async function assignNpuRole(ctx: FleetCtx, nodeId: string): Promise<SLMNode> {
  const node = requireNode(ctx, nodeId)
  try {
    const result = await ctx.api.assignNpuRole(nodeId)
    if (!result.success) {
      throw new Error(result.message)
    }
    const updatedNode: SLMNode = { ...node, roles: [...node.roles, 'npu-worker'] as NodeRole[] }
    ctx.state.nodes.value.set(nodeId, updatedNode)
    if (result.detection_triggered) {
      await fetchNpuStatus(ctx, nodeId)
    }
    return updatedNode
  } catch (err) {
    reportError(ctx, err, `Failed to assign NPU role to node ${nodeId}`)
    throw err
  }
}

/** Remove the npu-worker role through the dedicated NPU endpoint, which cleans up NPU data. */
export async function removeNpuRole(ctx: FleetCtx, nodeId: string): Promise<SLMNode> {
  const node = requireNode(ctx, nodeId)
  try {
    const result = await ctx.api.removeNpuRole(nodeId)
    if (!result.success) {
      throw new Error(result.message)
    }
    const updatedNode: SLMNode = { ...node, roles: node.roles.filter((r) => r !== 'npu-worker') as NodeRole[] }
    ctx.state.nodes.value.set(nodeId, updatedNode)
    ctx.state.npuCapabilities.value.delete(nodeId)
    return updatedNode
  } catch (err) {
    reportError(ctx, err, `Failed to remove NPU role from node ${nodeId}`)
    throw err
  }
}

/** Update the NPU load balancing configuration. */
export async function updateNpuLoadBalancing(ctx: FleetCtx, config: NPULoadBalancingConfig): Promise<void> {
  try {
    await ctx.api.updateNpuLoadBalancing(config)
    ctx.state.npuLoadBalancingConfig.value = config
  } catch (err) {
    reportError(ctx, err, 'Failed to update NPU load balancing configuration')
    throw err
  }
}

/** Fetch the current NPU load balancing configuration. A failure yields null. */
export async function fetchNpuLoadBalancing(ctx: FleetCtx): Promise<NPULoadBalancingConfig | null> {
  try {
    const config = await ctx.api.getNpuLoadBalancing()
    ctx.state.npuLoadBalancingConfig.value = config
    return config
  } catch (err) {
    reportError(ctx, err, 'Failed to fetch NPU load balancing configuration')
    return null
  }
}

/** Fetch the fleet-level NPU metrics. A failure yields null. */
export async function fetchNpuFleetMetrics(ctx: FleetCtx): Promise<NPUFleetMetrics | null> {
  try {
    const metrics = await ctx.api.getNpuFleetMetrics()
    ctx.state.npuFleetMetrics.value = metrics
    return metrics
  } catch (err) {
    reportError(ctx, err, 'Failed to fetch NPU fleet metrics')
    return null
  }
}

/** Fetch the NPU metrics of one node. A failure yields null. */
export async function fetchNpuNodeMetrics(ctx: FleetCtx, nodeId: string): Promise<NPUWorkerMetrics | null> {
  try {
    return await ctx.api.getNpuNodeMetrics(nodeId)
  } catch (err) {
    reportError(ctx, err, `Failed to fetch metrics for node ${nodeId}`)
    return null
  }
}

/** Fetch the NPU worker config of one node. A failure yields null. */
export async function fetchNpuWorkerConfig(ctx: FleetCtx, nodeId: string): Promise<NPUWorkerConfig | null> {
  try {
    const config = await ctx.api.getNpuWorkerConfig(nodeId)
    ctx.state.npuWorkerConfigs.value.set(nodeId, config)
    return config
  } catch (err) {
    reportError(ctx, err, `Failed to fetch config for node ${nodeId}`)
    return null
  }
}

/** Update the NPU worker config of one node. A failure yields false. */
export async function updateNpuWorkerConfig(ctx: FleetCtx, nodeId: string, config: NPUWorkerConfig): Promise<boolean> {
  try {
    const result = await ctx.api.updateNpuWorkerConfig(nodeId, config)
    if (result.success) {
      ctx.state.npuWorkerConfigs.value.set(nodeId, result.config)
    }
    return result.success
  } catch (err) {
    reportError(ctx, err, `Failed to update config for node ${nodeId}`)
    return false
  }
}
