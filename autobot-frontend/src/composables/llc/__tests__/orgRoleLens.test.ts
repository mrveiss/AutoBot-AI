// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13943: the "View As: role" lens is a pure presentation filter — these
// tests pin the two contracts that matter: it narrows `org-person` nodes by
// the already-rendered `title` string and leaves everything else (in
// particular `org-group` containers) untouched, and it never needs
// `MembershipRole` to do it.

import { describe, it, expect } from 'vitest'
import { availableLensRoles, applyRoleLens, roleLensCounts } from '../orgRoleLens'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'
import type { CanvasNode } from '@/components/workflow/canvasNode'

function orgNode(overrides: Partial<OrgNode> & { id: string; title: string }): OrgNode {
  return {
    name: overrides.name ?? overrides.id,
    status: 'idle',
    adapter_type: '',
    is_human: false,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
    ...overrides,
  }
}

function personCanvasNode(id: string, title: string): CanvasNode {
  return {
    id,
    type: 'org-person',
    position: { x: 0, y: 0 },
    data: { label: id, title, status: 'idle', adapter_type: '', is_human: false },
    connections: [],
  }
}

function groupCanvasNode(id: string): CanvasNode {
  return {
    id,
    type: 'org-group',
    position: { x: 0, y: 0 },
    data: { label: id, width: 100, height: 100 },
    connections: [],
  }
}

describe('availableLensRoles', () => {
  it('collects distinct, alphabetised, non-blank titles across the whole forest', () => {
    const roots: OrgNode[] = [
      orgNode({
        id: 'ceo',
        title: 'manager',
        children: [orgNode({ id: 'dev', title: 'worker' }), orgNode({ id: 'dev2', title: 'worker' })],
      }),
      orgNode({ id: 'lead', title: 'lead' }),
      orgNode({ id: 'blank', title: '  ' }),
    ]

    expect(availableLensRoles(roots)).toEqual(['lead', 'manager', 'worker'])
  })

  it('returns an empty list for an empty forest', () => {
    expect(availableLensRoles([])).toEqual([])
  })
})

describe('applyRoleLens', () => {
  const nodes: CanvasNode[] = [
    groupCanvasNode('org-group:ceo'),
    personCanvasNode('ceo', 'manager'),
    personCanvasNode('dev', 'worker'),
    personCanvasNode('dev2', 'worker'),
  ]

  it('passes every node through when no role is selected', () => {
    expect(applyRoleLens(nodes, null)).toEqual(nodes)
  })

  it('keeps only org-person nodes whose title matches the selected role', () => {
    const result = applyRoleLens(nodes, 'worker')

    expect(result.map((n) => n.id)).toEqual(['org-group:ceo', 'dev', 'dev2'])
  })

  it('keeps every org-group container regardless of the selection — the box signals the filter, not a blank canvas', () => {
    const result = applyRoleLens(nodes, 'a-role-nobody-has')

    expect(result).toEqual([groupCanvasNode('org-group:ceo')])
  })
})

describe('roleLensCounts', () => {
  const nodes: CanvasNode[] = [
    groupCanvasNode('org-group:ceo'),
    personCanvasNode('ceo', 'manager'),
    personCanvasNode('dev', 'worker'),
    personCanvasNode('dev2', 'worker'),
  ]

  it('reports every person as shown when no role is selected', () => {
    expect(roleLensCounts(nodes, null)).toEqual({ shown: 3, total: 3 })
  })

  it('counts only the people the selected role matches, against the true total', () => {
    expect(roleLensCounts(nodes, 'worker')).toEqual({ shown: 2, total: 3 })
  })

  it('reports zero shown for a role nothing on the canvas carries', () => {
    expect(roleLensCounts(nodes, 'nonexistent')).toEqual({ shown: 0, total: 3 })
  })
})
