// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTable view config (#17562): search/filters, paging, column visibility and the two
// distinct empty states are implemented once in the primitive.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseTable, { type BaseTableColumn } from '../BaseTable.vue'
import { clampPage, filterRows, pageCountOf, pageRows } from '../../utils/tableView'

const COLUMNS: BaseTableColumn[] = [
  { key: 'name', label: 'Name', searchable: true, hideable: false },
  { key: 'role', label: 'Role', searchable: true },
  { key: 'note', label: 'Note', hidden: true },
]
const ROWS = [
  { id: 1, name: 'Bravo', role: 'web', note: 'n1' },
  { id: 2, name: 'Alpha', role: 'db', note: 'n2' },
  { id: 3, name: 'Charlie', role: 'web', note: 'n3' },
  { id: 4, name: 'Delta', role: 'cache', note: 'n4' },
  { id: 5, name: 'Echo', role: 'db', note: 'n5' },
]
const LABELS = { previous: 'Prev', next: 'Next' }

const make = (props: Record<string, unknown> = {}) =>
  mount(BaseTable, { props: { columns: COLUMNS, rows: ROWS, ...props } })
const names = (w: ReturnType<typeof make>) => w.findAll('tbody tr').map((tr) => tr.findAll('td')[0].text())

describe('tableView helpers', () => {
  it('filters by search over searchable columns only, case-insensitively', () => {
    expect(filterRows(ROWS, COLUMNS, 'WEB', undefined).map((r) => r.id)).toEqual([1, 3])
    expect(filterRows(ROWS, COLUMNS, 'n1', undefined)).toEqual([]) // `note` is not searchable
  })

  it('filters by column equality, ignoring blank values and matching any of an array', () => {
    expect(filterRows(ROWS, COLUMNS, '', { role: 'db' }).map((r) => r.id)).toEqual([2, 5])
    expect(filterRows(ROWS, COLUMNS, '', { role: '' })).toHaveLength(5)
    expect(filterRows(ROWS, COLUMNS, '', { role: ['web', 'cache'] }).map((r) => r.id)).toEqual([1, 3, 4])
    expect(filterRows(ROWS, COLUMNS, '', { role: [] })).toHaveLength(5)
  })

  it('pages with a clamped page and one page when unset', () => {
    expect(pageCountOf(5, 2)).toBe(3)
    expect(pageCountOf(0, 2)).toBe(1)
    expect(pageCountOf(5, undefined)).toBe(1)
    expect(clampPage(9, 3)).toBe(3)
    expect(clampPage(0, 3)).toBe(1)
    expect(pageRows([1, 2, 3, 4, 5], 3, 2)).toEqual([5])
    expect(pageRows([1, 2, 3], 1, undefined)).toEqual([1, 2, 3])
  })
})

describe('BaseTable view config', () => {
  it('applies search and filters', () => {
    expect(names(make({ search: 'a' }))).toEqual(['Bravo', 'Alpha', 'Charlie', 'Delta'])
    expect(names(make({ filters: { role: 'db' } }))).toEqual(['Alpha', 'Echo'])
  })

  it('shows "no data" when there are no rows, and "no matches" when a filter removed them all', () => {
    // fails if the two empty states collapse into one
    const empty = make({ rows: [], emptyTitle: 'No data', noMatchesTitle: 'No matches' })
    expect(empty.find('tbody').text()).toContain('No data')
    expect(empty.find('tbody').text()).not.toContain('No matches')
    const none = make({ search: 'zzz', emptyTitle: 'No data', noMatchesTitle: 'No matches' })
    expect(none.find('tbody').text()).toContain('No matches')
    expect(none.find('tbody').text()).not.toContain('No data')
  })

  it('offers a no-matches slot distinct from the empty slot', () => {
    const w = mount(BaseTable, {
      props: { columns: COLUMNS, rows: ROWS, search: 'zzz' },
      slots: { empty: 'EMPTY', 'no-matches': 'NOMATCH' },
    })
    expect(w.find('tbody').text()).toBe('NOMATCH')
  })

  it('pages rows, steps with the pagination bar and reports the page', async () => {
    const w = make({
      pageSize: 2,
      paginationLabels: LABELS,
      paginationLabel: 'Pages',
      paginationSummary: (p: number, n: number) => `Page ${p} of ${n}`,
    })
    expect(names(w)).toEqual(['Bravo', 'Alpha'])
    expect(w.find('nav').text()).toContain('Page 1 of 3')
    await w.findAll('nav button').find((b) => b.text() === 'Next')!.trigger('click')
    expect(names(w)).toEqual(['Charlie', 'Delta'])
    expect(w.emitted('update:page')?.[0]).toEqual([2])
  })

  it('honours a controlled page and clamps one past the end', () => {
    const w = make({ pageSize: 2, page: 9, paginationLabels: LABELS, paginationLabel: 'Pages' })
    expect(names(w)).toEqual(['Echo'])
  })

  it('returns to page 1 when the search changes', async () => {
    const w = make({ pageSize: 2, paginationLabels: LABELS, paginationLabel: 'Pages' })
    await w.findAll('nav button').find((b) => b.text() === 'Next')!.trigger('click')
    await w.setProps({ search: 'e' })
    expect(w.emitted('update:page')?.at(-1)).toEqual([1])
  })

  it('renders no pagination bar without a page size or without labels', () => {
    expect(make({ pageSize: 2 }).find('nav').exists()).toBe(false)
    expect(make({ paginationLabels: LABELS, paginationLabel: 'Pages' }).find('nav').exists()).toBe(false)
  })

  it('starts with `hidden` columns off and lets the menu turn them on and off', async () => {
    const w = make({ columnsMenuLabel: 'Columns' })
    expect(w.findAll('thead th').map((t) => t.text())).toEqual(['Name', 'Role'])
    const boxes = w.findAll('details input[type="checkbox"]')
    expect(boxes).toHaveLength(2) // `name` is hideable:false, so it is not in the menu
    await boxes[1].setValue(true)
    expect(w.findAll('thead th').map((t) => t.text())).toEqual(['Name', 'Role', 'Note'])
    expect(w.emitted('update:visibleColumns')?.[0]).toEqual([['name', 'role', 'note']])
    await boxes[0].setValue(false)
    expect(w.findAll('thead th').map((t) => t.text())).toEqual(['Name', 'Note'])
  })

  it('takes its visible columns from the app when controlled', () => {
    const w = make({ visibleColumns: ['note'] })
    expect(w.findAll('thead th').map((t) => t.text())).toEqual(['Name', 'Note'])
  })

  it('spans the empty row over the visible columns only', () => {
    const w = make({ rows: [] })
    expect(w.find('tbody td').attributes('colspan')).toBe('2')
  })

  it('renders no menu without a menu label', () => {
    expect(make().find('details').exists()).toBe(false)
  })
})
