// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Company dashboard display shapes and the mappers from the backend rows (#9861, #11395).
 * Shared by CompanyDashboard (fetch, live events) and CompanyDashboardWidget (render).
 */
import {
  runStatusToAgentStatus,
  runStatusToRunDisplayStatus,
  type AgentDisplayStatus,
  type RunDisplayStatus,
} from '@/composables/llc/llcStatus'

export interface AgentStatus {
  id: string
  name: string
  title: string
  status: AgentDisplayStatus
  adapter_type: string
  last_heartbeat: string | null
  // #20519: the server's answer to "can this agent start a run", and why not.
  can_run?: boolean | null
  cannot_run_reason?: string | null
}

export interface PendingApproval {
  id: string
  title: string
  requested_by: string
  created_at: string
  issue_id: string | null
}

export interface BudgetInfo {
  spent: number
  total: number
  label: string
}

export interface HeartbeatRun {
  agent_id: string
  agent_name: string
  run_id: string
  status: RunDisplayStatus
  started_at: string
  duration_ms: number | null
}

export interface ActivityEvent {
  id: string
  type: string
  summary: string
  agent_name: string | null
  timestamp: string
}

/** Everything the widgets render, fetched once per company. */
export interface CompanyDashboardData {
  agents: AgentStatus[]
  approvals: PendingApproval[]
  budgets: BudgetInfo[]
  runs: HeartbeatRun[]
  activity: ActivityEvent[]
}

// Raw backend shapes (differ from the display interfaces above).
export interface RawAgentRow {
  id: string
  name: string
  title?: string | null
  adapter_type?: string | null
  can_run?: boolean | null
  cannot_run_reason?: string | null
  last_heartbeat_at: string | null
  last_run_status: string | null
}
export interface RawBudgetRow {
  agent_id: string
  budget_limit: string | number
  budget_spent: string | number
}
export interface RawRunRow {
  id: string
  agent_id: string
  status: string
  started_at: string | null
  finished_at: string | null
}

export function mapAgent(r: RawAgentRow): AgentStatus {
  return {
    id: r.id,
    name: r.name,
    title: r.title ?? '',
    status: runStatusToAgentStatus(r.last_run_status),
    adapter_type: r.adapter_type ?? '',
    last_heartbeat: r.last_heartbeat_at,
    can_run: r.can_run,
    cannot_run_reason: r.cannot_run_reason,
  }
}

export function mapBudget(r: RawBudgetRow, agentLabel?: string): BudgetInfo {
  return {
    spent: Number(r.budget_spent) || 0,
    total: Number(r.budget_limit) || 0,
    label: agentLabel ?? r.agent_id,
  }
}

export function mapRun(r: RawRunRow, agentLabel?: string): HeartbeatRun {
  const duration =
    r.started_at && r.finished_at
      ? new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()
      : null
  return {
    agent_id: r.agent_id,
    agent_name: agentLabel ?? r.agent_id,
    run_id: r.id,
    status: runStatusToRunDisplayStatus(r.status),
    started_at: r.started_at ?? '',
    duration_ms: duration,
  }
}

// Map an activity-log row (llc/services/activity_log.py — actor_*/entity_*/action/
// occurred_at) to the ActivityEvent display shape. Used by both the initial fetch
// and the live /ws/live stream so neither renders blank fields (#11395).
export function mapActivityRow(p: Record<string, unknown>): ActivityEvent {
  return {
    id: String(p.id ?? ''),
    type: String(p.action ?? p.type ?? ''),
    summary: String(p.summary ?? `${p.action ?? ''} ${p.entity_type ?? ''}`.trim()),
    agent_name: (p.actor_agent_id ?? p.actor_user_id ?? null) as string | null,
    timestamp: String(p.occurred_at ?? p.timestamp ?? ''),
  }
}
