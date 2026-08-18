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
 * that is the direction the canvas draws its ports and bezier edges in. A root
 * subtree that actually *is* a hierarchy also gets an `org-group` container
 * node — the section/grouping container — sized to its subtree bounding box and
 * emitted first so it paints behind the people.
 *
 * GH#13994: "root" is not a synonym for "unit". People join the forest as roots
 * because a membership carries no `reports_to` edge, so wrapping every root
 * turned a company of twelve people into twelve single-person "units". A unit
 * is a root that has someone under it; everyone else is drawn bare, in a grid
 * below the units.
 */

import type { CanvasNode } from '@/components/workflow/canvasNode'
import { CANVAS_NODE_WIDTH } from '@/components/workflow/canvasNode'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'
import type { CompanyTeam, OrgPerson } from './orgPeople'
import { UNGROUPED_TEAM_ID, groupPeopleByTeam } from './orgPeople'

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
/**
 * Columns in the grid of ungrouped individuals (GH#13994). They have no
 * hierarchy to lay out, so they pack across before they stack down — a company
 * of twelve people is three rows of a readable grid, not a twelve-row column
 * the reader has to pan through.
 */
const UNGROUPED_COLUMNS = 4
/** Id prefix that keeps container ids from colliding with agent ids. */
/**
 * What a container node stands for (#14596).
 *
 * Carried in `data` rather than as a new `CanvasNodeType`: the renderer's
 * `nodeIcons` / `nodeLabels` are `Record<CanvasNodeType, ...>` literals, so a
 * new member is a compile error until both gain entries — and neither an icon
 * nor a type label is what distinguishes these. What differs is how the box is
 * drawn, which is a styling concern.
 */
export const GROUP_KIND_UNIT = 'unit'
export const GROUP_KIND_TEAM = 'team'

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

/** One person node, offset by the origin of whatever region holds it. */
function toPersonNode(placed: PlacedNode, leftOffset: number, topOffset: number): CanvasNode {
  const { node } = placed
  return {
    id: node.id,
    type: 'org-person',
    position: { x: leftOffset + placed.x, y: topOffset + placed.y },
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
      // #14596: which kind of container this is, so the renderer can draw them
      // differently. A team and a reporting unit answer different questions —
      // "who works together" and "who reports to whom" — and until this
      // existed they were the same box with different words in it.
      kind: GROUP_KIND_UNIT,
      width: 2 * GROUP_PADDING + (depth + 1) * CANVAS_NODE_WIDTH + depth * COLUMN_GAP,
      height: GROUP_HEADER + 2 * GROUP_PADDING + rows * ROW_HEIGHT,
    },
    connections: [],
  }
}

/**
 * Is this root an org *unit* — something a container and a tab can stand for?
 *
 * Only a root with someone under it. Root-ness alone is not a unit: the
 * org-chart endpoint returns every person of the company as a root because a
 * membership carries no `reports_to` edge, and treating that as a unit drew one
 * container and one tab per person (GH#13994).
 *
 * This is the single definition of "unit" — `buildOrgCanvasGraph` draws the
 * containers from it and `OrgChart.vue` builds the tab strip from it, so the
 * strip and the canvas cannot disagree about what a unit is. It stays a
 * structural proxy only until real team grouping lands (GH#13938).
 */
export function isOrgUnit(root: OrgNode): boolean {
  return (root.children ?? []).length > 0
}

/** The roots that are units, in tree order. */
export function orgUnitRoots(roots: OrgNode[]): OrgNode[] {
  return roots.filter(isOrgUnit)
}

/**
 * Lay out one unit — its container plus the subtree inside it.
 *
 * @returns the next free top offset
 */
function layoutUnit(
  root: OrgNode,
  topOffset: number,
  groups: CanvasNode[],
  people: CanvasNode[],
  unitLabel: (name: string) => string,
): number {
  const placed: PlacedNode[] = []
  const cursor = { row: 0 }
  placeSubtree(root, 0, cursor, placed)
  const contentTop = topOffset + GROUP_HEADER + GROUP_PADDING
  for (const item of placed) people.push(toPersonNode(item, GROUP_PADDING, contentTop))
  groups.push(toGroupNode(root, placed, topOffset, cursor.row, unitLabel))
  return topOffset + GROUP_HEADER + 2 * GROUP_PADDING + cursor.row * ROW_HEIGHT + GROUP_GAP
}

/**
 * Lay out the individuals who are not a unit: a bare grid, no container.
 *
 * They are still first-class canvas nodes — same id, same payload, same click
 * target — they simply are not wrapped in a box that claims they are an
 * organisational unit of one (GH#13994).
 */
