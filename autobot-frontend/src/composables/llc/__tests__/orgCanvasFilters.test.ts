// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14608: the Company OS canvas's multi-filter — role, team and tool
// combining with AND. These tests pin the three contracts that matter:
//
//  * the axes intersect (removing either one changes the result — otherwise
//    a test could not tell a real AND from an accidental OR);
//  * every section keeps the same "org-group passes through untouched"
//    reasoning `orgRoleLens.ts` already established for role, applied
//    consistently to the new team and tool axes;
//  * a value that matches nothing in the current data collapses its own
//    section to an honest `[]`, never a node the reader would mistake for a
//    match.
//
// Fixtures are built with the real producers (`buildOrgCanvasGraph`,
// `buildTeamCanvasNodes`, `buildProcessCanvasNodes`, `buildToolCanvasNodes`),
// not hand-rolled `CanvasNode` objects — so these tests exercise the exact
// shapes `OrgChart.vue` renders, not an approximation of them.

import { describe, it, expect } from 'vitest'
import {
  applyHierarchyFilters,
  applyTeamSectionFilter,
  applyProcessToolFilter,
  applyToolSectionFilter,
  buildTeamIdsByOrgNodeId,
  buildToolRoleIndex,
  teamFilterCounts,
  toolFilterCounts,
  hasActiveCanvasFilters,
  hasCombinedCanvasFilters,
  type CanvasFilterState,
} from '../orgCanvasFilters'
import {
  buildOrgCanvasGraph,
  buildTeamCanvasNodes,
  buildProcessCanvasNodes,
  buildToolCanvasNodes,
  flattenOrgNodes,
  ORG_GROUP_PREFIX,
  TEAM_GROUP_PREFIX,
  type ProcessNodeSource,
  type ToolNodeSource,
} from '../orgCanvasGraph'
import { buildOrgPeople } from '../orgPeople'
import type { CompanyTeam } from '../orgPeople'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'

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

const unitLabel = (name: string) => `${name} unit`
const teamLabel = (name: string) => `${name} team`

// ceo unit: ceo (Manager) -> dev (Engineer). Three ungrouped users: Grace and
// Ivan are both Engineers, on different teams; Hana is a Designer.
const ROOTS: OrgNode[] = [
  orgNode({
    id: 'ceo',
    title: 'Manager',
    children: [orgNode({ id: 'dev', title: 'Engineer' })],
  }),
  orgNode({ id: 'user:U1', name: 'Grace', title: 'Engineer', is_human: true }),
  orgNode({ id: 'user:U2', name: 'Hana', title: 'Designer', is_human: true }),
  orgNode({ id: 'user:U3', name: 'Ivan', title: 'Engineer', is_human: true }),
]

const TEAMS: CompanyTeam[] = [
  { id: 't-platform', name: 'Platform', member_user_ids: ['U1'] },
  { id: 't-design', name: 'Design', member_user_ids: ['U2', 'U3'] },
]

const TOOLS: ToolNodeSource[] = [
  { role_id: 'r-eng', role_name: 'Engineer', tool_name: 'web_search' },
  { role_id: 'r-mgr', role_name: 'Manager', tool_name: 'jira' },
]

const PROCESSES: ProcessNodeSource[] = [
  { role_id: 'r-eng', role_name: 'Engineer', workflow_id: 'wf-eng' },
  { role_id: 'r-mgr', role_name: 'Manager', workflow_id: 'wf-mgr' },
]

const hierarchyNodes = buildOrgCanvasGraph(ROOTS, unitLabel)
const people = buildOrgPeople(ROOTS, [])
const orgNodesById = flattenOrgNodes(ROOTS)
const teamNodes = buildTeamCanvasNodes(orgNodesById, people, TEAMS, 0, teamLabel, 'No team')
const processNodes = buildProcessCanvasNodes(PROCESSES, 0)
const toolNodes = buildToolCanvasNodes(TOOLS, PROCESSES, 0)

const toolRoleIndex = buildToolRoleIndex(TOOLS)
const ctx = {
  teamIdsByOrgNodeId: buildTeamIdsByOrgNodeId(people, TEAMS),
  toolRoleNames: toolRoleIndex.names,
  toolRoleIds: toolRoleIndex.ids,
}

function ids(nodes: { id: string }[]): string[] {
  return nodes.map((n) => n.id)
}

