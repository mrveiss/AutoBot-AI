// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Canonical LLC work-item shape (#9724).
 *
 * Previously declared independently in KanbanBoardView, SprintBoardView,
 * BacklogView and WorkItemDetail with drifting fields (assignee_type /
 * column_id), which made the views' WorkItem incompatible with
 * WorkItemDetail's `@updated` payload.
 *
 * Both `column_id` and `assignee_type` are optional because neither is on
 * every response (GH#13993):
 * - `assignee_type` is emitted by the work-items response (`api/work_items.py`)
 *   and, since GH#13993, by the board-items response as well.
 * - `column_id` is derived from a board's column `status_filter` rather than
 *   stored on the item, so ONLY the board-items response
 *   (`GET /api/llc/boards/{id}/items`) carries it.
 */

/**
 * Closed work-item enum sets (#11131). Kept in sync with the `llc.enums.*`
 * i18n keys and the `<WorkItemBadge>` color classes so the allowed values are
 * enforced at compile time rather than being bare `string`.
 */
export type WorkItemType = 'epic' | 'feature' | 'pbi' | 'task' | 'bug' | 'spike' | 'subtask' | 'risk'
export type WorkItemPriority = 'critical' | 'high' | 'medium' | 'low'
export type WorkItemStatus =
  | 'backlog'
  | 'ready'
  | 'in_progress'
  | 'in_review'
  | 'done'
  | 'blocked'
  | 'cancelled'

/**
 * What `GET /api/llc/boards/{id}/items` actually returns per card (#14075).
 *
 * `_work_item_summary` (autobot-backend/llc/api/boards.py:95-115) emits
 * exactly these 11 keys. The board views used to assert `WorkItem` here,
 * which is a claim TypeScript cannot check — and it was wrong: the summary
 * carries none of `description`, `assignee_name`, `reviewer_user_id`,
 * `reviewer_agent_id`, `sprint_id`, `labels`, `acceptance_criteria`,
 * `acceptance_criteria_done` or `linked_pr_urls`.
 *
 * Typing the board payload honestly is what makes #14044 a compile-time
 * concern rather than a blank panel: anything needing a detail field must
 * fetch the item, because this type does not have one to read.
 */
export interface WorkItemSummary {
  id: string
  identifier: string
  title: string
  type: WorkItemType
  status: WorkItemStatus
  priority: WorkItemPriority
  story_points: number | null
  assignee_agent_id: string | null
  assignee_user_id: string | null
  assignee_type: 'user' | 'agent' | null
  column_id: string
}

export interface WorkItem {
  id: string
  identifier: string
  type: WorkItemType
  title: string
  description: string
  priority: WorkItemPriority
  story_points: number | null
  assignee_name: string | null
  // GH#13993: backend only ever writes 'user' | 'agent' (never 'human').
  assignee_type?: 'user' | 'agent' | null
  // Assignment keyspace (#10032): agent = AgentOrgNode UUID PK, user = user UUID.
  assignee_agent_id?: string | null
  assignee_user_id?: string | null
  reviewer_user_id?: string | null
  reviewer_agent_id?: string | null
  sprint_id: string | null
  column_id?: string
  status: WorkItemStatus
  labels: string[]
  acceptance_criteria: string[]
  // GH#10852: per-criterion completion, parallel-indexed to acceptance_criteria.
  acceptance_criteria_done?: boolean[]
  linked_pr_urls?: string[]
}
