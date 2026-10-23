// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseTable behavioral tests (#14778): the one data table for both apps,
// built to the refined-UI spec 4.6 (real <table>, th scope, numeric cells).

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { h, nextTick, reactive } from 'vue'
import tableSource from '../BaseTable.vue?raw'
import BaseTable, { type BaseTableColumn } from '../BaseTable.vue'

const COLUMNS: BaseTableColumn[] = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'count', label: 'Count', numeric: true, sortable: true },
  { key: 'note', label: 'Note', wrap: true },
]
const ROWS = [
  { id: 1, name: 'Bravo', count: 20, note: 'b' },
  { id: 2, name: 'Alpha', count: 3, note: 'a' },
  { id: 3, name: 'Charlie', count: 100, note: 'c' },
]

const make = (props: Record<string, unknown> = {}, slots: Record<string, unknown> = {}) =>
  mount(BaseTable, { props: { columns: COLUMNS, rows: ROWS, ...props }, slots: slots as never })

const bodyNames = (w: ReturnType<typeof make>) =>
  w.findAll('tbody tr').map((tr) => tr.findAll('td')[0].text())

describe('BaseTable', () => {
  it('is a real table whose headers all carry scope="col"', () => {
    // fails if headers become div grids or lose scope
    const w = make()
    expect(w.find('table').exists()).toBe(true)
    const ths = w.findAll('thead th')
    expect(ths).toHaveLength(3)
    ths.forEach((th) => expect(th.attributes('scope')).toBe('col'))
  })

  it('right-aligns numeric cells and headers, and marks them monospace-numeric', () => {
    // fails if numeric columns stop aligning right (spec 4.6)
    const w = make()
    const cell = w.findAll('tbody tr')[0].findAll('td')[1]
    expect(cell.classes()).toEqual(expect.arrayContaining(['aui-table__cell--numeric', 'aui-table__cell--right']))
    expect(w.findAll('thead th')[1].classes()).toContain('aui-table__cell--right')
  })

  it('wraps only columns flagged wrap', () => {
    const w = make()
    const cells = w.findAll('tbody tr')[0].findAll('td')
    expect(cells[0].classes()).not.toContain('aui-table__cell--wrap')
    expect(cells[2].classes()).toContain('aui-table__cell--wrap')
  })

  it('renders a caption, or an aria-label when there is none', () => {
    expect(make({ caption: 'People' }).find('caption').text()).toBe('People')
    const w = make({ ariaLabel: 'People table' })
    expect(w.find('caption').exists()).toBe(false)
    expect(w.find('table').attributes('aria-label')).toBe('People table')
  })

  it('sorts uncontrolled with aria-sort on the th, via a button inside it', async () => {
    // fails if the sort control is not a button in the th or aria-sort stops following the sort
    const w = make()
    const th = () => w.findAll('thead th')[0]
    expect(th().attributes('aria-sort')).toBe('none')
    expect(w.findAll('thead th')[2].attributes('aria-sort')).toBeUndefined()
    await th().find('button').trigger('click')
    expect(th().attributes('aria-sort')).toBe('ascending')
    expect(bodyNames(w)).toEqual(['Alpha', 'Bravo', 'Charlie'])
    await th().find('button').trigger('click')
    expect(th().attributes('aria-sort')).toBe('descending')
    expect(bodyNames(w)).toEqual(['Charlie', 'Bravo', 'Alpha'])
    expect(w.emitted('sort')).toEqual([['name', 'asc'], ['name', 'desc']])
  })

  it('sorts numbers numerically', async () => {
    const w = make()
    await w.findAll('thead th')[1].find('button').trigger('click')
    expect(w.findAll('tbody tr').map((tr) => tr.findAll('td')[1].text())).toEqual(['3', '20', '100'])
  })

  it('leaves row order to the app when sortKey is controlled', async () => {
    const w = make({ sortKey: 'name', sortOrder: 'desc' })
    expect(w.findAll('thead th')[0].attributes('aria-sort')).toBe('descending')
    expect(bodyNames(w)).toEqual(['Bravo', 'Alpha', 'Charlie'])
    await w.findAll('thead th')[0].find('button').trigger('click')
    expect(w.emitted('sort')).toEqual([['name', 'asc']])
    expect(bodyNames(w)).toEqual(['Bravo', 'Alpha', 'Charlie'])
  })

  it('shows the empty state from props, and the empty slot over it', () => {
    const w = make({ rows: [], emptyTitle: 'Nothing here' })
    expect(w.text()).toContain('Nothing here')
    expect(w.find('td[colspan="3"]').exists()).toBe(true)
    expect(make({ rows: [] }, { empty: () => h('i', 'custom') }).find('i').text()).toBe('custom')
  })

  it('shows loading instead of rows, with aria-busy and a status label', () => {
    const w = make({ loading: true, loadingLabel: 'Loading rows' })
    expect(w.find('table').attributes('aria-busy')).toBe('true')
    expect(w.find('[role="status"]').text()).toBe('Loading rows')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.text()).not.toContain('Alpha')
  })

  it('renders a per-column cell slot with the row and value', () => {
    const w = make({}, {
      'cell-name': ({ row, value }: { row: { id: number }; value: string }) => h('b', `${row.id}:${value}`),
    })
    expect(w.findAll('tbody tr')[0].find('b').text()).toBe('1:Bravo')
  })

  it('selects rows and all rows, emitting the keys', async () => {
    const w = make({ selectable: true, selectAllLabel: 'All', selectRowLabel: (n: number) => `Row ${n}` })
    const boxes = w.findAll('input[type="checkbox"]')
    expect(boxes[1].attributes('aria-label')).toBe('Row 1')
    await boxes[1].setValue(true)
    expect(w.emitted('selection-change')?.[0]).toEqual([[1]])
    await boxes[0].setValue(true)
    expect(w.emitted('selection-change')?.[1]).toEqual([[1, 2, 3]])
  })

  it('drops the keys of rows the app removed, so a later toggle never re-emits them', async () => {
    // fails if `selected` keeps stale keys when `rows` changes
    const w = make({ selectable: true })
    await w.findAll('input[type="checkbox"]')[0].setValue(true)
    await w.setProps({ rows: ROWS.filter((r) => r.id !== 2) })
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[1, 3]])
    await w.findAll('input[type="checkbox"]')[1].setValue(false)
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[3]])
  })

  it('keeps the selection when rows change but every selected row is still there', async () => {
    // contrast case: fails if the prune emits when nothing was removed
    const w = make({ selectable: true })
    await w.findAll('input[type="checkbox"]')[1].setValue(true)
    const before = w.emitted('selection-change')?.length
    await w.setProps({ rows: [...ROWS] })
    expect(w.emitted('selection-change')?.length).toBe(before)
  })

  it('drops the key of a row the app spliced out of the same array in place', async () => {
    // fails if the prune watches only the rows array reference, which splice leaves unchanged
    const rows = reactive(ROWS.map((r) => ({ ...r })))
    const w = make({ selectable: true, rows })
    await w.findAll('input[type="checkbox"]')[0].setValue(true)
    rows.splice(1, 1)
    await nextTick()
    expect(w.emitted('selection-change')?.at(-1)).toEqual([[1, 3]])
  })

  it('keeps the selection when a row is edited in place but no key goes away', async () => {
    // contrast case: fails if an in-place edit that removes no key emits a selection change
    const rows = reactive(ROWS.map((r) => ({ ...r })))
    const w = make({ selectable: true, rows })
    await w.findAll('input[type="checkbox"]')[1].setValue(true)
    const before = w.emitted('selection-change')?.length
    rows[0].note = 'edited'
    rows.push({ id: 4, name: 'Delta', count: 1, note: 'd' })
    await nextTick()
    expect(w.emitted('selection-change')?.length).toBe(before)
  })

  it('select-all on rows without the key field selects every row, never undefined', async () => {
    // fails if keysOf and row rendering stop sharing the identity-key fallback
    const rows = ROWS.map(({ id: _id, ...rest }) => rest)
    const w = make({ selectable: true, rows })
    await w.findAll('input[type="checkbox"]')[0].setValue(true)
    const keys = w.emitted('selection-change')?.at(-1)?.[0] as unknown[]
    expect(keys).toHaveLength(3)
    expect(keys.every((k) => typeof k === 'number')).toBe(true)
    expect(new Set(keys).size).toBe(3)
  })

  it('keeps the same keyless row selected after a sort reorders it', async () => {
    // fails if a keyless row is keyed by its position: the selection would jump rows on sort
    const rows = ROWS.map(({ id: _id, ...rest }) => rest)
    const w = make({ selectable: true, rows })
    await w.findAll('tbody input[type="checkbox"]')[0].setValue(true) // Bravo
    await w.find('th button').trigger('click') // sort by name: Alpha, Bravo, Charlie
    const checked = w.findAll('tbody tr').filter((tr) => (tr.find('input').element as HTMLInputElement).checked)
    expect(checked.map((tr) => tr.findAll('td')[1].text())).toEqual(['Bravo'])
  })

  it('warns when selectable is set without both checkbox labels', () => {
    // fails if a selectable table can render nameless checkboxes silently
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    make({ selectable: true })
    expect(warn.mock.calls.some((c) => String(c[0]).includes('selectAllLabel'))).toBe(true)
    warn.mockClear()
    make({ selectable: true, selectAllLabel: 'All', selectRowLabel: (n: number) => `Row ${n}` })
    expect(warn.mock.calls.some((c) => String(c[0]).includes('selectAllLabel'))).toBe(false)
    warn.mockRestore()
  })

  it('declares zebra before hover and selected, so both still win on a zebra row', () => {
    // fails if the zebra rule follows a same-specificity hover or selected rule
    const at = (sel: string) => tableSource.indexOf(sel)
    expect(at('.aui-table__row--zebra {')).toBeLessThan(at('.aui-table__row:hover {'))
    expect(at('.aui-table__row--zebra {')).toBeLessThan(at('.aui-table__row--selected {'))
  })

  it('opens a header tooltip for columns that declare one', () => {
    const w = make({ columns: [{ key: 'name', label: 'Name', tooltip: 'The name' }] })
    expect(w.find('[role="tooltip"]').text()).toBe('The name')
    expect(w.find('[role="tooltip"]').classes()).toContain('aui-tooltip__bubble--bottom')
  })

  it('scrolls horizontally in its own container', () => {
    expect(tableSource).toMatch(/\.aui-table__scroll\s*\{[^}]*overflow-x:\s*auto/)
  })

  it('uses no box-shadow and no raw colour in its source', () => {
    // fails if an elevation or a literal colour creeps into the table
    expect(tableSource).not.toMatch(/box-shadow/)
    expect(tableSource).not.toMatch(/:\s*#[0-9a-f]{3,8}\b|rgba?\(/i)
  })
})
