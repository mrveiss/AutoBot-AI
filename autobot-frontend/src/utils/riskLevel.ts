// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canonical command-approval risk-level vocabulary (#14955).
 *
 * The `risk_level` field rendered by `useCommandApproval`/`ChatMessages.vue`
 * and `ApprovalRequestCard.vue` is contracted to
 * `autobot-backend/models/command_execution.py::RiskLevel` (#7258's
 * deliberate uppercase fork, kept for legacy Redis/SQLite wire
 * compatibility): exactly four uppercase values —
 * `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` — see:
 *   - `models/command_execution.py::RiskLevel` (enum definition)
 *   - `models/command_execution.py::CommandExecution.to_dict` (`.value`)
 *   - `api/agent_terminal.py` command-status response (`risk_level`)
 *
 * The wider `CommandRisk` enum (`SAFE/MODERATE/HIGH/CRITICAL/DANGEROUS/
 * FORBIDDEN`) is converted to the vocabulary above at the backend boundary
 * by `services/agent_terminal/utils.py::map_risk_to_level`. That boundary
 * must be applied at every call site that turns a `CommandRisk` into a
 * `risk_level` string FOR THE UI — #14955 found one that skipped it:
 * `services/agent_terminal/service.py::_queue_command_for_approval`'s
 * returned response (what `chat_workflow/tool_handler.py` reads into
 * `metadata["risk_level"]`) was forwarding the raw `CommandRisk.value`, e.g.
 * `"dangerous"`. Fixed to reuse the already-converted
 * `cmd_execution.risk_level`.
 *
 * That same method's internal `session.pending_approval["risk"]` is
 * deliberately NOT converted — it feeds the auto-approve rules engine
 * (`CommandApprovalManager`/`approval_memory.py`), which matches on the
 * 6-member `CommandRisk` vocabulary and would silently stop matching stored
 * rules if fed the narrower 4-member one. Only the UI-facing response is a
 * `RiskLevel`; internal approval state stays a `CommandRisk`. Do NOT widen
 * this table to accept `MODERATE`/`DANGEROUS`/`FORBIDDEN`/`SAFE` as a
 * workaround for a producer that skips the UI-response conversion — fix
 * that producer instead, the same way this one was fixed.
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
