// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Shared LLC status types and display mappings (GH#9909).
 *
 * Consolidates the status unions, status-dot color maps, and raw
 * run-status mappings previously duplicated across OrgTreeNode.vue,
 * CompanyTreeNode.vue, and CompanyDashboard.vue.
 *
 * No generated LLC run-status type exists under src/types or src/api, so
 * the unions below are the single source of truth for the frontend.
 */

/** Display status for an LLC agent (org-chart node / dashboard agent grid). */
export type AgentDisplayStatus = 'active' | 'idle' | 'error' | 'paused'

/** Display status for a heartbeat-run row. */
export type RunDisplayStatus = 'running' | 'done' | 'failed'

/**
 * Agent status → tailwind status-dot color.
 * Exact map shared verbatim by OrgTreeNode.vue and CompanyDashboard.vue
 * ('paused' and any unknown status fall through to gray).
 */
export function agentStatusColor(status: string): string {
  if (status === 'active') return 'bg-green-500'
  if (status === 'idle') return 'bg-yellow-400'
  if (status === 'error') return 'bg-red-500'
  return 'bg-gray-400'
}

/**
 * Company status → tailwind status-dot color (CompanyTreeNode.vue).
 * NOTE: intentionally different from agentStatusColor — companies have no
 * 'idle'/'error' states, 'paused' is yellow, and 'inactive'/unknown is gray.
 */
export function companyStatusColor(status: string): string {
  if (status === 'active') return 'bg-green-500'
  if (status === 'paused') return 'bg-yellow-400'
  return 'bg-gray-400'
}

/** Raw heartbeat-run status → agent display status. */
export function runStatusToAgentStatus(s: string | null): AgentDisplayStatus {
  if (s === 'running') return 'active'
  if (s === 'failed' || s === 'timeout' || s === 'interrupted') return 'error'
  return 'idle'
}

/** Raw heartbeat-run status → run display status ('completed' → 'done'). */
export function runStatusToRunDisplayStatus(s: string): RunDisplayStatus {
  return s === 'completed' ? 'done' : s === 'running' ? 'running' : 'failed'
}
