// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * "View As: role" lens for the Company OS canvas (GH#13943, umbrella #13935).
 *
 * A presentation filter only: it narrows which of the *already-fetched*
 * canvas nodes are drawn. Nothing here fetches, authorises or withholds a
 * response — the org-chart payload is unchanged, only what is rendered from
 * it (the umbrella's hard condition on #13943).
 *
 * Deliberately does NOT import `MembershipRole`
 * (`autobot-backend/llc/models/enums.py`) — the RBAC gate that authorises
 * claim/unclaim of a work item — or branch on it. The lens reads
 * `OrgNode.title`, the same display string `OrgTreeNode.vue` and the canvas
 * node card already render under a person's name (for a member, the
 * lower-cased membership role label the backend already serialises there;
 * for an agent, its org role or configured title). Filtering on a rendered
 * string can never be mistaken for, or accidentally wired into, an access
 * decision — two mechanisms that both look like authorisation is the defect
 * shape #13250 tracks, and this file is deliberately just a string filter
 * over what is already on screen.
 */

import type { CanvasNode } from '@/components/workflow/canvasNode'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'

/**
 * Distinct, non-blank `title` values in a forest, alphabetised.
 *
 * Not a fixed vocabulary — like the canvas's `tool` colour dimension
 * (`canvasNodeRules.ts`), a role here is whatever value the org chart already
 * carries, so the lens's option list can never fork from the backend's set of
 * roles.
 */
export function availableLensRoles(roots: OrgNode[]): string[] {
  const seen = new Set<string>()
  const stack = [...roots]
  while (stack.length > 0) {
    const node = stack.pop()
    if (!node) continue
    const title = node.title?.trim()
    if (title) seen.add(title)
    for (const child of node.children ?? []) stack.push(child)
  }
  return [...seen].sort((a, b) => a.localeCompare(b))
}

/** `data.title` off a canvas node's payload, or `null` when absent/not a string. */
function nodeTitle(node: CanvasNode): string | null {
  const data = node.data as Record<string, unknown>
  return typeof data.title === 'string' ? data.title : null
}

/**
 * Filter canvas nodes to the selected role.
 *
 * Only `org-person` nodes carry a role — an `org-group` container (and any
 * workflow-authoring node type; this composable is never wired into
 * `WorkflowBuilderView.vue`) passes through untouched, so a unit's container
 * stays visible even once every person inside it is filtered out. The empty
 * box, not a blank canvas, is what tells the reader the lens removed
 * something rather than the company having no data (#14064's failure shape).
 */
export function applyRoleLens(nodes: CanvasNode[], role: string | null): CanvasNode[] {
  if (!role) return nodes
  return nodes.filter((node) => node.type !== 'org-person' || nodeTitle(node) === role)
}

/** How many `org-person` nodes a role lens leaves visible, out of how many total. */
export function roleLensCounts(
  nodes: CanvasNode[],
  role: string | null,
): { shown: number; total: number } {
  const people = nodes.filter((node) => node.type === 'org-person')
  const total = people.length
  if (!role) return { shown: total, total }
  return { shown: people.filter((node) => nodeTitle(node) === role).length, total }
}
