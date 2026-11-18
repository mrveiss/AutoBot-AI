// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one data table for both apps (#14778). Each story is a visual-regression
// subject: plain, numeric columns, sortable, empty, loading, and a wide table
// that scrolls inside its container.
import type { Meta, StoryObj } from '@storybook/vue3'
import BaseTable, { type BaseTableColumn } from './BaseTable.vue'

const COLUMNS: BaseTableColumn[] = [
  { key: 'host', label: 'Host', monospace: true },
  { key: 'role', label: 'Role' },
  { key: 'note', label: 'Note', wrap: true },
]
const ROWS = [
  { id: 1, host: 'node-a', role: 'frontend', note: 'Serves the web UI.', cpu: 12.5, mem: 2048, errors: 0 },
  { id: 2, host: 'node-b', role: 'backend', note: 'API and workers; restarts nightly after the backup window closes.', cpu: 71.25, mem: 8192, errors: 14 },
  { id: 3, host: 'node-c', role: 'data', note: 'Redis and the vector store.', cpu: 33, mem: 16384, errors: 2 },
]
const NUMERIC: BaseTableColumn[] = [
  { key: 'host', label: 'Host', monospace: true, sortable: true },
  { key: 'cpu', label: 'CPU %', numeric: true, tooltip: 'Average over the last minute' },
  { key: 'mem', label: 'Memory MB', numeric: true },
  { key: 'errors', label: 'Errors', numeric: true },
]
const WIDE: BaseTableColumn[] = [
  ...NUMERIC,
  ...Array.from({ length: 10 }, (_, i) => ({ key: `col${i + 1}`, label: `Column ${i + 1}`, width: '180px' })),
]
// Each wide column has its own key (unique v-for keys) and shows the row's note.
const WIDE_ROWS = ROWS.map((r) => ({ ...r, ...Object.fromEntries(WIDE.slice(NUMERIC.length).map((c) => [c.key, r.note])) }))

const meta = {
  title: 'Kit/BaseTable',
  component: BaseTable,
  args: { columns: COLUMNS, rows: ROWS, caption: 'Hosts' },
} satisfies Meta<typeof BaseTable>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
export const Zebra: Story = { args: { zebra: true } }
export const NumericColumns: Story = { args: { columns: NUMERIC } }
export const Sortable: Story = { args: { columns: NUMERIC, caption: 'Sortable hosts' } }
export const Empty: Story = { args: { rows: [], emptyTitle: 'No hosts', emptyDescription: 'Nothing is registered yet.' } }
export const Loading: Story = { args: { loading: true, loadingLabel: 'Loading hosts' } }
export const Populated: Story = { args: { columns: NUMERIC, caption: 'Populated hosts', zebra: true } }
// Rows exist but the search removed them all: distinct copy from `Empty` (#17562).
export const NoMatches: Story = {
  args: {
    columns: [{ key: 'host', label: 'Host', searchable: true }, ...NUMERIC.slice(1)],
    search: 'zzz',
    emptyTitle: 'No hosts',
    emptyDescription: 'Nothing is registered yet.',
    noMatchesTitle: 'No matching hosts',
    noMatchesDescription: 'Change the search to see more.',
  },
}
export const Paged: Story = {
  args: {
    columns: NUMERIC,
    pageSize: 2,
    paginationLabel: 'Hosts pages',
    paginationLabels: { previous: 'Previous', next: 'Next' },
    paginationSummary: (page: number, count: number) => `Page ${page} of ${count}`,
  },
}
export const ColumnMenu: Story = {
  args: {
    columns: NUMERIC.map((c) => (c.key === 'errors' ? { ...c, hidden: true } : c)),
    columnsMenuLabel: 'Columns',
  },
}
export const Wide: Story = {
  args: { columns: WIDE, rows: WIDE_ROWS },
  render: (args) => ({
    components: { BaseTable },
    setup: () => ({ args }),
    template: '<div style="max-width:480px"><BaseTable v-bind="args" /></div>',
  }),
}
