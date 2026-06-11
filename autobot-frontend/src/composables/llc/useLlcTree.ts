// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Shared LLC tree helpers (GH#9909).
 *
 * Consolidates the recursive expand-marker and tree-assembly logic that was
 * duplicated across GoalTree.vue and SubCompanyTree.vue.
 */

/** Minimal node shape required by markExpanded(). */
export interface ExpandableNode {
  expanded?: boolean
  children?: ExpandableNode[]
}

/**
 * Set the expanded flag on the given nodes; all descendants are collapsed.
 * Calling with `expanded = true` expands the roots only (matches the
 * previous per-view behavior in GoalTree.vue / SubCompanyTree.vue).
 */
export function markExpanded<T extends ExpandableNode>(nodes: T[], expanded: boolean): void {
  for (const node of nodes) {
    node.expanded = expanded
    if (node.children) markExpanded(node.children, false)
  }
}

/**
 * Assemble a forest from a flat list using id → parent-id edges.
 * Items with a falsy, unknown, or self-referencing parent become roots.
 */
export function buildTreeFromParent<TFlat, TNode extends { children: TNode[] }>(
  items: TFlat[],
  idKey: keyof TFlat,
  parentKey: keyof TFlat,
  toNode: (item: TFlat) => TNode,
): TNode[] {
  const byId = new Map<unknown, TNode>()
  for (const item of items) byId.set(item[idKey], toNode(item))
  const roots: TNode[] = []
  for (const item of items) {
    const node = byId.get(item[idKey])!
    const parentId = item[parentKey]
    const parent = parentId ? byId.get(parentId) : undefined
    if (parent && parent !== node) parent.children.push(node)
    else roots.push(node)
  }
  return roots
}

/**
 * Recursively map an already-nested raw tree (e.g. the company /tree
 * endpoint response) into a display-node tree.
 */
export function mapTree<TRaw extends { children?: TRaw[] }, TNode>(
  raw: TRaw,
  toNode: (item: TRaw, children: TNode[]) => TNode,
): TNode {
  return toNode(
    raw,
    (raw.children ?? []).map((child) => mapTree(child, toNode)),
  )
}
