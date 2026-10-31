// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Fleet store lifecycle slice (#19834): enrollment, connection test, certificates, events,
 * updates, the fleet update summary and roles.
 */
import type {
  ConnectionTestResult,
  NodeEvent,
  NodeEventFilters,
  NodeUpdateCheckResponse,
  NodeUpdateSummary,
  RoleInfo,
} from '@autobot/slm-contract'
import type { NodeCertificate } from '@/utils/slmApi/nodes'
import { reportError, type FleetCtx } from './context'
import { refreshNode, updateNodeStatus } from './nodes'

// ── Fleet update summary (#682) ─────────────────────────────────────────────

/** Fetch the fleet-wide update summary. Supplementary info: a failure leaves it null. */
export async function fetchFleetUpdateSummary(ctx: FleetCtx): Promise<void> {
  try {
    ctx.state.fleetUpdateSummary.value = await ctx.api.getFleetUpdateSummary()
  } catch {
    ctx.state.fleetUpdateSummary.value = null
  }
}

/** The update summary of one node, by ID (#682). */
export function getNodeUpdateSummary(ctx: FleetCtx, nodeId: string): NodeUpdateSummary | undefined {
  return ctx.state.fleetUpdateSummary.value?.nodes.find((n) => n.node_id === nodeId)
}

/**
 * Reconcile one node's cached update summary with a fresh live-check result (#11964), so the
 * node-card badge and the live "Check for updates" scan never disagree.
 */
export function reconcileNodeUpdateSummary(
  ctx: FleetCtx,
  nodeId: string,
  systemUpdates: number,
  codeUpdateAvailable: boolean,
  codeStatus: string,
): void {
  const summary = ctx.state.fleetUpdateSummary.value
  const entry = summary?.nodes.find((n) => n.node_id === nodeId)
  if (!summary || !entry) return

  entry.system_updates = systemUpdates
  entry.code_update_available = codeUpdateAvailable
  entry.code_status = codeStatus
  entry.total_updates = systemUpdates + (codeUpdateAvailable ? 1 : 0)

  summary.total_system_updates = summary.nodes.reduce((sum, n) => sum + n.system_updates, 0)
  summary.total_code_updates = summary.nodes.filter((n) => n.code_update_available).length
  summary.nodes_needing_updates = summary.nodes.filter((n) => n.total_updates > 0).length
}

// ── Roles ───────────────────────────────────────────────────────────────────

/** Fetch the available roles from the API. */
export async function fetchRoles(ctx: FleetCtx): Promise<RoleInfo[]> {
  try {
    const roles = await ctx.api.getRoles()
    ctx.state.availableRoles.value = roles
    return roles
  } catch (err) {
    reportError(ctx, err, 'Failed to fetch roles')
    throw err
  }
}

// ── Enrollment and connection testing ───────────────────────────────────────

/** Start enrollment for a node; the status goes to 'enrolling' optimistically and is re-read after. */
export async function enrollNode(ctx: FleetCtx, nodeId: string): Promise<void> {
  updateNodeStatus(ctx, nodeId, 'enrolling')
  try {
    await ctx.api.enrollNode(nodeId)
    await refreshNode(ctx, nodeId)
  } catch (err) {
    // Revert on failure: fetch fresh state, and mark unhealthy if that fails too.
    await refreshNode(ctx, nodeId).catch(() => {
      updateNodeStatus(ctx, nodeId, 'unhealthy')
    })
    reportError(ctx, err, `Failed to enroll node ${nodeId}`)
    throw err
  }
}

/** Test the SSH connection to a node. */
export async function testConnection(ctx: FleetCtx, nodeId: string): Promise<ConnectionTestResult> {
  const node = ctx.state.nodes.value.get(nodeId)
  if (!node) {
    throw new Error(`Node ${nodeId} not found`)
  }
  try {
    return await ctx.api.testConnection({
      ip_address: node.ip_address,
      ssh_user: node.ssh_user || 'root',
      ssh_port: node.ssh_port || 22,
      auth_method: node.auth_method || 'password',
    })
  } catch (err) {
    reportError(ctx, err, `Failed to test connection to node ${nodeId}`)
    throw err
  }
}

// ── Certificates ────────────────────────────────────────────────────────────

/** Get the certificate status of a node. */
export async function checkNodeCertificate(ctx: FleetCtx, nodeId: string): Promise<NodeCertificate> {
  try {
    const certInfo = await ctx.api.getCertificateStatus(nodeId)
    ctx.state.certificateStatus.value.set(nodeId, certInfo)
    return certInfo
  } catch (err) {
    reportError(ctx, err, `Failed to get certificate status for node ${nodeId}`)
    throw err
  }
}

/** Renew a node's certificate, then re-read its status. */
export async function renewNodeCertificate(ctx: FleetCtx, nodeId: string): Promise<void> {
  try {
    await ctx.api.renewCertificate(nodeId)
    await checkNodeCertificate(ctx, nodeId)
  } catch (err) {
    reportError(ctx, err, `Failed to renew certificate for node ${nodeId}`)
    throw err
  }
}

/** Deploy a certificate to a node (initial issuance), then re-read its status. */
export async function deployNodeCertificate(ctx: FleetCtx, nodeId: string): Promise<void> {
  try {
    await ctx.api.deployCertificate(nodeId)
    await checkNodeCertificate(ctx, nodeId)
  } catch (err) {
    reportError(ctx, err, `Failed to deploy certificate to node ${nodeId}`)
    throw err
  }
}

// ── Events ──────────────────────────────────────────────────────────────────

/** Get the lifecycle events of a node. */
export async function getNodeEvents(
  ctx: FleetCtx,
  nodeId: string,
  filters?: NodeEventFilters,
): Promise<NodeEvent[]> {
  try {
    const events = await ctx.api.getNodeEvents(nodeId, filters)
    ctx.state.nodeEvents.value.set(nodeId, events)
    return events
  } catch (err) {
    reportError(ctx, err, `Failed to get events for node ${nodeId}`)
    throw err
  }
}

// ── Updates ─────────────────────────────────────────────────────────────────

/**
 * Check a node for available updates, and reconcile the cached fleet summary with the scan
 * (#11964). Returns the full response so callers get code_update_available/code_status directly.
 */
export async function checkNodeUpdates(ctx: FleetCtx, nodeId: string): Promise<NodeUpdateCheckResponse> {
  try {
    const result = await ctx.api.checkUpdates(nodeId)
    ctx.state.nodeUpdates.value.set(nodeId, result.updates)
    reconcileNodeUpdateSummary(ctx, nodeId, result.total, result.code_update_available, result.code_status)
    return result
  } catch (err) {
    reportError(ctx, err, `Failed to check updates for node ${nodeId}`)
    throw err
  }
}

/** Apply updates to a node, then re-read its updates and its status. */
export async function applyNodeUpdates(
  ctx: FleetCtx,
  nodeId: string,
  updateIds: string[],
): Promise<{ applied: string[]; failed: string[] }> {
  try {
    const result = await ctx.api.applyUpdates(nodeId, updateIds)
    await checkNodeUpdates(ctx, nodeId)
    await refreshNode(ctx, nodeId)
    return { applied: result.applied_updates, failed: result.failed_updates }
  } catch (err) {
    reportError(ctx, err, `Failed to apply updates to node ${nodeId}`)
    throw err
  }
}
