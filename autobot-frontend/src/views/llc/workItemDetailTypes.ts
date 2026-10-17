// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Side-panel record shapes for WorkItemDetail.vue (split out of the component for the size ceiling, #18730). */

export interface Comment {
  id: string
  body: string
  author_name: string
  author_type: 'human' | 'agent'
  created_at: string
}

export interface Artifact {
  id: string
  name: string
  type: string
  url: string
}

export interface ActivityEvent {
  id: string
  actor_name: string
  description: string
  created_at: string
}

export interface GoalAncestor {
  id: string
  title: string
}
