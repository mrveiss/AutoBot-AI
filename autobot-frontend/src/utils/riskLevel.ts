// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canonical command-approval risk-level vocabulary (#14955).
 *
 * The single producer for the `risk_level` field rendered by
 * `useCommandApproval`/`ChatMessages.vue` and `ApprovalRequestCard.vue` is
 * `autobot-backend/models/command_execution.py::RiskLevel` (#7258's
 * deliberate uppercase fork, kept for legacy Redis/SQLite wire
 * compatibility). It serializes exactly four uppercase values —
 * `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` — see:
 *   - `models/command_execution.py::RiskLevel` (enum definition)
 *   - `models/command_execution.py::CommandExecution.to_dict` (`.value`)
 *   - `api/agent_terminal.py` command-status response (`risk_level`)
 *
 * The wider `CommandRisk` enum (`SAFE/MODERATE/HIGH/CRITICAL/DANGEROUS/
 * FORBIDDEN`) never reaches the frontend directly — it is converted to the
 * vocabulary above at the backend boundary by
 * `services/agent_terminal/utils.py::map_risk_to_level` before a command
 * ever produces a `risk_level` string for the UI. Do NOT widen this table
 * to accept `MODERATE`/`DANGEROUS`/`FORBIDDEN`; that would quietly accept a
 * non-canonical vocabulary the backend never emits at this call site.
 */

export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical'

const RISK_SEVERITY_BY_LEVEL: Record<string, RiskSeverity> = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical'
}

/**
 * Normalize a producer-emitted risk level (e.g. "CRITICAL") to its
 * canonical severity bucket. Returns `null` for anything outside the
 * canonical vocabulary so callers apply their own "unclassified" default
 * instead of a value silently falling through to the wrong bucket.
 */
export function getRiskSeverity(riskLevel: string | null | undefined): RiskSeverity | null {
  if (!riskLevel) return null
  return RISK_SEVERITY_BY_LEVEL[riskLevel.toUpperCase()] ?? null
}
