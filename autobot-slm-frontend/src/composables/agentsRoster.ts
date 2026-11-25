// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { AgentOrgStatusItem, AvailableAgent } from '@/types/agents'

// #22141: GET /agent/agents/available rows, joined with the agent_org status items (stats) and the
// AI-stack status items (type) by name or id. A null stat is unmeasured, never 0 (#17514).
export interface Agent extends AvailableAgent {
  type: string | null
  tasksCompleted: number | null
  successRate: number | null
}

export interface AgentStats {
  total_agents: number
  active_agents: number
  total_tasks: number | null
  avg_success_rate: number | null
}

const ACTIVE_STATUSES = ['active', 'available', 'ready']

export function statusGroup(status: string | null): string {
  if (status === null) return 'unknown'
  return ACTIVE_STATUSES.includes(status) ? 'active' : status
}

function average(values: number[]): number | null {
  return values.length ? Math.round(values.reduce((sum, v) => sum + v, 0) / values.length) : null
}

export function summarise(rows: Agent[], total: number): AgentStats {
  const tasks = rows.map(a => a.tasksCompleted).filter((v): v is number => v !== null)
  const rates = rows.map(a => a.successRate).filter((v): v is number => v !== null)
  return {
    total_agents: total,
    active_agents: rows.filter(a => statusGroup(a.status) === 'active').length,
    total_tasks: tasks.length ? tasks.reduce((sum, v) => sum + v, 0) : null,
    avg_success_rate: average(rates),
  }
}

export function joinAgents(
  available: AvailableAgent[],
  org: AgentOrgStatusItem[],
  types: Record<string, string>,
): Agent[] {
  const byKey = new Map<string, AgentOrgStatusItem>()
  org.forEach(o => { byKey.set(o.id, o); byKey.set(o.name, o) })
  return available.map(a => {
    const o = byKey.get(a.name)
    return {
      ...a,
      type: types[a.name] ?? o?.type ?? null,
      tasksCompleted: o?.tasksCompleted ?? null,
      successRate: o?.successRate ?? null,
    }
  })
}
