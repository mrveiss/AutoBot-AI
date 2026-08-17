// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13963: process nodes on the org canvas — the contextual entrance to the
// absorbed automation module.
//
// The id round-trip is what these mostly guard. A process node encodes the role
// and the workflow into its canvas id, and the click handler decodes the
// workflow back out. If the two ever disagree the node still renders and still
// looks clickable — it just opens the wrong workflow, or nothing. That failure
// is silent, so it is asserted rather than assumed.

import { describe, it, expect } from 'vitest'
import {
  buildProcessCanvasNodes,
  canvasBottom,
  workflowIdFromProcessNode,
  PROCESS_NODE_PREFIX,
} from '../orgCanvasGraph'

const PROCESSES = [
  { role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' },
  { role_id: 'r2', role_name: 'SRE', workflow_id: 'wf-oncall' },
]

describe('process canvas nodes (#13963)', () => {
  it('builds one node per process, typed so the canvas can draw it', () => {
    const nodes = buildProcessCanvasNodes(PROCESSES, 0)

    expect(nodes).toHaveLength(2)
    expect(nodes.every((n) => n.type === 'org-process')).toBe(true)
  })

  it('carries the role name and workflow id the canvas renders', () => {
    const [node] = buildProcessCanvasNodes(PROCESSES, 0)

    expect(node.data).toMatchObject({
      role_id: 'r1',
      role_name: 'Head of Sales',
      workflow_id: 'wf-quarterly',
    })
  })

  it('round-trips the workflow id through the node id', () => {
    // The whole click path depends on this. A node whose id cannot be decoded
    // renders fine and opens nothing.
    for (const process of PROCESSES) {
      const [node] = buildProcessCanvasNodes([process], 0)
      expect(workflowIdFromProcessNode(node.id)).toBe(process.workflow_id)
    }
  })

  it('round-trips a workflow id that itself contains a colon', () => {
    // The id is `process:<role>:<workflow>`, so a naive split on ':' would
    // truncate a namespaced workflow id and open the wrong thing.
    const [node] = buildProcessCanvasNodes(
      [{ role_id: 'r1', role_name: 'SRE', workflow_id: 'team:oncall:v2' }],
      0,
    )

    expect(workflowIdFromProcessNode(node.id)).toBe('team:oncall:v2')
  })

  it('does not decode a workflow from a non-process node', () => {
    // People and group ids must fall through to the drawer, not the router.
    expect(workflowIdFromProcessNode('agent-7')).toBeNull()
    expect(workflowIdFromProcessNode('org-group:sales')).toBeNull()
    expect(workflowIdFromProcessNode(`${PROCESS_NODE_PREFIX}r1`)).toBeNull()
  })

  it('places processes below the people graph', () => {
    const people = buildProcessCanvasNodes(PROCESSES, 0)
    const below = buildProcessCanvasNodes(PROCESSES, canvasBottom(people))

    expect(Math.min(...below.map((n) => n.position.y))).toBeGreaterThan(
      Math.max(...people.map((n) => n.position.y)),
    )
  })

  it('packs across before stacking down', () => {
    const many = Array.from({ length: 4 }, (_, i) => ({
      role_id: `r${i}`,
      role_name: `Role ${i}`,
      workflow_id: `wf-${i}`,
    }))

    const nodes = buildProcessCanvasNodes(many, 0)
    const firstRowY = nodes[0].position.y

    // At least two share the first row, and x increases across it — otherwise a
    // dozen processes become a column the reader has to pan through.
    const firstRow = nodes.filter((n) => n.position.y === firstRowY)
    expect(firstRow.length).toBeGreaterThan(1)
    expect(firstRow[1].position.x).toBeGreaterThan(firstRow[0].position.x)
  })

  it('returns nothing for a company with no processes', () => {
    expect(buildProcessCanvasNodes([], 0)).toEqual([])
    expect(canvasBottom([])).toBe(0)
  })
})
