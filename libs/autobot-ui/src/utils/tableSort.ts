// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Row ordering for BaseTable's uncontrolled sort (#14778).

export type SortOrder = 'asc' | 'desc'

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Nullish values sort last in BOTH directions; numbers numerically; everything else as text. */
function compareValues(a: unknown, b: unknown, sign: 1 | -1): number {
  const aNil = a === null || a === undefined
  const bNil = b === null || b === undefined
  if (aNil || bNil) return Number(aNil) - Number(bNil)
  if (typeof a === 'number' && typeof b === 'number') return sign * (a - b)
  return sign * collator.compare(String(a), String(b))
}

/** A sorted copy of `rows` by `key`; the input is never mutated. */
export function sortRows<T extends Record<string, unknown>>(
  rows: readonly T[],
  key: string,
  order: SortOrder,
): T[] {
  const sign: 1 | -1 = order === 'asc' ? 1 : -1
  return [...rows].sort((x, y) => compareValues(x[key], y[key], sign))
}
