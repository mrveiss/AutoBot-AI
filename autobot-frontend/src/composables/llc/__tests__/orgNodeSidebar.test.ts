// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13940: pure data-binding helpers behind the canvas node sidebar's fixed
// slot order + icon rail. No markup here — `CanvasNodeSidebar.test.ts` covers
// rendered content; this file pins the URL-building and partitioning rules
// that decide whether a slot is even attempted.

import { describe, it, expect } from 'vitest'
import {
  SIDEBAR_RAIL_ICONS,
  NOTE_TABS,
  canFetchAssignedItems,
  canHandoffAssignedItems,
  assignedItemsUrl,
  partitionAssignedItems,
  costUrl,
  findAgentCost,
  activityUrl,
  emptySlotState,
  type AgentCostRow,
} from '../orgNodeSidebar'
import type { WorkItem } from '@/views/llc/workItemTypes'

function item(overrides: Partial<WorkItem>): WorkItem {
  return {
    id: 'wi-1',
    identifier: 'TASK-1',
    type: 'task',
    title: 'Do the thing',
    description: '',
    priority: 'medium',
    story_points: null,
    assignee_name: null,
    sprint_id: null,
    status: 'in_progress',
    labels: [],
    acceptance_criteria: [],
    ...overrides,
  }
}

describe('SIDEBAR_RAIL_ICONS (#13940)', () => {
  it('is the fixed order info -> checklist -> cost -> activity -> handoff', () => {
    expect(SIDEBAR_RAIL_ICONS).toEqual(['info', 'checklist', 'cost', 'activity', 'handoff'])
  })

  it('never includes "comments" — no endpoint attaches a comment thread to an org-chart node', () => {
    expect(SIDEBAR_RAIL_ICONS).not.toContain('comments')
  })
})

describe('NOTE_TABS (#13940)', () => {
  it('is the fixed order overview -> checklist -> output', () => {
    expect(NOTE_TABS).toEqual(['overview', 'checklist', 'output'])
  })
})

describe('canFetchAssignedItems', () => {
  it('is true for an agent node with a node_id', () => {
    expect(canFetchAssignedItems({ id: 'agent-1', node_id: 'pk-1', is_human: false })).toBe(true)
  })

  it('is true for a human node with a node_id — list_by_project gained an assignee_user_id filter (#14192)', () => {
    expect(canFetchAssignedItems({ id: 'user:1', node_id: 'user-uuid-1', is_human: true })).toBe(true)
  })

  it('is false for an agent node missing node_id (a pre-#13940 fixture)', () => {
    expect(canFetchAssignedItems({ id: 'agent-1', is_human: false })).toBe(false)
  })

  it('is false for a human node missing node_id', () => {
    expect(canFetchAssignedItems({ id: 'user:1', is_human: true })).toBe(false)
  })
})

describe('canHandoffAssignedItems (#14192)', () => {
  it('is true for an agent node with a node_id — the existing agent_to_human verb applies', () => {
    expect(canHandoffAssignedItems({ id: 'agent-1', node_id: 'pk-1', is_human: false })).toBe(true)
  })

  it('is false for a human node even with a node_id — no human_to_human handoff verb exists', () => {
    expect(canHandoffAssignedItems({ id: 'user:1', node_id: 'user-uuid-1', is_human: true })).toBe(false)
  })

  it('is false for an agent node missing node_id', () => {
    expect(canHandoffAssignedItems({ id: 'agent-1', is_human: false })).toBe(false)
  })
})

describe('assignedItemsUrl', () => {
  it('filters an agent by the node_id (the assignment-keyspace UUID) through `assignee`', () => {
    const url = assignedItemsUrl('c1', { id: 'agent-slug', node_id: 'pk-uuid-1', is_human: false })
    expect(url).toBe('/api/llc/work-items?company_id=c1&assignee=pk-uuid-1')
  })

  it('filters a human node by node_id through `assignee_user_id`, not `assignee` (#14192)', () => {
    const url = assignedItemsUrl('c1', { id: 'user:1', node_id: 'user-uuid-1', is_human: true })
    expect(url).toBe('/api/llc/work-items?company_id=c1&assignee_user_id=user-uuid-1')
  })
})

describe('partitionAssignedItems', () => {
  it('splits open (checklist) from done (output) and drops cancelled from both', () => {
    const items = [
      item({ id: '1', status: 'in_progress' }),
      item({ id: '2', status: 'done' }),
      item({ id: '3', status: 'backlog' }),
      item({ id: '4', status: 'cancelled' }),
      item({ id: '5', status: 'done' }),
    ]
    const { open, done } = partitionAssignedItems(items)
    expect(open.map((i) => i.id)).toEqual(['1', '3'])
    expect(done.map((i) => i.id)).toEqual(['2', '5'])
  })

  it('returns empty partitions for an empty list', () => {
    expect(partitionAssignedItems([])).toEqual({ open: [], done: [] })
  })
})

describe('costUrl', () => {
  it('is the path-scoped sibling endpoint, tenant-checked on the path segment', () => {
    expect(costUrl('c1')).toBe('/api/llc/companies/c1/costs/by-agent-model')
  })
})

describe('findAgentCost', () => {
  const rows: AgentCostRow[] = [
    { agent_id: 'ceo', agent_name: 'Ada', total_tokens: 500, cost_usd: '0.12' },
    { agent_id: 'dev', agent_name: 'Grace', total_tokens: 900, cost_usd: '0.30' },
  ]

  it('matches on the agent slug (OrgChartNode.id), not node_id', () => {
    expect(findAgentCost(rows, { id: 'dev', is_human: false })).toEqual(rows[1])
  })

  it('returns null when no row matches', () => {
    expect(findAgentCost(rows, { id: 'unknown', is_human: false })).toBeNull()
  })
})

describe('activityUrl', () => {
  it('filters on entity_type=agent and entity_id=the node slug', () => {
    const url = activityUrl('c1', { id: 'dev', is_human: false })
    expect(url).toBe('/api/llc/companies/c1/activity?entity_type=agent&entity_id=dev&page_size=20')
  })
})

describe('emptySlotState', () => {
  it('starts idle with no items', () => {
    expect(emptySlotState()).toEqual({ status: 'idle', items: [] })
  })
})
