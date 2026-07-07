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
 * `column_id` and `assignee_type` are only present on board API responses,
 * hence optional here.
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

export interface WorkItem {
  id: string
  identifier: string
  type: WorkItemType
  title: string
  description: string
  priority: WorkItemPriority
  story_points: number | null
  assignee_name: string | null
  assignee_type?: 'human' | 'agent' | null
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
  linked_pr_urls?: string[]
}
