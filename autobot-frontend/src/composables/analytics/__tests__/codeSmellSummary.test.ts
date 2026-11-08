// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { buildSmellsExport, summarizeSmells } from '../codeSmellSummary'

const smell = (severity: string | undefined, smell_type: string) => ({ severity, smell_type })

describe('summarizeSmells (#20493)', () => {
  it('counts totals, severities and types from one pass', () => {
    const s = summarizeSmells([smell('high', 'a'), smell('HIGH', 'a'), smell('low', 'b'), smell(undefined, 'b')])
    expect(s.total).toBe(4)
    expect(s.bySeverity).toEqual({ critical: 0, high: 2, medium: 0, low: 2 })
    expect(s.byType.a.high).toBe(2)
    expect(s.byType.b.low).toBe(2)
  })

  it('counts an unrecognised severity as low so the severities add up to the total', () => {
    const s = summarizeSmells([smell('weird', 'a')])
    expect(Object.values(s.bySeverity).reduce((a, b) => a + b, 0)).toBe(s.total)
  })
})

describe('the export agrees with the cards (#20493)', () => {
  it('exports the same list with the same total and severity counts', () => {
    const list = [smell('high', 'a'), smell('medium', 'a'), smell('high', 'b')]
    const exported = buildSmellsExport(list)
    const cards = summarizeSmells(list)
    expect(exported.smells).toEqual(list)
    expect(exported.summary.total_smells).toBe(cards.total)
    expect(exported.smells_by_severity).toEqual(cards.bySeverity)
  })
})

describe('the export names its category (#20493)', () => {
  it('carries the file category the list was loaded for', () => {
    expect(buildSmellsExport([], 'test').file_category).toBe('test')
  })
})
