// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Workflow Planner gate and conversion rules (#19938), pure so the screens stay thin.
 *
 * The server reports only the criteria still missing for the next status. A gate is "met" when
 * the plan already holds the status it earns, or the server evaluated its rung and listed
 * nothing for it; otherwise it is "open" (with the server's own messages) or "pending" (its rung
 * has not been evaluated yet). A pending gate is never shown as passed.
 */
import { STATUS_ORDER, type GateResponse, type Plan, type PlanStatus } from '@/composables/llc/workflowPlanTypes'

export const GATE_IDS = ['G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7'] as const
export type GateRowState = 'met' | 'open' | 'pending'
export interface GateRow {
  id: string
  state: GateRowState
  messages: string[]
}

/** The status each gate earns (the server's STATUS_LADDER). */
const EARNS: Record<string, PlanStatus> = {
  G1: 'measured',
  G2: 'measured',
  G3: 'labeled',
  G4: 'labeled',
  G5: 'approved',
  G6: 'approved',
  G7: 'approved',
}

function held(id: string, status: PlanStatus): boolean {
  const earns = EARNS[id]
  return !!earns && STATUS_ORDER.indexOf(status) >= STATUS_ORDER.indexOf(earns)
}

function stateOf(id: string, status: PlanStatus, gate: GateResponse, open: string[]): GateRowState {
  if (held(id, status)) return 'met'
  if (open.length) return 'open'
  return EARNS[id] && gate.next_status === EARNS[id] ? 'met' : 'pending'
}

/** One row per gate G1-G7, plus a row for any gate id the server reports that is not one of them. */
export function gateRows(status: PlanStatus, gate: GateResponse): GateRow[] {
  const known: readonly string[] = GATE_IDS
  const extra = gate.missing.map((m) => m.gate).filter((g) => !known.includes(g))
  return [...GATE_IDS, ...new Set(extra)].map((id) => {
    const messages = gate.missing.filter((m) => m.gate === id).map((m) => m.message)
    return { id, state: stateOf(id, status, gate, messages), messages: held(id, status) ? [] : messages }
  })
}

const APPROVAL_PRECONDITIONS: readonly string[] = ['G5', 'G6']

/**
 * The open criteria that make the server refuse approval, as reported by the last gate read. G7
 * (an owner or admin approved the preview) is the approval act itself, so it is open by design and
 * never blocks; G5 and G6 must hold first. Only what the server listed counts: a null gate or an
 * unevaluated rung yields none, so nothing is claimed passed and the server stays the final word.
 */
export function approvalBlockers(status: PlanStatus, gate: GateResponse | null): GateRow[] {
  if (!gate) return []
  return gateRows(status, gate).filter((r) => r.state === 'open' && APPROVAL_PRECONDITIONS.includes(r.id))
}

export type ConvertPhase = 'not_ready' | 'needs_preview' | 'previewed' | 'approved' | 'converted'

/** Where the plan is in preview, approve, convert: read from the stored plan, never guessed. */
export function convertPhase(plan: Plan): ConvertPhase {
  if (plan.status === 'converted') return 'converted'
  if (plan.status === 'approved') return 'approved'
  if (plan.status !== 'labeled') return 'not_ready'
  return plan.conversion?.status === 'preview' ? 'previewed' : 'needs_preview'
}

export function conversionErrors(plan: Plan): string[] {
  return [...(plan.conversion?.contract_errors ?? []), ...(plan.conversion?.preview_errors ?? [])]
}

export type ConvertFailure = 'unavailable' | 'blocked' | 'error'

/** 404: the planner switch is off or the plan is gone. 409: a gate is open (the list is read from /gate). */
export function classifyConvertError(err: unknown): ConvertFailure {
  const message = err instanceof Error ? err.message : ''
  if (/^HTTP 404\b/.test(message)) return 'unavailable'
  return /^HTTP 409\b/.test(message) ? 'blocked' : 'error'
}