function layoutUngrouped(roots: OrgNode[], topOffset: number, people: CanvasNode[]): void {
  roots.forEach((root, index) => {
    const placed: PlacedNode = {
      node: root,
      depth: 0,
      x: (index % UNGROUPED_COLUMNS) * (CANVAS_NODE_WIDTH + COLUMN_GAP),
      y: Math.floor(index / UNGROUPED_COLUMNS) * ROW_HEIGHT,
    }
    people.push(toPersonNode(placed, 0, topOffset))
  })
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
  for (const root of orgUnitRoots(roots)) {
    topOffset = layoutUnit(root, topOffset, groups, people, unitLabel)
  }
  layoutUngrouped(
    roots.filter((root) => !isOrgUnit(root)),
    topOffset,
    people,
  )
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


/** A workflow a role runs, as returned by ``GET .../process-nodes`` (#13963). */
export interface ProcessNodeSource {
  role_id: string
  role_name: string
  workflow_id: string
}

/** Prefix that marks a canvas node as a process, so a click can be routed. */
export const PROCESS_NODE_PREFIX = 'process:'

/**
 * Lay out process nodes below the people graph (#13963).
 *
 * They pack across before stacking down, like ungrouped individuals: a company
 * with a dozen processes should read as a grid, not a column the reader has to
 * pan through.
 *
 * Placed *below* `topOffset` rather than interleaved with the hierarchy on
 * purpose — a process is not a person and does not report to anyone, so giving
 * it a position in the reporting tree would assert a relationship that does not
 * exist.
 */
export function buildProcessCanvasNodes(
  processes: ProcessNodeSource[],
  topOffset: number,
): CanvasNode[] {
  return processes.map((process, index) => ({
    id: `${PROCESS_NODE_PREFIX}${process.role_id}:${process.workflow_id}`,
    type: 'org-process',
    position: {
      x: (index % UNGROUPED_COLUMNS) * (CANVAS_NODE_WIDTH + COLUMN_GAP),
      y: topOffset + Math.floor(index / UNGROUPED_COLUMNS) * ROW_HEIGHT,
    },
    data: {
      role_id: process.role_id,
      role_name: process.role_name,
      workflow_id: process.workflow_id,
    },
    // Required by CanvasNode (via WorkflowNode). Always empty: a process node
    // draws no edges — it is an entry point, not a step in a graph. Declared so
    // the type is satisfied structurally instead of cast past, which would have
    // hidden the next missing field rather than naming it.
    connections: [],
  }))
}

/** The workflow a process node opens, or null if the id is not a process node. */
export function workflowIdFromProcessNode(nodeId: string): string | null {
  if (!nodeId.startsWith(PROCESS_NODE_PREFIX)) return null
  // id = process:<role_id>:<workflow_id>; a workflow id may itself contain ':'
  // so split off exactly the prefix and the role id, and keep the rest whole.
  const rest = nodeId.slice(PROCESS_NODE_PREFIX.length)
  const separator = rest.indexOf(':')
  if (separator < 0) return null
  const workflowId = rest.slice(separator + 1)
  return workflowId.length > 0 ? workflowId : null
}

/** Lowest edge of a laid-out graph, so later sections start below it. */
export function canvasBottom(nodes: CanvasNode[]): number {
  return nodes.reduce((lowest, node) => Math.max(lowest, node.position.y + ROW_HEIGHT), 0)
}

/**
 * Teams on the canvas (GH#14596, parent #13938).
 *
 * `isOrgUnit`/`org-group` above answers "who reports to whom", derived from
 * the hierarchy. A team is a different question — "who works together" — and
 * is read from `GET .../teams` via `groupPeopleByTeam` (`orgPeople.ts`), the
 * same function the People list already groups by, so the canvas and the
 * People list can never disagree about who is on a team.
 *
 * A team container reuses the `org-group` node type rather than inventing a
 * new one: `WorkflowCanvas.vue` sizes and renders `org-group` generically
 * already, so a team container needs no new branch there. It is visually
 * distinct from a reporting-unit container by construction — a different id
 * namespace (`TEAM_GROUP_PREFIX`, never `ORG_GROUP_PREFIX`), a different
 * caption ("<name> team" vs "<name> unit", GH#14596), and its own section
 * below the hierarchy — not a CSS variant of the same box, which would need
 * a change to `WorkflowCanvas.vue` this composable does not make.
 */

/**
 * Id prefix for a team's own container, and for every duplicate member node
 * inside it. Deliberately not `ORG_GROUP_PREFIX`: a reporting unit and a team
 * must never collide on id, and the prefix alone is enough for a reader of
 * the graph (or a test) to tell which kind of container a node is.
 */
export const TEAM_GROUP_PREFIX = 'org-team:'

/** Separates a team's id from the real org-chart id inside a composite id. */
const TEAM_MEMBER_MARK = ':member:'

/**
 * A team member's canvas id: stable and unique per (team, person) pair.
 *
 * Not the person's own `orgNodeId` — the same person can be on several teams,
 * and the canvas cannot draw two nodes that share an id. It is also not a
 * fresh, disconnected identity: the real org-chart id is embedded whole, so
 * `teamMemberOrgNodeId` can always recover exactly who this node is.
 */
function teamMemberNodeId(groupId: string, orgNodeId: string): string {
  return `${TEAM_GROUP_PREFIX}${groupId}${TEAM_MEMBER_MARK}${orgNodeId}`
}

/**
 * The real org-chart node id behind a team-member canvas node, or `null` when
 * `nodeId` does not name one (a team container, an `org-person` from the
 * reporting hierarchy, a process node, …).
 *
 * Lets a click on a person's roster card in a team open the same drawer a
 * click on their reporting-hierarchy node opens — the two are the same
 * person, not two identities that happen to share a name.
 */
export function teamMemberOrgNodeId(nodeId: string): string | null {
  if (!nodeId.startsWith(TEAM_GROUP_PREFIX)) return null
  const at = nodeId.indexOf(TEAM_MEMBER_MARK)
  if (at < 0) return null
  const orgNodeId = nodeId.slice(at + TEAM_MEMBER_MARK.length)
  return orgNodeId.length > 0 ? orgNodeId : null
}

/**
 * One team's (or the ungrouped bucket's) people, packed in a grid inside
 * their own container — a team carries no hierarchy, so it lays out like the
 * ungrouped grid above, not like a unit's tree (#13994's same reasoning,
 * applied to a team instead of a bare root).
 *
 * @returns the next free top offset, so groups stack without overlapping.
 */
function layoutTeamGroup(
  groupId: string,
  label: string,
  members: OrgNode[],
  topOffset: number,
  groups: CanvasNode[],
  memberNodes: CanvasNode[],
): number {
  const columns = Math.min(UNGROUPED_COLUMNS, Math.max(1, members.length))
  const rows = Math.max(1, Math.ceil(members.length / UNGROUPED_COLUMNS))
  const contentTop = topOffset + GROUP_HEADER + GROUP_PADDING
  members.forEach((member, index) => {
    memberNodes.push({
      id: teamMemberNodeId(groupId, member.id),
      type: 'org-person',
      position: {
        x: GROUP_PADDING + (index % UNGROUPED_COLUMNS) * (CANVAS_NODE_WIDTH + COLUMN_GAP),
        y: contentTop + Math.floor(index / UNGROUPED_COLUMNS) * ROW_HEIGHT,
      },
      data: {
        label: member.name,
        title: member.title,
        status: member.status,
        adapter_type: member.adapter_type,
        is_human: member.is_human,
      },
      // A roster is not a reporting line: nobody in it reports to anyone
      // else in it by virtue of team membership alone.
      connections: [],
    })
  })
  groups.push({
    id: `${TEAM_GROUP_PREFIX}${groupId}`,
    type: 'org-group',
    position: { x: 0, y: topOffset },
    data: {
      label,
      kind: GROUP_KIND_TEAM,
      width: 2 * GROUP_PADDING + columns * CANVAS_NODE_WIDTH + (columns - 1) * COLUMN_GAP,
      height: GROUP_HEADER + 2 * GROUP_PADDING + rows * ROW_HEIGHT,
    },
    connections: [],
  })
  return topOffset + GROUP_HEADER + 2 * GROUP_PADDING + rows * ROW_HEIGHT + GROUP_GAP
}

/**
 * Build the canvas rendering of the company's teams.
 *
 * Every member becomes its own `org-person` canvas node inside its team's
 * container — one node per (team, person) pair, so a person on several teams
 * appears in each without duplicating their identity (`teamMemberNodeId`).
 * The `UNGROUPED_TEAM_ID` bucket (`orgPeople.ts`) renders the same way, so a
 * person on no team is still a first-class, visible, labelled node — never
 * silently dropped the way a filtered-out node would be.
 *
 * Only people with an `orgNodeId` are placed — a contact has none and is
 * already absent from the canvas everywhere else (#13938); this does not
 * introduce a new exclusion, it stays consistent with the one that exists.
 *
 * Draws nothing at all when the company has zero teams — mirroring
 * `OrgPeopleList.vue`'s own `v-if="hasTeams"` gate on its group headers. A
 * company with no teams has no team *structure* to draw a boundary around;
 * boxing everyone into a single "not in a team" container would assert a
 * grouping that does not exist. The honest statement for that case is the
 * "no teams are defined" banner the caller renders beside the canvas, not an
 * empty-of-meaning box drawn here.
 */
export function buildTeamCanvasNodes(
  orgNodesById: Map<string, OrgNode>,
  people: OrgPerson[],
  teams: CompanyTeam[],
  topOffset: number,
  teamLabel: (name: string) => string,
  ungroupedLabel: string,
): CanvasNode[] {
  if (teams.length === 0) return []
  const groups: CanvasNode[] = []
  const memberNodes: CanvasNode[] = []
  let cursor = topOffset
  for (const group of groupPeopleByTeam(people, teams)) {
    const members = group.people
      .map((person) => (person.orgNodeId ? orgNodesById.get(person.orgNodeId) : undefined))
      .filter((node): node is OrgNode => node !== undefined)
    const label = group.id === UNGROUPED_TEAM_ID ? ungroupedLabel : teamLabel(group.name)
    cursor = layoutTeamGroup(group.id, label, members, cursor, groups, memberNodes)
  }
  return [...groups, ...memberNodes]
}
