// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Org chart → canvas graph (GH#13939).
 *
 * Maps the `GET /api/llc/companies/{id}/org-chart` tree onto the node shape
 * `components/workflow/WorkflowCanvas.vue` already renders, so Company OS gets
 * a pan/zoom process canvas without a graph library and without a second
 * canvas implementation.
 *
 * Layout is left-to-right hierarchical (depth → column, leaves → rows) because
 * that is the direction the canvas draws its ports and bezier edges in. Each
 * root subtree also gets an `org-group` container node — the section/grouping
 * container — sized to its subtree bounding box and emitted first so it paints
 * behind the people.
 */

import type { CanvasNode } from '@/components/workflow/canvasNode'
import { CANVAS_NODE_WIDTH } from '@/components/workflow/canvasNode'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'

/** Horizontal distance between two depth levels. */
const COLUMN_GAP = 80
/** Vertical distance between two leaf rows. */
const ROW_HEIGHT = 130
/** Inner padding of a grouping container. */
const GROUP_PADDING = 24
/** Height reserved for the grouping container's own header. */
const GROUP_HEADER = 44
/** Vertical distance between two grouping containers. */
const GROUP_GAP = 60
/** Id prefix that keeps container ids from colliding with agent ids. */
export const ORG_GROUP_PREFIX = 'org-group:'

interface PlacedNode {
  node: OrgNode
  depth: number
  x: number
  y: number
}

/**
 * Depth-first placement. Leaves take the next free row; a parent centres on
 * its first and last child. Returns the row offset assigned to `node`.
 */
function placeSubtree(
  node: OrgNode,
  depth: number,
  cursor: { row: number },
  out: PlacedNode[],
): number {
  const x = depth * (CANVAS_NODE_WIDTH + COLUMN_GAP)
  const children = node.children ?? []
  if (children.length === 0) {
    const y = cursor.row * ROW_HEIGHT
    cursor.row += 1
    out.push({ node, depth, x, y })
    return y
  }
  const childRows = children.map((child) => placeSubtree(child, depth + 1, cursor, out))
  const y = (childRows[0] + childRows[childRows.length - 1]) / 2
  out.push({ node, depth, x, y })
  return y
}

/** One person node, offset into its grouping container. */
function toPersonNode(placed: PlacedNode, topOffset: number): CanvasNode {
  const { node } = placed
  return {
    id: node.id,
    type: 'org-person',
    position: { x: GROUP_PADDING + placed.x, y: topOffset + placed.y },
    data: {
      label: node.name,
      title: node.title,
      status: node.status,
      adapter_type: node.adapter_type,
      is_human: node.is_human,
    },
    connections: (node.children ?? []).map((child) => child.id),
  }
}

/** The grouping container for one root subtree. */
function toGroupNode(
  root: OrgNode,
  placed: PlacedNode[],
  topOffset: number,
  rows: number,
  unitLabel: (name: string) => string,
): CanvasNode {
  const depth = Math.max(...placed.map((p) => p.depth))
  return {
    id: `${ORG_GROUP_PREFIX}${root.id}`,
    type: 'org-group',
    position: { x: 0, y: topOffset },
    data: {
      label: unitLabel(root.name),
      width: 2 * GROUP_PADDING + (depth + 1) * CANVAS_NODE_WIDTH + depth * COLUMN_GAP,
      height: GROUP_HEADER + 2 * GROUP_PADDING + rows * ROW_HEIGHT,
    },
    connections: [],
  }
}

/**
 * Build the canvas graph for an org-chart forest.
 *
 * @param roots      root org nodes as returned by the org-chart endpoint
 * @param unitLabel  localiser for a grouping container's caption
 */
export function buildOrgCanvasGraph(
  roots: OrgNode[],
  unitLabel: (name: string) => string,
): CanvasNode[] {
  const groups: CanvasNode[] = []
  const people: CanvasNode[] = []
  let topOffset = 0
  for (const root of roots) {
    const placed: PlacedNode[] = []
    const cursor = { row: 0 }
    placeSubtree(root, 0, cursor, placed)
    const contentTop = topOffset + GROUP_HEADER + GROUP_PADDING
    for (const item of placed) people.push(toPersonNode(item, contentTop))
    groups.push(toGroupNode(root, placed, topOffset, cursor.row, unitLabel))
    topOffset += GROUP_HEADER + 2 * GROUP_PADDING + cursor.row * ROW_HEIGHT + GROUP_GAP
  }
  // Containers first so the people paint on top of them.
  return [...groups, ...people]
}

/**
 * Structural key of a forest: ids, nesting and the labels the canvas paints.
 *
 * Deliberately excludes `status`. Pause/resume writes `status` on the tree node
 * in place, and a layout driven by it rebuilt the whole graph on every toggle,
 * discarding every position the user had dragged (GH#13996).
 */
export function orgLayoutKey(roots: OrgNode[]): string {
  return roots
    .map(
      (node) =>
        `${node.id}:${node.name}:${node.title}:${node.adapter_type}:${node.is_human}` +
        `(${orgLayoutKey(node.children ?? [])})`,
    )
    .join(',')
}

/** Flatten an org forest into a lookup by agent id. */
export function flattenOrgNodes(roots: OrgNode[]): Map<string, OrgNode> {
  const byId = new Map<string, OrgNode>()
  const stack = [...roots]
  while (stack.length > 0) {
    const node = stack.pop()
    if (!node) continue
    byId.set(node.id, node)
    for (const child of node.children ?? []) stack.push(child)
  }
  return byId
}
