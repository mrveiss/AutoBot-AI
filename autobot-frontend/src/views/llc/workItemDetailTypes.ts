// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Side-panel record shapes for WorkItemDetail.vue (split out of the component for the size ceiling, #18730). */

/** POST /work-items/{id}/comments body (work_items.py add_comment). No author name is served. */
export interface Comment {
  id: string
  body: string
  author_agent_id: string | null
  author_user_id: string | null
  created_at: string | null
}

/** GET /work-items/{id}/products item (work_items.py list_work_products). */
export interface RawWorkProduct {
  id: string
  type: string
  title: string
  url: string | null
}

export interface Artifact {
  id: string
  name: string
  type: string
  url: string | null
}

/** GET /work-items/{id}/activity item (ActivityLogEntry in llc/api/activity.py). */
export interface RawActivityEntry {
  id: string
  actor_type: string
  action: string
  occurred_at: string
}

export interface ActivityEvent {
  id: string
  actor_name: string
  description: string
  created_at: string
}

/** The comment API serves author ids only (no names), so the id is the label. */
export function commentAuthor(c: Comment): string {
  return c.author_agent_id ?? c.author_user_id ?? ''
}

export function toArtifact(p: RawWorkProduct): Artifact {
  return { id: p.id, name: p.title, type: p.type, url: p.url }
}

/** The log serves actor_type and action only, so those are what is shown. */
export function toActivityEvent(e: RawActivityEntry): ActivityEvent {
  return { id: e.id, actor_name: e.actor_type, description: e.action, created_at: e.occurred_at }
}

export interface GoalAncestor {
  id: string
  title: string
}
