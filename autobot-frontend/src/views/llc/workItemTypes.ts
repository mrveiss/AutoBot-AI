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
export interface WorkItem {
  id: string
  identifier: string
  type: string
  title: string
  description: string
  priority: string
  story_points: number | null
  assignee_name: string | null
  assignee_type?: 'human' | 'agent' | null
  sprint_id: string | null
  column_id?: string
  status: string
  labels: string[]
  acceptance_criteria: string[]
  linked_pr_urls?: string[]
}
