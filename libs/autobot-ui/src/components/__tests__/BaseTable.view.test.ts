// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTable view config (#17562): search/filters, paging, column visibility and the two
// distinct empty states are implemented once in the primitive.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseTable, { type BaseTableColumn } from '../BaseTable.vue'
import { clampPage, defaultVisibleKeys, filterRows, pageCountOf, pageRows, toggleAllSelection } from '../../utils/tableView'

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

describe('tableView selection and columns helpers', () => {
  it('select-all adds the scope, keeps keys outside it, and removes only the scope when all selected', () => {
    expect([...toggleAllSelection(new Set([9]), [1, 2])]).toEqual([9, 1, 2])
    expect([...toggleAllSelection(new Set([9, 1, 2]), [1, 2])]).toEqual([9])
    expect([...toggleAllSelection(new Set([1]), [])]).toEqual([1])
  })

  it('lists every column not flagged hidden as visible by default', () => {
    expect(defaultVisibleKeys([{ key: 'a' }, { key: 'b', hidden: true }, { key: 'c' }])).toEqual(['a', 'c'])
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

  it('shows a column added after mount, and starts a late `hidden` one off', async () => {
    // fails if visibility is captured once at mount
    const w = make()
    await w.setProps({
      columns: [...COLUMNS, { key: 'extra', label: 'Extra' }, { key: 'late', label: 'Late', hidden: true }],
    })
    expect(w.findAll('thead th').map((t) => t.text())).toEqual(['Name', 'Role', 'Extra'])
  })

  it('does not slice rows when no pager can render, and warns', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const w = make({ pageSize: 2 })
    expect(names(w)).toHaveLength(5)
    expect(warn.mock.calls.flat().join(' ')).toContain('pageSize')
    warn.mockRestore()
  })

  it('selects all of the filtered set only, across pages, and clears only that set', async () => {
    const w = make({
      selectable: true,
      selectAllLabel: 'All',
      selectRowLabel: (n: number) => `Row ${n}`,
      filters: { role: 'db' },
      pageSize: 1,
      paginationLabels: LABELS,
      paginationLabel: 'Pages',
    })
    const head = () => w.find('thead input[type="checkbox"]')
    await head().setValue(true)
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[2, 5]])
    expect((head().element as HTMLInputElement).checked).toBe(true)
    await head().setValue(false)
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[]])
  })

  it('does not reset the page when `filters` is re-created with the same content', async () => {
    const w = make({ pageSize: 2, page: 2, filters: { role: '' }, paginationLabels: LABELS, paginationLabel: 'Pages' })
    await w.setProps({ filters: { role: '' } })
    expect(w.emitted('update:page')).toBeUndefined()
  })

  it('labels the columns list and closes the menu on Escape', async () => {
    const w = mount(BaseTable, { props: { columns: COLUMNS, rows: ROWS, columnsMenuLabel: 'Columns' }, attachTo: document.body })
    expect(w.find('ul').attributes('role')).toBe('group')
    expect(w.find('ul').attributes('aria-label')).toBe('Columns')
    const details = w.find('details')
    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('keydown', { key: 'Escape' })
    expect((details.element as HTMLDetailsElement).open).toBe(false)
    w.unmount()
  })

  it('clamps the page when `pageSize` grows while on a later page', async () => {
    const w = make({ pageSize: 2, page: 3, paginationLabels: LABELS, paginationLabel: 'Pages', paginationSummary: (p: number, n: number) => `${p}/${n}` })
    expect(names(w)).toEqual(['Echo'])
    await w.setProps({ pageSize: 10 })
    expect(names(w)).toHaveLength(5)
    expect(w.text()).toContain('1/1')
  })

  it('shows one page over an empty table without crashing', () => {
    const w = make({ rows: [], pageSize: 2, paginationLabels: LABELS, paginationLabel: 'Pages', paginationSummary: (p: number, n: number) => `${p}/${n}` })
    expect(w.text()).toContain('1/1')
  })

  it('select-all after rows were removed never re-emits their keys', async () => {
    const w = make({ selectable: true, selectAllLabel: 'All', selectRowLabel: (n: number) => `Row ${n}` })
    const head = () => w.find('thead input[type="checkbox"]')
    await head().setValue(true)
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[1, 2, 3, 4, 5]])
    await w.setProps({ rows: ROWS.slice(0, 2) })
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[1, 2]])
    await w.setProps({ rows: ROWS.slice(0, 3) })
    expect((head().element as HTMLInputElement).checked).toBe(false)
    await head().setValue(true)
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[1, 2, 3]])
  })

  it('keeps the controls slot in its own wrapper, apart from the columns menu', () => {
    const w = mount(BaseTable, {
      props: { columns: COLUMNS, rows: ROWS, columnsMenuLabel: 'Columns' },
      slots: { controls: '<div class="mine">x</div>' },
    })
    expect(w.find('.aui-table__controls > .mine').exists()).toBe(true)
    expect(w.find('.aui-table__controls').text()).toBe('x')
    expect(w.find('.aui-table__tools').text()).toContain('Columns')
  })
})
