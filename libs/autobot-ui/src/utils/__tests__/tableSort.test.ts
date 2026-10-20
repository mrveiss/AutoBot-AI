// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTable's uncontrolled sort order (#14778).

import { describe, it, expect } from 'vitest'
import { sortRows } from '../tableSort'

const ROWS = [{ v: 2 }, { v: null }, { v: 10 }, { v: undefined }, { v: 1 }]
const values = (rows: { v: unknown }[]) => rows.map((r) => r.v)

describe('sortRows', () => {
  it('puts nullish values last when ascending', () => {
    expect(values(sortRows(ROWS, 'v', 'asc'))).toEqual([1, 2, 10, null, undefined])
  })

  it('puts nullish values last when descending too', () => {
    // fails if the direction is applied to the null comparison (nulls would lead)
    expect(values(sortRows(ROWS, 'v', 'desc')).slice(0, 3)).toEqual([10, 2, 1])
    expect(values(sortRows(ROWS, 'v', 'desc')).slice(3).every((v) => v === null || v === undefined)).toBe(true)
  })

  it('sorts text naturally and never mutates the input', () => {
    const rows = [{ v: 'item10' }, { v: 'item2' }]
    expect(values(sortRows(rows, 'v', 'asc'))).toEqual(['item2', 'item10'])
    expect(values(rows)).toEqual(['item10', 'item2'])
  })
})