describe('hasActiveCanvasFilters / hasCombinedCanvasFilters', () => {
  const none: CanvasFilterState = { role: null, team: null, tool: null }

  it('is false when every axis is null', () => {
    expect(hasActiveCanvasFilters(none)).toBe(false)
    expect(hasCombinedCanvasFilters(none)).toBe(false)
  })

  it('active fires for role alone; combined does not — role is not one of the new axes', () => {
    const filters = { ...none, role: 'Engineer' }
    expect(hasActiveCanvasFilters(filters)).toBe(true)
    expect(hasCombinedCanvasFilters(filters)).toBe(false)
  })

  it('combined fires for team or tool', () => {
    expect(hasCombinedCanvasFilters({ ...none, team: 't-design' })).toBe(true)
    expect(hasCombinedCanvasFilters({ ...none, tool: 'web_search' })).toBe(true)
  })
})

describe('applyHierarchyFilters — role, team and tool combine with AND', () => {
  it('role alone keeps every Engineer plus the unit container', () => {
    const result = applyHierarchyFilters(hierarchyNodes, { role: 'Engineer', team: null, tool: null }, ctx)
    expect(ids(result)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'dev', 'user:U1', 'user:U3'])
  })

  it('team alone keeps only that team\'s members plus the unit container', () => {
    const result = applyHierarchyFilters(hierarchyNodes, { role: null, team: 't-design', tool: null }, ctx)
    expect(ids(result)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'user:U2', 'user:U3'])
  })

  it('role + team combine to the intersection, not the union', () => {
    const result = applyHierarchyFilters(
      hierarchyNodes,
      { role: 'Engineer', team: 't-design', tool: null },
      ctx,
    )
    // Only Ivan is both an Engineer and on Design — dev (no team) and Grace
    // (Platform) are each removed by exactly one of the two axes.
    expect(ids(result)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'user:U3'])
  })

  it('removing the role axis widens the result — proves the axes are independent, not coincidentally equal', () => {
    const combined = applyHierarchyFilters(
      hierarchyNodes,
      { role: 'Engineer', team: 't-design', tool: null },
      ctx,
    )
    const teamOnly = applyHierarchyFilters(hierarchyNodes, { role: null, team: 't-design', tool: null }, ctx)
    expect(ids(teamOnly)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'user:U2', 'user:U3'])
    expect(ids(teamOnly).length).toBeGreaterThan(ids(combined).length)
  })

  it('removing the team axis widens the result the same way', () => {
    const combined = applyHierarchyFilters(
      hierarchyNodes,
      { role: 'Engineer', team: 't-design', tool: null },
      ctx,
    )
    const roleOnly = applyHierarchyFilters(hierarchyNodes, { role: 'Engineer', team: null, tool: null }, ctx)
    expect(ids(roleOnly)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'dev', 'user:U1', 'user:U3'])
    expect(ids(roleOnly).length).toBeGreaterThan(ids(combined).length)
  })

  it('team + tool combine (the two axes this module adds beside role)', () => {
    const combined = applyHierarchyFilters(
      hierarchyNodes,
      { role: null, team: 't-design', tool: 'web_search' },
      ctx,
    )
    // web_search is carried by "Engineer" — only Ivan is both Design and an
    // Engineer; Hana (Design, Designer) is removed by the tool axis alone.
    expect(ids(combined)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'user:U3'])

    const toolOnly = applyHierarchyFilters(hierarchyNodes, { role: null, team: null, tool: 'web_search' }, ctx)
    expect(ids(toolOnly)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'dev', 'user:U1', 'user:U3'])
    expect(ids(toolOnly).length).toBeGreaterThan(ids(combined).length)
  })

  it('a role nobody currently carries empties the org-person set but keeps the unit container', () => {
    const result = applyHierarchyFilters(hierarchyNodes, { role: 'nonexistent', team: null, tool: null }, ctx)
    expect(ids(result)).toEqual([`${ORG_GROUP_PREFIX}ceo`])
  })

  it('a team id present nowhere in the data empties every org-person, unit container survives', () => {
    const result = applyHierarchyFilters(hierarchyNodes, { role: null, team: 'nonexistent', tool: null }, ctx)
    expect(ids(result)).toEqual([`${ORG_GROUP_PREFIX}ceo`])
  })

  it('a tool name present nowhere in the data empties every org-person, unit container survives', () => {
    const result = applyHierarchyFilters(hierarchyNodes, { role: null, team: null, tool: 'nonexistent' }, ctx)
    expect(ids(result)).toEqual([`${ORG_GROUP_PREFIX}ceo`])
  })

  it('passes every node through untouched when no axis is active', () => {
    expect(applyHierarchyFilters(hierarchyNodes, { role: null, team: null, tool: null }, ctx)).toEqual(
      hierarchyNodes,
    )
  })
})

