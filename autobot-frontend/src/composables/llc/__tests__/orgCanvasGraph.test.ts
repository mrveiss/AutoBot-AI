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
  buildTeamCanvasNodes,
  flattenOrgNodes,
  orgLayoutKey,
  isOrgUnit,
  orgUnitRoots,
  teamMemberOrgNodeId,
  ORG_GROUP_PREFIX,
  TEAM_GROUP_PREFIX,
} from '../orgCanvasGraph'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'
import { buildOrgPeople } from '../orgPeople'
import type { CompanyTeam } from '../orgPeople'

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

/** Two real hierarchies — the case where two containers must stack. */
const TWO_UNIT_FOREST: OrgNode[] = [FOREST[0], node('ops', [node('sre')])]

/** A person: a root with no reports, exactly what a membership produces. */
function person(id: string, name: string): OrgNode {
  return { ...node(id), name, title: 'member', is_human: true, budget_total: 0 }
}

/** Twelve people and nothing else — the company shape from GH#13994. */
const PEOPLE_ONLY: OrgNode[] = Array.from({ length: 12 }, (_, i) =>
  person(`user:${i}`, `Person ${i}`),
)

const unitLabel = (name: string) => `${name} unit`

describe('buildOrgCanvasGraph (#13939)', () => {
  it('emits one container per unit plus one node per person', () => {
    const graph = buildOrgCanvasGraph(FOREST, unitLabel)
    const groups = graph.filter((n) => n.type === 'org-group')
    const people = graph.filter((n) => n.type === 'org-person')

    // #13994: `advisor` is a root with no reports — a person, not a unit.
    expect(groups.map((g) => g.id)).toEqual([`${ORG_GROUP_PREFIX}ceo`])
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

  it('stacks unit containers without overlapping', () => {
    const graph = buildOrgCanvasGraph(TWO_UNIT_FOREST, unitLabel)
    const first = graph.find((n) => n.id === `${ORG_GROUP_PREFIX}ceo`)!
    const second = graph.find((n) => n.id === `${ORG_GROUP_PREFIX}ops`)!

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

// GH#13994: the backend returns every person of the company as a root, because a
// membership carries no `reports_to` edge. Wrapping every root made each of them
// a single-person "unit". These cases are people-shaped on purpose — the older
// fixtures are all agent hierarchies, which is why the explosion was invisible.
describe('grouping is by descendants, not root-ness (#13994)', () => {
  it('draws no container at all for a company that is only people', () => {
    const graph = buildOrgCanvasGraph(PEOPLE_ONLY, unitLabel)

    expect(graph.filter((n) => n.type === 'org-group')).toEqual([])
    expect(graph.filter((n) => n.type === 'org-person')).toHaveLength(12)
    expect(graph.map((n) => n.data.label)).not.toContain(unitLabel('Person 0'))
  })

  it('keeps every bare person a first-class, selectable node', () => {
    const graph = buildOrgCanvasGraph(PEOPLE_ONLY, unitLabel)
    const first = graph[0]

    expect(first.id).toBe('user:0')
    expect(first.data).toMatchObject({ label: 'Person 0', title: 'member', is_human: true })
    expect(first.connections).toEqual([])
  })

  it('packs bare people across before stacking them down', () => {
    const graph = buildOrgCanvasGraph(PEOPLE_ONLY, unitLabel)
    const positions = graph.map((n) => n.position)

    // Row 1 walks right; the fifth wraps back to the first column, one row down.
    expect(positions[1].x).toBeGreaterThan(positions[0].x)
    expect(positions[1].y).toBe(positions[0].y)
    expect(positions[4].x).toBe(positions[0].x)
    expect(positions[4].y).toBeGreaterThan(positions[0].y)
    expect(new Set(positions.map((p) => `${p.x}:${p.y}`)).size).toBe(12)
  })

  it('mixes units and people: containers wrap only the hierarchies', () => {
    const graph = buildOrgCanvasGraph([...FOREST, ...PEOPLE_ONLY.slice(0, 3)], unitLabel)
    const groups = graph.filter((n) => n.type === 'org-group')
    const container = groups[0]

    expect(groups.map((g) => g.id)).toEqual([`${ORG_GROUP_PREFIX}ceo`])
    // The people sit below the last container, not inside it.
    for (const id of ['advisor', 'user:0', 'user:1', 'user:2']) {
      const bare = graph.find((n) => n.id === id)!
      expect(bare.position.y).toBeGreaterThanOrEqual(
        container.position.y + (container.data.height as number),
      )
    }
  })

  it('names a unit as a root with reports — the predicate the tab strip shares', () => {
    expect(isOrgUnit(FOREST[0])).toBe(true)
    expect(isOrgUnit(FOREST[1])).toBe(false)
    expect(isOrgUnit({ ...FOREST[1], children: undefined as unknown as OrgNode[] })).toBe(false)
    expect(orgUnitRoots([...FOREST, ...PEOPLE_ONLY]).map((r) => r.id)).toEqual(['ceo'])
    expect(orgUnitRoots(PEOPLE_ONLY)).toEqual([])
  })
})

// GH#14596: teams as a first-class canvas grouping — a different question
// than `isOrgUnit`'s reporting units ("who reports to whom" vs "who works
// together"), read from the same `groupPeopleByTeam` the People list uses.
describe('buildTeamCanvasNodes (#14596)', () => {
  const alice = person('user:alice', 'Alice')
  const bob = person('user:bob', 'Bob')
  const charlie = node('agent:charlie') // an agent — never a team member (#13938)
  const TEAM_FOREST: OrgNode[] = [alice, bob, charlie]
  const teamPeople = buildOrgPeople(TEAM_FOREST, [])
  const byId = flattenOrgNodes(TEAM_FOREST)
  const teamLabel = (name: string) => `TEAM ${name}`
  const UNGROUPED_LABEL = 'UNGROUPED'

  const TWO_TEAMS: CompanyTeam[] = [
    { id: 't1', name: 'Platform', member_user_ids: ['alice', 'bob'] },
    { id: 't2', name: 'Growth', member_user_ids: ['alice'] },
  ]

  it('draws a team container in its own id namespace, distinct from a reporting-unit container', () => {
    const graph = buildTeamCanvasNodes(byId, teamPeople, TWO_TEAMS, 0, teamLabel, UNGROUPED_LABEL)
    const groups = graph.filter((n) => n.type === 'org-group')

    expect(groups.map((g) => g.id).sort()).toEqual(
      [`${TEAM_GROUP_PREFIX}t1`, `${TEAM_GROUP_PREFIX}t2`, `${TEAM_GROUP_PREFIX}__no_team__`].sort(),
    )
    // The discriminator a mutation would break: a team container never
    // carries the reporting-unit prefix, and vice versa.
    for (const group of groups) {
      expect(group.id.startsWith(TEAM_GROUP_PREFIX)).toBe(true)
      expect(group.id.startsWith(ORG_GROUP_PREFIX)).toBe(false)
    }
    expect(groups.map((g) => g.data.label).sort()).toEqual(
      ['TEAM Growth', 'TEAM Platform', 'UNGROUPED'].sort(),
    )
  })

  it('draws one node per (team, person) pair — a person on two teams appears in each, same identity', () => {
    const graph = buildTeamCanvasNodes(byId, teamPeople, TWO_TEAMS, 0, teamLabel, UNGROUPED_LABEL)
    const aliceNodes = graph.filter((n) => n.type === 'org-person' && n.data.label === 'Alice')

    // Two distinct canvas nodes (t1 and t2 each get their own)…
    expect(aliceNodes).toHaveLength(2)
    expect(new Set(aliceNodes.map((n) => n.id)).size).toBe(2)
    // …but both resolve back to the exact same real org-chart identity — the
    // duplication is visual, not a second person invented from nothing.
    for (const aliceNode of aliceNodes) {
      expect(teamMemberOrgNodeId(aliceNode.id)).toBe('user:alice')
    }
  })

  it('puts a person on no team in the honest ungrouped bucket, never dropped', () => {
    const graph = buildTeamCanvasNodes(byId, teamPeople, TWO_TEAMS, 0, teamLabel, UNGROUPED_LABEL)
    const ungroupedContainer = graph.find((n) => n.id === `${TEAM_GROUP_PREFIX}__no_team__`)!
    const charlieNodes = graph.filter(
      (n) => n.type === 'org-person' && teamMemberOrgNodeId(n.id) === 'agent:charlie',
    )

    expect(ungroupedContainer.data.label).toBe(UNGROUPED_LABEL)
    // Alice and Bob are both claimed by a team, so charlie is the only
    // member of the ungrouped bucket — and mutating either predicate above
    // must not silently absorb charlie into a team he was never added to.
    expect(charlieNodes).toHaveLength(1)
  })

  it('draws nothing when the company has zero teams — the caller states that fact in words instead', () => {
    expect(buildTeamCanvasNodes(byId, teamPeople, [], 0, teamLabel, UNGROUPED_LABEL)).toEqual([])
  })

  it('still draws an empty team as an empty container, rather than dropping it', () => {
    const emptyTeam: CompanyTeam[] = [{ id: 't3', name: 'Marketing', member_user_ids: [] }]
    const graph = buildTeamCanvasNodes(byId, teamPeople, emptyTeam, 0, teamLabel, UNGROUPED_LABEL)
    const marketing = graph.find((n) => n.id === `${TEAM_GROUP_PREFIX}t3`)!
    // Nobody claims the team, so everyone (alice, bob, charlie) falls into
    // the ungrouped bucket instead — that bucket's people are not what this
    // assertion is about, so it is scoped to `t3`'s own roster alone.
    const marketingMembers = graph.filter((n) => n.id.startsWith(`${TEAM_GROUP_PREFIX}t3:member:`))

    expect(marketing).toBeDefined()
    expect(marketing.data.label).toBe('TEAM Marketing')
    expect(marketingMembers).toHaveLength(0)
  })

  it('resolves a team-member canvas id back to the real org-chart id, and rejects anything else', () => {
    expect(teamMemberOrgNodeId(`${TEAM_GROUP_PREFIX}t1:member:user:alice`)).toBe('user:alice')
    // Not a team-member id at all — a reporting-unit container, a bare
    // person, a process node: none of these should resolve to anything.
    expect(teamMemberOrgNodeId(`${ORG_GROUP_PREFIX}ceo`)).toBeNull()
    expect(teamMemberOrgNodeId('ceo')).toBeNull()
    expect(teamMemberOrgNodeId(`${TEAM_GROUP_PREFIX}t1`)).toBeNull()
  })
})
