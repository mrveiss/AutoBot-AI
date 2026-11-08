// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The one place code smells are counted (#20493).
 *
 * The summary cards and the exported report both call `summarizeSmells`, so they
 * cannot disagree: the export is built from the same list and the same counter
 * the cards show.
 */

export const SMELL_SEVERITIES = ['critical', 'high', 'medium', 'low'] as const
export type SmellSeverity = (typeof SMELL_SEVERITIES)[number]

export interface CountableSmell {
  severity?: string
  smell_type?: string
}

export interface SmellSummary {
  total: number
  bySeverity: Record<SmellSeverity, number>
  byType: Record<string, Record<SmellSeverity, number>>
}

const emptySeverityCounts = (): Record<SmellSeverity, number> => ({
  critical: 0,
  high: 0,
  medium: 0,
  low: 0,
})

/** A missing or unrecognised severity counts as `low`, as the cards always did. */
const severityOf = (smell: CountableSmell): SmellSeverity => {
  const sev = (smell.severity || 'low').toLowerCase()
  return (SMELL_SEVERITIES as readonly string[]).includes(sev) ? (sev as SmellSeverity) : 'low'
}

export function summarizeSmells(smells: readonly CountableSmell[]): SmellSummary {
  const summary: SmellSummary = { total: smells.length, bySeverity: emptySeverityCounts(), byType: {} }
  for (const smell of smells) {
    const sev = severityOf(smell)
    const type = smell.smell_type || 'unknown'
    summary.bySeverity[sev]++
    summary.byType[type] ??= emptySeverityCounts()
    summary.byType[type][sev]++
  }
  return summary
}

/** The exported report: the cards' own list, counted by the cards' own function. */
export function buildSmellsExport<T extends CountableSmell>(smells: readonly T[]) {
  const summary = summarizeSmells(smells)
  return {
    summary: { total_smells: summary.total },
    smells_by_severity: summary.bySeverity,
    smells: [...smells],
  }
}