describe('applyTeamSectionFilter — the team-roster section', () => {
  it('is untouched when no team is selected', () => {
    expect(applyTeamSectionFilter(teamNodes, null)).toEqual(teamNodes)
  })

  it('keeps every team container but only the selected team\'s members — the box is the filtered cue', () => {
    const result = applyTeamSectionFilter(teamNodes, 't-design')

    const platformBox = result.find((n) => n.id === `${TEAM_GROUP_PREFIX}t-platform`)
    const designBox = result.find((n) => n.id === `${TEAM_GROUP_PREFIX}t-design`)
    expect(platformBox).toBeDefined()
    expect(designBox).toBeDefined()

    const platformMembers = result.filter(
      (n) => n.type === 'org-person' && n.id.startsWith(`${TEAM_GROUP_PREFIX}t-platform`),
    )
    const designMembers = result.filter(
      (n) => n.type === 'org-person' && n.id.startsWith(`${TEAM_GROUP_PREFIX}t-design`),
    )
    expect(platformMembers).toHaveLength(0)
    expect(designMembers).toHaveLength(2)
  })

  it('a team id present nowhere in the data leaves every roster empty of members', () => {
    const result = applyTeamSectionFilter(teamNodes, 'nonexistent')
    expect(result.filter((n) => n.type === 'org-person')).toHaveLength(0)
    // Both containers still drawn — never a bare canvas.
    expect(result.filter((n) => n.type === 'org-group')).toHaveLength(3)
  })
})

describe('applyProcessToolFilter — the process grid', () => {
  it('is untouched when no tool is selected', () => {
    expect(applyProcessToolFilter(processNodes, null, ctx)).toEqual(processNodes)
  })

  it("narrows to the steps run by roles that carry the selected tool", () => {
    const result = applyProcessToolFilter(processNodes, 'web_search', ctx)
    expect(result.map((n) => (n.data as { role_id: string }).role_id)).toEqual(['r-eng'])
  })

  it('a tool name present nowhere in the data empties the whole grid — no lone leftover step', () => {
    expect(applyProcessToolFilter(processNodes, 'nonexistent', ctx)).toEqual([])
  })
})

describe('applyToolSectionFilter — the tool grid', () => {
  it('is untouched when no tool is selected', () => {
    expect(applyToolSectionFilter(toolNodes, null)).toEqual(toolNodes)
  })

  it('narrows to the one selected tool node', () => {
    const result = applyToolSectionFilter(toolNodes, 'web_search')
    expect(result.map((n) => n.id)).toEqual(['tool:web_search'])
  })

  it('a tool name present nowhere in the data empties the grid entirely', () => {
    expect(applyToolSectionFilter(toolNodes, 'nonexistent')).toEqual([])
  })
})

describe('teamFilterCounts / toolFilterCounts — mirror roleLensCounts', () => {
  it('reports every person as shown when no team is selected', () => {
    expect(teamFilterCounts(hierarchyNodes, null, ctx)).toEqual({ shown: 5, total: 5 })
  })

  it('counts only the people the selected team carries, against the true total', () => {
    expect(teamFilterCounts(hierarchyNodes, 't-design', ctx)).toEqual({ shown: 2, total: 5 })
  })

  it('reports zero shown for a team nothing on the canvas carries', () => {
    expect(teamFilterCounts(hierarchyNodes, 'nonexistent', ctx)).toEqual({ shown: 0, total: 5 })
  })

  it('reports every person as shown when no tool is selected', () => {
    expect(toolFilterCounts(hierarchyNodes, null, ctx)).toEqual({ shown: 5, total: 5 })
  })

  it('counts only the people whose role carries the selected tool, against the true total', () => {
    expect(toolFilterCounts(hierarchyNodes, 'web_search', ctx)).toEqual({ shown: 3, total: 5 })
  })
})
