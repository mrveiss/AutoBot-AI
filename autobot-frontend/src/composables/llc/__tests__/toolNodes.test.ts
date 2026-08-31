// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14597: tool nodes on the org canvas — the graph half of "tools are stored
// and listed but have no canvas presence".
//
// Two things a hand-rolled fixture could not prove: that a tool carried by
// several roles folds into one node (never one per role), and that a tool
// node's edges point at the process nodes of the roles that carry it, built
// with the real `buildProcessCanvasNodes` producer rather than a hand-written
// id string that could drift from what that function actually emits.

import { describe, it, expect } from 'vitest'
import {
  buildProcessCanvasNodes,
  buildToolCanvasNodes,
  canvasBottom,
  toolNameFromNode,
  TOOL_NODE_PREFIX,
} from '../orgCanvasGraph'

const TOOLS = [
  { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' },
  { role_id: 'r2', role_name: 'SRE', tool_name: 'shell_exec' },
]

describe('tool canvas nodes (#14597)', () => {
  it('builds one node per distinct tool, typed so the canvas can draw it', () => {
    const nodes = buildToolCanvasNodes(TOOLS, [], 0)

    expect(nodes).toHaveLength(2)
    expect(nodes.every((n) => n.type === 'org-tool')).toBe(true)
  })

  it('folds a tool carried by several roles into a single node, not one per role', () => {
    const shared = [
      { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' },
      { role_id: 'r2', role_name: 'SRE', tool_name: 'web_search' },
      { role_id: 'r3', role_name: 'Support', tool_name: 'web_search' },
    ]

    const nodes = buildToolCanvasNodes(shared, [], 0)

    expect(nodes).toHaveLength(1)
    expect((nodes[0].data as { roles: { role_id: string }[] }).roles).toHaveLength(3)
  })

  it("carries every role's id and name on the shared node", () => {
    const shared = [
      { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' },
      { role_id: 'r2', role_name: 'SRE', tool_name: 'web_search' },
    ]

    const [node] = buildToolCanvasNodes(shared, [], 0)

    expect(node.data.roles).toEqual([
      { role_id: 'r1', role_name: 'Head of Sales' },
      { role_id: 'r2', role_name: 'SRE' },
    ])
  })

  it('de-duplicates the same (role, tool) attachment seen twice', () => {
    const duplicated = [
      { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' },
      { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' },
    ]

    const [node] = buildToolCanvasNodes(duplicated, [], 0)

    expect(node.data.roles).toHaveLength(1)
  })

  it('round-trips the tool name through the node id', () => {
    for (const tool of TOOLS) {
      const [node] = buildToolCanvasNodes([tool], [], 0)
      expect(toolNameFromNode(node.id)).toBe(tool.tool_name)
    }
  })

  it('does not decode a tool name from a non-tool node', () => {
    expect(toolNameFromNode('agent-7')).toBeNull()
    expect(toolNameFromNode('org-group:sales')).toBeNull()
    expect(toolNameFromNode(`${TOOL_NODE_PREFIX}`)).toBeNull()
  })

  it('connects a tool to the process node of a role that carries it, built with the real producer', () => {
    // Built with buildProcessCanvasNodes — not a hand-written id — so this
    // fails if that function's id shape ever changes without this one
    // following (GH#14027 family: a hand-rolled fixture can drift from what
    // the real producer emits).
    const processes = buildProcessCanvasNodes(
      [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }],
      0,
    )

    const [node] = buildToolCanvasNodes(
      [{ role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' }],
      [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }],
      0,
    )

    expect(node.connections).toEqual([processes[0].id])
  })

  it("carries no connection to a process belonging to a role that does not use the tool", () => {
    const [node] = buildToolCanvasNodes(
      [{ role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' }],
      [{ role_id: 'r2', role_name: 'SRE', workflow_id: 'wf-oncall' }],
      0,
    )

    expect(node.connections).toEqual([])
  })

  it('places tools below whatever section came before them', () => {
    const tools = buildToolCanvasNodes(TOOLS, [], 0)
    const below = buildToolCanvasNodes(TOOLS, [], canvasBottom(tools))

    expect(Math.min(...below.map((n) => n.position.y))).toBeGreaterThan(
      Math.max(...tools.map((n) => n.position.y)),
    )
  })

  it('returns nothing for a company with no tools', () => {
    expect(buildToolCanvasNodes([], [], 0)).toEqual([])
  })
})
