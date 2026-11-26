// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Pure helpers of the fleet store, split out of stores/fleet.ts (#21584) so that file, at its size
 * ceiling, can carry the incomplete-node-list state without growing.
 */

import type { FleetUpdateSummary, SLMNode } from '@/types/slm'
import i18n from '@/i18n'
import { PartialListError } from '@/utils/fetchAllPages'

/** The error for an action on a node the store does not hold; the text is translated (#21963). */
export function nodeNotFoundError(nodeId: string): Error {
  return new Error(i18n.global.t('fleet.errors.nodeNotFound', { nodeId }))
}

/**
 * Reconcile a single node's cached update summary with a fresh live-check
 * result (#11964).
 *
 * The live "Check for updates" scan (NodeLifecyclePanel) re-reads
 * node.code_status directly from the DB at click-time. The fleet-wide
 * summary that drives the node-card badge is otherwise only fetched once
 * on page load, so it can go stale. Patching the cached entry here after
 * every live check keeps the badge and the live scan from disagreeing.
 */
export function reconcileUpdateSummary(
  summary: FleetUpdateSummary | null,
  nodeId: string,
  systemUpdates: number,
  codeUpdateAvailable: boolean,
  codeStatus: string
): void {
  const entry = summary?.nodes.find(n => n.node_id === nodeId)
  if (!summary || !entry) return

  entry.system_updates = systemUpdates
  entry.code_update_available = codeUpdateAvailable
  entry.code_status = codeStatus
  entry.total_updates = systemUpdates + (codeUpdateAvailable ? 1 : 0)

  summary.total_system_updates = summary.nodes.reduce((sum, n) => sum + n.system_updates, 0)
  summary.total_code_updates = summary.nodes.filter(n => n.code_update_available).length
  summary.nodes_needing_updates = summary.nodes.filter(n => n.total_updates > 0).length
}

/** The node list the store was left holding when it is not the whole fleet (#21584). */
export interface NodeListIncomplete {
  /** Nodes actually read. */
  read: number
  /** Nodes the server reports, or null when it reported none. */
  total: number | null
  /** Why the rest could not be read. */
  reason: string
}

export const toNodeMap = (list: SLMNode[]): Map<string, SLMNode> => new Map(list.map((n) => [n.node_id, n]))

/** `{read, total}` for a partial read, null for anything else. */
export function incompleteOf(err: unknown): NodeListIncomplete | null {
  return err instanceof PartialListError ? { read: err.items.length, total: err.total, reason: err.reason } : null
}
