// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Fleet store cache slice (#19834): clearing cached data, and `$reset`. */
import type { FleetCtx } from './context'

/** Clear all cached data for a node. */
export function clearNodeCache(ctx: FleetCtx, nodeId: string): void {
  ctx.state.nodeEvents.value.delete(nodeId)
  ctx.state.certificateStatus.value.delete(nodeId)
  ctx.state.nodeUpdates.value.delete(nodeId)
  ctx.state.npuCapabilities.value.delete(nodeId)
}

/** Clear the events, certificate and update caches. */
export function clearAllCaches(ctx: FleetCtx): void {
  ctx.state.nodeEvents.value.clear()
  ctx.state.certificateStatus.value.clear()
  ctx.state.nodeUpdates.value.clear()
}

/**
 * Reset the store to its initial state. As in the SLM store, this resets the node list, the load
 * flags, the selection and the three caches above; roles, the NPU state and the update summary
 * are left as they were.
 */
export function $reset(ctx: FleetCtx): void {
  const { state } = ctx
  state.nodes.value.clear()
  state.isLoading.value = false
  state.error.value = null
  state.lastRefresh.value = null
  state.selectedNode.value = null
  clearAllCaches(ctx)
}
