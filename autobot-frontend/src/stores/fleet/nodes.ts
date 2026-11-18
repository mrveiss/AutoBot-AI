// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Fleet store node slice (#19834): fetching, selection, local state and CRUD. */
import type { NodeCreate, NodeHealth, NodeRole, NodeUpdate, SLMNode } from '@autobot/slm-contract'
import { reportError, storeNode, type FleetCtx } from './context'

// ── Fetching ────────────────────────────────────────────────────────────────

/** The newest `fetchNodes` call per store: only it may publish the list, the timestamp, the error and the loading flag. */
const latestFetch = new WeakMap<FleetCtx, number>()

/** Fetch all nodes from the API. A call that a newer one has overtaken publishes nothing. */
export async function fetchNodes(ctx: FleetCtx): Promise<void> {
  const { state } = ctx
  const token = (latestFetch.get(ctx) ?? 0) + 1
  latestFetch.set(ctx, token)
  const isLatest = () => latestFetch.get(ctx) === token
  state.isLoading.value = true
  state.error.value = null
  try {
    const nodeArray = await ctx.api.getNodes()
    if (!isLatest()) return
    state.nodes.value.clear()
    for (const node of nodeArray) {
      state.nodes.value.set(node.node_id, node)
    }
    resolveSelection(ctx)
    state.lastRefresh.value = new Date()
  } catch (err) {
    if (isLatest()) reportError(ctx, err, 'Failed to fetch nodes')
    throw err
  } finally {
    if (isLatest()) state.isLoading.value = false
  }
}

/** Point the selection at the current entry of the selected node; a node no longer in the fleet clears it. */
function resolveSelection(ctx: FleetCtx): void {
  const selected = ctx.state.selectedNode.value
  if (selected) ctx.state.selectedNode.value = ctx.state.nodes.value.get(selected.node_id) ?? null
}

/** Refresh a single node from the API. */
export async function refreshNode(ctx: FleetCtx, nodeId: string): Promise<SLMNode> {
  try {
    const node = await ctx.api.getNode(nodeId)
    storeNode(ctx, nodeId, node)
    return node
  } catch (err) {
    reportError(ctx, err, `Failed to refresh node ${nodeId}`)
    throw err
  }
}

// ── Selection and local state ───────────────────────────────────────────────

/** Select a node for detail view. */
export function selectNode(ctx: FleetCtx, nodeId: string | null): void {
  if (nodeId === null) {
    ctx.state.selectedNode.value = null
    return
  }
  ctx.state.selectedNode.value = ctx.state.nodes.value.get(nodeId) || null
}

/** Update a node in local state (no API call). */
export function setNodeLocal(ctx: FleetCtx, node: SLMNode): void {
  storeNode(ctx, node.node_id, node)
}

/** Update node health in local state; the node's status follows its health. */
export function updateNodeHealth(ctx: FleetCtx, nodeId: string, health: NodeHealth): void {
  const node = ctx.state.nodes.value.get(nodeId)
  if (node) {
    node.health = health
    node.status = health.status === 'healthy' ? 'online' :
                  health.status === 'degraded' ? 'degraded' :
                  health.status === 'unhealthy' ? 'error' : 'offline'
    ctx.state.nodes.value.set(nodeId, { ...node })
  }
}

/** Update node status in local state. */
export function updateNodeStatus(ctx: FleetCtx, nodeId: string, status: string): void {
  const node = ctx.state.nodes.value.get(nodeId)
  if (node) {
    node.status = status as SLMNode['status']
    ctx.state.nodes.value.set(nodeId, { ...node })
  }
}

/** Get a node by ID from local state. */
export function getNode(ctx: FleetCtx, nodeId: string): SLMNode | undefined {
  return ctx.state.nodes.value.get(nodeId)
}

/** Remove a node from local state (no API call), with everything cached for it. */
export function removeNodeLocal(ctx: FleetCtx, nodeId: string): void {
  const { state } = ctx
  state.nodes.value.delete(nodeId)
  if (state.selectedNode.value?.node_id === nodeId) {
    state.selectedNode.value = null
  }
  state.nodeEvents.value.delete(nodeId)
  state.certificateStatus.value.delete(nodeId)
  state.nodeUpdates.value.delete(nodeId)
  state.npuCapabilities.value.delete(nodeId)
  state.npuWorkerConfigs.value.delete(nodeId)
}

// ── CRUD (API calls) ────────────────────────────────────────────────────────

/** Register a new node. */
export async function registerNode(ctx: FleetCtx, data: NodeCreate): Promise<SLMNode> {
  try {
    const node = await ctx.api.registerNode(data)
    ctx.state.nodes.value.set(node.node_id, node)
    return node
  } catch (err) {
    reportError(ctx, err, 'Failed to register node')
    throw err
  }
}

/** Delete a node via the API and remove it from local state. */
export async function deleteNode(ctx: FleetCtx, nodeId: string): Promise<void> {
  try {
    await ctx.api.deleteNode(nodeId)
    removeNodeLocal(ctx, nodeId)
  } catch (err) {
    reportError(ctx, err, `Failed to delete node ${nodeId}`)
    throw err
  }
}

/** Update node details via the API. */
export async function updateNode(ctx: FleetCtx, nodeId: string, data: NodeUpdate): Promise<SLMNode> {
  try {
    const updatedNode = await ctx.api.updateNode(nodeId, data)
    storeNode(ctx, nodeId, updatedNode)
    return updatedNode
  } catch (err) {
    reportError(ctx, err, `Failed to update node ${nodeId}`)
    throw err
  }
}

/** Update node roles via the API. */
export async function updateNodeRoles(ctx: FleetCtx, nodeId: string, roles: NodeRole[]): Promise<SLMNode> {
  try {
    const updatedNode = await ctx.api.updateNodeRoles(nodeId, roles)
    storeNode(ctx, nodeId, updatedNode)
    return updatedNode
  } catch (err) {
    reportError(ctx, err, `Failed to update roles for node ${nodeId}`)
    throw err
  }
}
