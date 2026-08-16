// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canvas node sidebar — data model (#13940).
 *
 * The sidebar `OrgChart.vue` opens on a node selection (tree, canvas or the
 * People list — all three call the same `openDrawer`) gets a fixed slot
 * order: owner -> tools -> notes (overview/checklist/output) -> attributes,
 * plus a right icon rail. This module holds the parts that are not markup:
 * what each rail slot binds to, and — per #13940's mandate to audit first and
 * never build a slot with no data — why five of the promised six rail icons
 * bind to something real and one does not exist at all.
 *
 * ## Per-slot audit
 *
 * | rail slot | binds to | agent node | human node |
 * |---|---|---|---|
 * | info | fields already on `OrgChartNode` (org-chart response) | yes | yes |
 * | checklist | `GET /work-items?company_id&assignee=<node_id>` | yes | **no** |
 * | cost | `GET /companies/{id}/costs/by-agent-model`, row matched on `agent_id === node.id` | yes | **no** |
 * | activity | `GET /companies/{id}/activity?entity_type=agent&entity_id=<node.id>` | yes | **no** |
 * | handoff | the same checklist fetch — each row opens the existing `HandoffModal` (`direction: 'to_human'`), not a new endpoint | yes | **no** |
 * | comments | **no endpoint exists anywhere** — omitted from the rail entirely, see below | — | — |
 *
 * The three human "no"s share one root cause, not three:
 * `WorkItemService.list_by_project` (`autobot-backend/llc/services/
 * work_item_service.py`) accepts `assignee_agent_id` but has **no
 * `assignee_user_id` parameter at all** — confirmed by reading its signature,
 * not inferred — so a human node's assigned items can never be fetched
 * through the existing `/work-items` endpoint. `cost` and `activity` fail the
 * identical structural test for a different reason: `llc_agent_budgets` and
 * the activity log's `entity_type="agent"` writer (`controls_service.py`)
 * are agent-only by construction — there is no per-user budget row and no
 * activity entry is ever logged against a membership's user id. `checklist`,
 * `handoff` and `output` (a Notes sub-tab, not a rail icon) all key off the
 * same missing filter, so a human node reports one honest
 * `notApplicable` state rather than three unrelated-looking gaps.
 *
 * `comments` is not in `SIDEBAR_RAIL_ICONS` at all: the only comment thread
 * in Company OS is `/work-items/{id}/comments`, scoped to one work item.
 * Nothing attaches a comment thread to an org-chart node (an agent or a
 * person), for either node kind. Per #13940's "a slot with no data source
 * renders an honest empty state or is omitted", this one is omitted — a
 * permanently-empty comments panel would be indistinguishable from a feature
 * that is simply broken (#14105 records exactly that cost for a different
 * screen). This is a scope gap, not a bug: filed as a follow-up rather than
 * adding a new backend object, which #13940 rules out.
 *
 * This module is pure data/URL-building; the fetch calls and the markup live
 * in `CanvasNodeSidebar.vue`, which owns the loading/unavailable state per
 * the same not-empty-on-failure rule #14064 and #14104 established.
 */

import type { WorkItem } from '@/views/llc/workItemTypes'

/** The subset of `OrgNode` this module needs, so callers do not have to
 * import the full tree type just to build a URL. */
export interface SidebarNode {
  id: string
  node_id?: string
  is_human: boolean
}

/** Rail icons, in the fixed order the sidebar renders them. `comments` is
 * deliberately absent — see the module docstring. */
export type SidebarRailIcon = 'info' | 'checklist' | 'cost' | 'activity' | 'handoff'
export const SIDEBAR_RAIL_ICONS: readonly SidebarRailIcon[] = [
  'info',
  'checklist',
  'cost',
  'activity',
  'handoff',
]

/** Notes sub-tabs, in the fixed order. */
export type NoteTab = 'overview' | 'checklist' | 'output'
export const NOTE_TABS: readonly NoteTab[] = ['overview', 'checklist', 'output']

/**
 * Load state for a slot fetched over the network.
 *
 * `unavailable` is a *failed* fetch (#14064's distinction, extended here by
 * `notApplicable`: a slot that was never attempted because the node kind
 * structurally cannot answer it — see the module docstring). Neither is ever
 * rendered the same as `loaded` with zero items.
 */
export type SlotStatus = 'idle' | 'loading' | 'loaded' | 'unavailable' | 'notApplicable'

export interface SlotState<T> {
  status: SlotStatus
  items: T[]
}

export function emptySlotState<T>(): SlotState<T> {
  return { status: 'idle', items: [] }
}

/**
 * True only when the node's assigned items are reachable through the
 * existing `GET /work-items?assignee=` filter — agents only, and only once
 * the org-chart response's `node_id` (the assignment-keyspace UUID, #10032)
 * is present. A human node, or a fixture written before #13940 that omits
 * `node_id`, is a structural "not applicable", never a fetch attempt.
 */
export function canFetchAssignedItems(node: SidebarNode): boolean {
  return !node.is_human && !!node.node_id
}

export function assignedItemsUrl(companyId: string, node: SidebarNode): string {
  return `/api/llc/work-items?company_id=${encodeURIComponent(companyId)}&assignee=${encodeURIComponent(node.node_id ?? '')}`
}

const DONE_STATUS: WorkItem['status'] = 'done'
const TERMINAL_STATUSES: ReadonlySet<WorkItem['status']> = new Set(['done', 'cancelled'])

/** Checklist = active items; output = the same fetch's finished ones. One
 * network call, two Notes sub-tabs — never a second request for `output`. */
export function partitionAssignedItems(items: readonly WorkItem[]): {
  open: WorkItem[]
  done: WorkItem[]
} {
  const open: WorkItem[] = []
  const done: WorkItem[] = []
  for (const item of items) {
    if (item.status === DONE_STATUS) done.push(item)
    else if (!TERMINAL_STATUSES.has(item.status)) open.push(item)
  }
  return { open, done }
}

/** Path-scoped sibling of `/api/llc/costs/by-agent-model` (`llc/api/
 * budget.py`'s `costs_by_model_router`) — chosen over the query-param form
 * because it is tenant-checked by `assert_company_access` on the path
 * segment itself and needs no `company_id` query string. */
export function costUrl(companyId: string): string {
  return `/api/llc/companies/${encodeURIComponent(companyId)}/costs/by-agent-model`
}

export interface AgentCostRow {
  agent_id: string
  agent_name: string
  total_tokens: number
  cost_usd: string
}

/** Cost rows are keyed by the agent slug — `OrgChartNode.id`, not
 * `node_id` (see the module docstring's id-vs-node_id distinction). */
export function findAgentCost(rows: readonly AgentCostRow[], node: SidebarNode): AgentCostRow | null {
  return rows.find((row) => row.agent_id === node.id) ?? null
}

const ACTIVITY_PAGE_SIZE = 20

/** Activity entries key on `entity_id = node.id` (the agent slug) because
 * that is exactly what `controls_service.py` writes as `entity_id` for
 * pause/resume/terminate — the same value the pause/resume POST already
 * sends as `{agent_id}` in the URL path. */
export function activityUrl(companyId: string, node: SidebarNode): string {
  const params = new URLSearchParams({
    entity_type: 'agent',
    entity_id: node.id,
    page_size: String(ACTIVITY_PAGE_SIZE),
  })
  return `/api/llc/companies/${encodeURIComponent(companyId)}/activity?${params.toString()}`
}
