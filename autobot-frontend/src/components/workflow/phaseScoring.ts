// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Phase scoring and status/class derivation for PhaseProgressionIndicator.vue (#20658).
// completion_percentage is absent when a phase is unscored; null here, never a measured 0.

export interface ScoredPhase {
  completion_percentage: number | null
  status: string
}

export function deriveStatus(pct: number | null): string {
  if (pct === null) return 'not_scored'
  if (pct >= 95) return 'complete'
  if (pct >= 75) return 'mostly_complete'
  if (pct >= 50) return 'in_progress'
  return 'incomplete'
}

/** Mean of scored phases only; null when none are scored. */
export function averageScored(list: ScoredPhase[]): number | null {
  const scored = list.flatMap((p) => (p.completion_percentage === null ? [] : [p.completion_percentage]))
  if (scored.length === 0) return null
  return Math.round(scored.reduce((sum, v) => sum + v, 0) / scored.length)
}

const PHASE_CARD_CLASS: Record<string, string> = {
  complete: 'phase-complete',
  mostly_complete: 'phase-mostly-complete',
  in_progress: 'phase-in-progress',
  incomplete: 'phase-incomplete',
}

/** An unscored phase gets no status modifier, so it never reads as the lowest tier. */
export function getPhaseCardClass(phase: ScoredPhase): string[] {
  return ['phase-card-status', PHASE_CARD_CLASS[phase.status] ?? ''].filter(Boolean)
}

export function getStatusClass(status: string): string {
  const map: Record<string, string> = {
    complete: 'status-complete',
    mostly_complete: 'status-mostly-complete',
    in_progress: 'status-in-progress',
    incomplete: 'status-incomplete',
    promoted: 'status-complete',
    eligible: 'status-in-progress',
    blocked: 'status-incomplete',
  }
  return map[status] ?? 'status-unknown'
}

export function getProgressClass(pct: number): string {
  if (pct >= 95) return 'progress-complete'
  if (pct >= 75) return 'progress-mostly-complete'
  if (pct >= 50) return 'progress-in-progress'
  return 'progress-incomplete'
}

export function getMaturityClass(maturity: number): string {
  if (maturity >= 95) return 'maturity-production'
  if (maturity >= 80) return 'maturity-beta'
  if (maturity >= 50) return 'maturity-alpha'
  return 'maturity-pre-alpha'
}

export function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
