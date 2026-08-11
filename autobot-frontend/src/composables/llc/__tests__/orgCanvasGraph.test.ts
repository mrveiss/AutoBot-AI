// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13939: the org-chart tree is mapped onto the existing WorkflowCanvas node
// shape. These tests pin the layout invariants the canvas relies on — depth
// runs left-to-right (the direction the canvas draws ports and edges in),
// people never share a slot, containers enclose their subtree, and every
// parent→child link survives as a canvas connection.

import { describe, it, expect } from 'vitest'
import {
  buildOrgCanvasGraph,
  flattenOrgNodes,
  orgLayoutKey,
  ORG_GROUP_PREFIX,
} from '../orgCanvasGraph'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'

function node(id: string, children: OrgNode[] = []): OrgNode {
  return {
    id,
    name: `Agent ${id}`,
    title: 'Engineer',
    status: 'idle',
    adapter_type: 'claude',
    is_human: false,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 100,
    assigned_item_count: 0,
    children,
    parent_id: null,
  }
}

const FOREST: OrgNode[] = [
  node('ceo', [node('cto', [node('dev1'), node('dev2')]), node('cfo')]),
  node('advisor'),
]

const unitLabel = (name: string) => `${name} unit`

describe('buildOrgCanvasGraph (#13939)', () => {
  it('emits one container per root plus one node per person', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const groups = graph.filter((n) => n.type === 'org-group')
    const people = graph.filter((n) => n.type === 'org-person')

    expect(groups.map((g) => g.id)).toEqual([`${ORG_GROUP_PREFIX}ceo`, `${ORG_GROUP_PREFIX}advisor`])
    expect(people.map((p) => p.id).sort()).toEqual(['advisor', 'ceo', 'cfo', 'cto', 'dev1', 'dev2'])
  })

  it('containers are emitted before people so they paint behind them', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const lastGroup = graph.map((n) => n.type).lastIndexOf('org-group')
    const firstPerson = graph.map((n) => n.type).indexOf('org-person')

    expect(lastGroup).toBeLessThan(firstPerson)
  })

  it('places every child in a column right of its parent', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const byId = new Map(graph.map((n) => [n.id, n]))

    for (const [parentId, childId] of [
      ['ceo', 'cto'],
      ['ceo', 'cfo'],
      ['cto', 'dev1'],
      ['cto', 'dev2'],
    ]) {
      expect(byId.get(childId)!.position.x).toBeGreaterThan(byId.get(parentId)!.position.x)
    }
  })

  it('never puts two people on the same point', () => {
    const people = buildOrgCanvasGraph(FOREST, unitLabel).filter((n) => n.type === 'org-person')
    const points = people.map((p) => `${p.position.x}:${p.position.y}`)

    expect(new Set(points).size).toBe(points.length)
  })

  it('keeps a parent vertically between its outermost children', () => {
    const byId = new Map(buildOrgCanvasGraph(FOREST, unitLabel).map((n) => [n.id, n]))
    const cto = byId.get('cto')!.position.y

    expect(cto).toBeGreaterThan(byId.get('dev1')!.position.y)
    expect(cto).toBeLessThan(byId.get('dev2')!.position.y)
  })

  it('sizes each container around its own subtree', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const group = graph.find((n) => n.id === `${ORG_GROUP_PREFIX}ceo`)!
    const subtree = graph.filter((n) => ['ceo', 'cto', 'cfo', 'dev1', 'dev2'].includes(n.id))
    const width = group.data.width as number
    const height = group.data.height as number

    for (const person of subtree) {
      expect(person.position.x).toBeGreaterThanOrEqual(group.position.x)
      expect(person.position.x).toBeLessThan(group.position.x + width)
      expect(person.position.y).toBeGreaterThan(group.position.y)
      expect(person.position.y).toBeLessThan(group.position.y + height)
    }
  })

  it('stacks root containers without overlapping', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const first = graph.find((n) => n.id === `${ORG_GROUP_PREFIX}ceo`)!
    const second = graph.find((n) => n.id === `${ORG_GROUP_PREFIX}advisor`)!

    expect(second.position.y).toBeGreaterThanOrEqual(
      first.position.y + (first.data.height as number),
    )
  })

  it('carries the person payload and the parent→child connections', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const ceo = graph.find((n) => n.id === 'ceo')!

    expect(ceo.data).toMatchObject({
      label: 'Agent ceo',
      title: 'Engineer',
      status: 'idle',
      adapter_type: 'claude',
      is_human: false,
    })
    expect(ceo.connections).toEqual(['cto', 'cfo'])
  })

  it('localises the container caption through the supplied labeller', () => {
    const graph = buildOrgCanvasGraph(FOREST, (name) => `EINHEIT ${name}`)
    const group = graph.find((n) => n.id === `${ORG_GROUP_PREFIX}ceo`)!

    expect(group.data.label).toBe('EINHEIT Agent ceo')
  })

  it('returns an empty graph for an empty forest', () => {
    expect(buildOrgCanvasGraph([], unitLabel)).toEqual([])
  })

  it('flattens the forest into an id lookup', () => {
    const byId = flattenOrgNodes(FOREST)

    expect([...byId.keys()].sort()).toEqual(['advisor', 'ceo', 'cfo', 'cto', 'dev1', 'dev2'])
    expect(byId.get('dev2')!.name).toBe('Agent dev2')
  })
})

// GH#13996: the layout key is what the Org Chart watches. It must change when
// the drawn forest changes and must NOT change on a pause/resume — a relayout
// throws away every position the user dragged.
describe('orgLayoutKey (#13996)', () => {
  it('is stable when only a status changes', () => {
    const before = orgLayoutKey(FOREST)
    const paused: OrgNode[] = structuredClone(FOREST)
    paused[0].children[0].status = 'paused'

    expect(orgLayoutKey(paused)).toBe(before)
  })

  it.each<[string, (forest: OrgNode[]) => void]>([
    ['a renamed agent', (f) => void (f[0].name = 'Renamed')],
    ['a changed title', (f) => void (f[0].title = 'CTO')],
    ['a changed adapter', (f) => void (f[0].adapter_type = 'ollama')],
    ['a human/agent switch', (f) => void (f[0].is_human = true)],
    ['a removed child', (f) => void f[0].children.pop()],
    ['a new root', (f) => void f.push(node('newbie'))],
    ['a moved child', (f) => void (f[1].children = [f[0].children.pop()!])],
  ])('changes on %s', (_label, mutate) => {
    const before = orgLayoutKey(FOREST)
    const after: OrgNode[] = structuredClone(FOREST)
    mutate(after)

    expect(orgLayoutKey(after)).not.toBe(before)
  })

  it('is empty for an empty forest', () => {
    expect(orgLayoutKey([])).toBe('')
  })
})
