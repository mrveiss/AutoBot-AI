// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canvas node sidebar — data model (#13940, #14192).
 *
 * The sidebar `OrgChart.vue` opens on a node selection (tree, canvas or the
 * People list — all three call the same `openDrawer`) gets a fixed slot
 * order: owner -> tools -> notes (overview/checklist/output) -> attributes,
 * plus a right icon rail. This module holds the parts that are not markup:
 * what each rail slot binds to, and — per #13940's mandate to audit first and
 * never build a slot with no data — why some of the promised six rail icons
 * bind to something real, why one is agent-only for a structural reason
 * (#14192), and why one does not exist at all.
 *
 * ## Per-slot audit
 *
 * | rail slot | binds to | agent node | human node |
 * |---|---|---|---|
 * | info | fields already on `OrgChartNode` (org-chart response) | yes | yes |
 * | checklist | `GET /work-items?company_id&assignee=<node_id>` (agent) or `&assignee_user_id=<node_id>` (human, #14192) | yes | yes |
 * | cost | `GET /companies/{id}/costs/by-agent-model`, row matched on `agent_id === node.id` | yes | **no** |
 * | activity | `GET /companies/{id}/activity?entity_type=agent&entity_id=<node.id>` | yes | **no** |
 * | handoff | the same checklist fetch feeds the row list; each row opens `HandoffModal` (`direction: 'to_human'`), which POSTs the *agent*-only `/handoff/to-human` endpoint | yes | **no** |
 * | comments | **no endpoint exists anywhere** — omitted from the rail entirely, see below | — | — |
 *
 * `checklist` (and the `output`/`checklist` Notes sub-tabs, which read the
 * same fetch) used to be human-"no" for one root cause: `WorkItemService.
 * list_by_project` (`autobot-backend/llc/services/work_item_service.py`)
 * accepted `assignee_agent_id` but had **no `assignee_user_id` parameter at
 * all** — confirmed by reading its signature, not inferred — so a human
 * node's assigned items could never be fetched through the existing
 * `/work-items` endpoint even though the data was always there
 * (`LLCWorkItem.assignee_user_id`, populated since #10532, and already read
 * by `llc/api/companies.py`'s `_compose_human_nodes` for the org-chart's own
 * per-person item count). #14192 closed that gap: `list_by_project` and
 * `GET /work-items` both gained an `assignee_user_id` filter, so
 * `canFetchAssignedItems` below no longer excludes a human node.
 *
 * `handoff` stays human-"no" for a *different*, deeper reason that the
 * missing filter alone does not fix: `HandoffService.agent_to_human`
 * (`autobot-backend/llc/services/handoff.py`) rejects any work item whose
 * `assignee_agent_id` does not match the caller's `agent_id` — and a
 * human-assigned item's `assignee_agent_id` is always `NULL`, so the call
 * would always raise `HandoffNotAllowed`. There is no `human_to_human`
 * handoff verb in Company OS today. Fetching the list is now possible for a
 * human node (`canFetchAssignedItems`), but offering the "Hand Off" *action*
 * on that list is not (`canHandoffAssignedItems`) — the two are
 * deliberately different predicates so the checklist/output tabs can show
 * real data while the handoff panel still reports an honest
 * `notApplicable` rather than a button that always 400s.
 *
 * `cost` and `activity` are unrelated gaps, both product decisions rather
 * than "add a filter" fixes: `llc_agent_budgets` and the activity log's
 * `entity_type="agent"` writer (`controls_service.py`) are agent-only by
 * construction — there is no per-user budget row and no activity entry is
 * ever logged against a membership's user id. Left as `notApplicable`
 * pending an owner decision on whether a company member should be
 * metered/audited the way a hired agent is (#14192's Gap 2).
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
 * True once the node's assigned items are reachable through `GET
 * /work-items` — either the `assignee` (agent) or `assignee_user_id`
 * (human, #14192) filter — and the org-chart response's `node_id` (the
 * assignment-keyspace id, #10032) is present. Only a fixture written before
 * #13940 that omits `node_id` is a structural "not applicable" now; node
 * kind alone no longer excludes a fetch attempt.
 */
export function canFetchAssignedItems(node: SidebarNode): boolean {
  return !!node.node_id
}

/**
 * True only when the node's assigned items may also be offered the "Hand
 * Off" *action* — narrower than `canFetchAssignedItems` on purpose. The
 * list is fetchable for a human node since #14192, but `HandoffService.
 * agent_to_human` (`autobot-backend/llc/services/handoff.py`) requires the
 * item's `assignee_agent_id` to match the caller, which is never true for a
 * human-assigned item (`assignee_agent_id` is always `NULL` there). There is
 * no `human_to_human` handoff verb, so the action stays agent-only even
 * though the underlying list is not — see the module docstring.
 */
export function canHandoffAssignedItems(node: SidebarNode): boolean {
  return !node.is_human && canFetchAssignedItems(node)
}

export function assignedItemsUrl(companyId: string, node: SidebarNode): string {
  // #14192: a human node's `node_id` is a user id, never an agent id — it
  // must be sent through the `assignee_user_id` keyspace-specific param, not
  // the agent-only `assignee` one, or the filter would silently match zero
  // rows (LLCWorkItem.assignee_agent_id is never a user id).
  const param = node.is_human ? 'assignee_user_id' : 'assignee'
  return `/api/llc/work-items?company_id=${encodeURIComponent(companyId)}&${param}=${encodeURIComponent(node.node_id ?? '')}`
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
