// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Multi-property filtering for the Company OS canvas (#14608, parent #13935,
 * extends #13943).
 *
 * `orgRoleLens.ts` filters by exactly one property — a person's role. Once
 * teams (#14596) and tools (#14597) became canvas objects, that stopped
 * being enough: a reader wants "this team, using this tool" narrowed
 * together, not one property at a time.
 *
 * This module does not replace the role lens — it composes with it.
 * `applyHierarchyFilters` below calls `applyRoleLens` first, unchanged, and
 * only then narrows further by team and tool. The role lens's own exported
 * functions (`applyRoleLens`, `roleLensCounts`, `availableLensRoles`) are
 * untouched and still used directly by `OrgChart.vue` for the "View As:
 * role" control — this file adds two new axes beside it, on the same
 * per-node-type scoping decisions `orgRoleLens.ts` already established:
 *
 *   * Role narrows the reporting hierarchy only (`orgRoleLens.ts`'s own,
 *     unmodified decision) — never the team roster, process grid or tool
 *     grid, each of which "is a different grouping question" (#14596's own
 *     comment on `OrgChart.vue`'s `lensedCanvasNodes`).
 *   * Team narrows the reporting hierarchy (via real membership) *and* the
 *     team-roster section itself — the roster's own axis is exactly what
 *     "team" means, unlike role's relationship to it.
 *   * Tool narrows the reporting hierarchy (a person's title is one of the
 *     tool's carrying roles), the process grid (a step's `role_id` is one of
 *     the tool's role ids — the "steps ... using this tool" example the
 *     issue itself gives) and the tool grid (down to the one selected tool).
 *
 * Filters combine with AND: "team X, tool Y" means a person (or step) must
 * satisfy both, not either — matching how the issue's own example reads
 * ("owned by this team, using this tool, that are still manual" is a
 * conjunction in plain English) and how a reader narrows a large map: each
 * added filter should only ever remove nodes, never bring more back.
 *
 * Every filter here is presentation-only, same as the role lens: nothing in
 * this module fetches, authorises or withholds a response. See
 * `orgRoleLens.ts`'s module docstring for the fuller justification, which
 * applies unchanged to team and tool.
 */

import type { CanvasNode } from '@/components/workflow/canvasNode'
import { applyRoleLens, nodeTitle } from './orgRoleLens'
import { teamGroupIdOfMemberNode } from './orgCanvasGraph'
import type { ToolNodeSource } from './orgCanvasGraph'
import { groupPeopleByTeam } from './orgPeople'
import type { CompanyTeam, OrgPerson } from './orgPeople'

/** The multi-filter's current selection. `null` means "no filter on this axis". */
export interface CanvasFilterState {
  role: string | null
  team: string | null
  tool: string | null
}

/** True once at least one axis narrows the canvas. */
export function hasActiveCanvasFilters(filters: CanvasFilterState): boolean {
  return filters.role !== null || filters.team !== null || filters.tool !== null
}

/** True once team or tool narrows the canvas — the two axes this module adds. */
export function hasCombinedCanvasFilters(filters: CanvasFilterState): boolean {
  return filters.team !== null || filters.tool !== null
}

/**
 * Lookups the team and tool predicates need, built once per render from data
 * `OrgChart.vue` already fetches — never a second request.
 */
export interface CanvasFilterContext {
  /** Every team (or `UNGROUPED_TEAM_ID`) id a reporting-hierarchy person belongs to. */
  teamIdsByOrgNodeId: ReadonlyMap<string, ReadonlySet<string>>
  /** Role *names* (== a person's `title`) each tool is carried by. */
  toolRoleNames: ReadonlyMap<string, ReadonlySet<string>>
  /** Role *ids* (== a process node's `role_id`) each tool is carried by. */
  toolRoleIds: ReadonlyMap<string, ReadonlySet<string>>
}

/**
 * Every reporting-hierarchy org-chart node id, mapped to the team ids
 * (`CompanyTeam.id`, or `UNGROUPED_TEAM_ID`) it belongs to.
 *
 * Built from `groupPeopleByTeam` — the exact function `buildTeamCanvasNodes`
 * already groups the roster section by — so the hierarchy's team filter and
 * the roster it is drawn beside can never disagree about who is on a team.
 */
export function buildTeamIdsByOrgNodeId(
  people: OrgPerson[],
  teams: CompanyTeam[],
): Map<string, Set<string>> {
  const byOrgNodeId = new Map<string, Set<string>>()
  for (const group of groupPeopleByTeam(people, teams)) {
    for (const person of group.people) {
      if (!person.orgNodeId) continue
      let ids = byOrgNodeId.get(person.orgNodeId)
      if (!ids) {
        ids = new Set()
        byOrgNodeId.set(person.orgNodeId, ids)
      }
      ids.add(group.id)
    }
  }
  return byOrgNodeId
}

/**
 * Every tool name, mapped to the role names and role ids that carry it —
 * the same (role, tool) attachment rows `buildToolCanvasNodes` groups, kept
 * as two indices because the hierarchy only carries a person's `title`
 * (role *name*) while a process node carries `role_id`.
 */
export function buildToolRoleIndex(tools: readonly ToolNodeSource[]): {
  names: Map<string, Set<string>>
  ids: Map<string, Set<string>>
} {
  const names = new Map<string, Set<string>>()
  const ids = new Map<string, Set<string>>()
  for (const row of tools) {
    let nameSet = names.get(row.tool_name)
    if (!nameSet) {
      nameSet = new Set()
      names.set(row.tool_name, nameSet)
    }
    nameSet.add(row.role_name)

    let idSet = ids.get(row.tool_name)
    if (!idSet) {
      idSet = new Set()
      ids.set(row.tool_name, idSet)
    }
    idSet.add(row.role_id)
  }
  return { names, ids }
}

/**
 * Does this `org-person` node belong to `team`?
 *
 * A team-roster member node (`teamGroupIdOfMemberNode` recognises its id
 * shape) carries its team in the id itself, by construction — it is drawn
 * inside exactly one team's container. A reporting-hierarchy node has no
 * such id shape and is looked up in `ctx.teamIdsByOrgNodeId` instead.
 */
function personMatchesTeam(node: CanvasNode, team: string | null, ctx: CanvasFilterContext): boolean {
  if (!team) return true
  const rosterTeam = teamGroupIdOfMemberNode(node.id)
  if (rosterTeam !== null) return rosterTeam === team
  return ctx.teamIdsByOrgNodeId.get(node.id)?.has(team) ?? false
}

/** Does this `org-person` node's role carry `tool`? */
function personMatchesTool(node: CanvasNode, tool: string | null, ctx: CanvasFilterContext): boolean {
  if (!tool) return true
  const roles = ctx.toolRoleNames.get(tool)
  if (!roles) return false
  const title = nodeTitle(node)
  return title !== null && roles.has(title)
}

/**
 * The reporting-hierarchy canvas: role, team and tool combine with AND.
 *
 * Role is applied first via the unmodified `applyRoleLens` — the role lens
 * keeps behaving exactly as it did before this module existed. Team and
 * tool then narrow further, but only ever remove `org-person` nodes: an
 * `org-group` (unit) container passes through untouched, same reasoning
 * `applyRoleLens` already documents — the emptied box, not a missing one, is
 * the "filtered by view" cue (#14064's failure shape).
 */
export function applyHierarchyFilters(
  nodes: CanvasNode[],
  filters: CanvasFilterState,
  ctx: CanvasFilterContext,
): CanvasNode[] {
  const roleFiltered = applyRoleLens(nodes, filters.role)
  if (!filters.team && !filters.tool) return roleFiltered
  return roleFiltered.filter(
    (node) =>
      node.type !== 'org-person' ||
      (personMatchesTeam(node, filters.team, ctx) && personMatchesTool(node, filters.tool, ctx)),
  )
}

/**
 * The team-roster section (#14596): only the team axis touches it, for the
 * same reason `OrgChart.vue`'s `lensedCanvasNodes` already gives for why the
 * role lens does not — a roster answers a different question than role or
 * tool, and a person hidden from it here is still drawn on the
 * reporting-hierarchy canvas above.
 */
export function applyTeamSectionFilter(nodes: CanvasNode[], team: string | null): CanvasNode[] {
  if (!team) return nodes
  return nodes.filter((node) => node.type !== 'org-person' || teamGroupIdOfMemberNode(node.id) === team)
}

/**
 * The process grid (#13963): a step's tool is read from its own `role_id`,
 * never re-derived from a person's title — the same id `buildToolCanvasNodes`
 * already draws its tool -> process edges from, so the filter and the edges
 * it sits beside can never disagree about which steps a tool touches.
 *
 * Role and team are deliberately not applied here: neither a role nor a team
 * is carried on a process node's own data, and matching by the role *name*
 * a person happens to display would be a guess this module does not make.
 */
export function applyProcessToolFilter(
  nodes: CanvasNode[],
  tool: string | null,
  ctx: CanvasFilterContext,
): CanvasNode[] {
  if (!tool) return nodes
  const roleIds = ctx.toolRoleIds.get(tool)
  if (!roleIds) return []
  return nodes.filter((node) => {
    const data = node.data as Record<string, unknown>
    return typeof data.role_id === 'string' && roleIds.has(data.role_id)
  })
}

/** The tool grid (#14597): narrows to the one selected tool node. */
export function applyToolSectionFilter(nodes: CanvasNode[], tool: string | null): CanvasNode[] {
  if (!tool) return nodes
  return nodes.filter((node) => {
    const data = node.data as Record<string, unknown>
    return node.type !== 'org-tool' || data.tool_name === tool
  })
}

/** How many hierarchy people carry `team`, out of how many total. Mirrors `roleLensCounts`. */
export function teamFilterCounts(
  nodes: CanvasNode[],
  team: string | null,
  ctx: CanvasFilterContext,
): { shown: number; total: number } {
  const people = nodes.filter((node) => node.type === 'org-person')
  const total = people.length
  if (!team) return { shown: total, total }
  return { shown: people.filter((node) => personMatchesTeam(node, team, ctx)).length, total }
}

/** How many hierarchy people carry `tool`, out of how many total. Mirrors `roleLensCounts`. */
export function toolFilterCounts(
  nodes: CanvasNode[],
  tool: string | null,
  ctx: CanvasFilterContext,
): { shown: number; total: number } {
  const people = nodes.filter((node) => node.type === 'org-person')
  const total = people.length
  if (!tool) return { shown: total, total }
  return { shown: people.filter((node) => personMatchesTool(node, tool, ctx)).length, total }
}
