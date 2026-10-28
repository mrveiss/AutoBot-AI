// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Row filtering, paging and column visibility for BaseTable (#17562): the pure part, so every
// table gets one behaviour and a view declares config instead of building it.

export interface ViewColumn {
  key: string
  searchable?: boolean
  hidden?: boolean
  hideable?: boolean
  formatter?: (value: unknown) => string
}

export type TableFilters = Record<string, unknown>

const blank = (v: unknown): boolean => v === undefined || v === null || v === ''

/** The text a cell shows, which is also what `search` matches against. */
export function cellText(value: unknown, formatter?: (value: unknown) => string): string {
  if (formatter) return formatter(value)
  return blank(value) ? '' : String(value)
}

function matchesFilter(value: unknown, wanted: unknown): boolean {
  if (Array.isArray(wanted)) return wanted.length === 0 || wanted.some((w) => matchesFilter(value, w))
  return blank(wanted) || String(value) === String(wanted)
}

/**
 * Rows passing every active filter (a blank value or empty array is inactive; a key is matched
 * by its raw value, as text) and containing `search` (case-insensitive) in a `searchable` column.
 */
export function filterRows<T extends Record<string, unknown>>(
  rows: readonly T[],
  columns: readonly ViewColumn[],
  search: string | undefined,
  filters: TableFilters | undefined,
): T[] {
  const needle = (search ?? '').trim().toLowerCase()
  const searchable = columns.filter((c) => c.searchable)
  const active = Object.entries(filters ?? {}).filter(([, v]) => !blank(v))
  if (!needle && active.length === 0) return rows as T[]
  return rows.filter(
    (row) =>
      active.every(([key, wanted]) => matchesFilter(row[key], wanted)) &&
      (!needle || searchable.some((c) => cellText(row[c.key], c.formatter).toLowerCase().includes(needle))),
  )
}

/** Number of pages (>= 1) for `total` rows; an unset size means one unpaged page. */
export function pageCountOf(total: number, pageSize: number | undefined): number {
  return pageSize && pageSize > 0 ? Math.max(1, Math.ceil(total / pageSize)) : 1
}

/** `page` (1-based) clamped into 1..pageCount. */
export function clampPage(page: number, pageCount: number): number {
  return Math.min(Math.max(1, Math.floor(page) || 1), pageCount)
}

/** The rows of one page; every row when `pageSize` is unset. */
export function pageRows<T>(rows: readonly T[], page: number, pageSize: number | undefined): T[] {
  if (!pageSize || pageSize <= 0) return rows as T[]
  const start = (clampPage(page, pageCountOf(rows.length, pageSize)) - 1) * pageSize
  return rows.slice(start, start + pageSize)
}

/** Keys shown by default: every column not flagged `hidden`. */
export function defaultVisibleKeys(columns: readonly ViewColumn[]): string[] {
  return columns.filter((c) => !c.hidden).map((c) => c.key)
}
