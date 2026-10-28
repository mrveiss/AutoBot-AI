<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseTable -- the one data table for both apps (#14778, refined-UI spec 4.6).
  A real <table> with `th scope`, inside an overflow-x:auto container so a wide
  table scrolls instead of squeezing. Token-only (--aui-table-*); no shadows.

  Columns: { key, label, align?, numeric?, monospace?, wrap?, width?, sortable?,
  tooltip?, formatter?, searchable?, hidden?, hideable? }. Numeric cells are right-aligned, monospace and
  tabular-nums; only `wrap` columns wrap. Sorting is uncontrolled (rows are
  sorted here) unless `sortKey` is passed, then the app owns the order and
  reacts to `sort`. The kit holds no text: caption/labels come from the app.

  View config, applied once here (#17562): rows -> filter (`search` over `searchable`
  columns, `filters` as column-key equality) -> sort -> page (`pageSize`, v-model:page).
  Column visibility: `hidden` columns start off; with `columnsMenuLabel` a menu lets the
  user toggle every `hideable` column (v-model:visibleColumns to own the state). Two empty
  states: no rows at all (`emptyTitle`/`emptyDescription`, slot `empty`) and rows that
  the filter removed (`noMatchesTitle`/`noMatchesDescription`, slot `no-matches`).

  Slots: caption, controls, cell-<key> ({ row, value }), actions ({ row }),
  empty, loading, footer. Header tooltips reuse BaseTooltip and open downwards.
-->
<script setup lang="ts">
import { computed, ref, useSlots, warn, watch, watchEffect } from 'vue'
import BaseTooltip from './BaseTooltip.vue'
import EmptyState from './EmptyState.vue'
import BaseTableColumnsMenu from './BaseTableColumnsMenu.vue'
import type { SemanticVariant } from '../types/semantic'
import BasePagination, { type PaginationLabels } from './BasePagination.vue'
import { sortRows, type SortOrder } from '../utils/tableSort'
import {
  cellText,
  clampPage,
  defaultVisibleKeys,
  filterRows,
  pageCountOf,
  pageRows,
  type TableFilters,
} from '../utils/tableView'

export type { SortOrder }
export type TableRow = Record<string, unknown>
export type TableRowKey = string | number
export type TableSize = 'compact' | 'comfortable'
/** A row's state, tinted from the status tokens (#19640). */
export type TableRowVariant = Extract<SemanticVariant, 'success' | 'warning' | 'error' | 'info'>

export interface BaseTableColumn {
  key: string
  label: string
  sortable?: boolean
  width?: string
  align?: 'left' | 'center' | 'right'
  /** Right-aligned, monospace, tabular-nums. */
  numeric?: boolean
  monospace?: boolean
  /** Message/description columns only; every other cell stays on one line. */
  wrap?: boolean
  /** Header tooltip text. */
  tooltip?: string
  formatter?: (value: unknown) => string
  /** `search` matches this column's displayed text. */
  searchable?: boolean
  /** Not shown until the user turns it on in the columns menu. */
  hidden?: boolean
  /** `false` keeps the column out of the menu, so it can never be hidden. */
  hideable?: boolean
}

const props = withDefaults(
  defineProps<{
    columns: BaseTableColumn[]
    rows: TableRow[]
    rowKey?: string
    /** Visible caption; also names the table for assistive tech. */
    caption?: string
    /** Accessible name when there is no caption. */
    ariaLabel?: string
    size?: TableSize
    zebra?: boolean
    loading?: boolean
    /** Announced while loading (sr-only status). */
    loadingLabel?: string
    emptyTitle?: string
    emptyDescription?: string
    /** Controlled sort: when set the app orders `rows` and handles `sort`. */
    sortKey?: string
    sortOrder?: SortOrder
    /** Requires `selectAllLabel` and `selectRowLabel`: a checkbox without a name is unusable by screen reader. */
    selectable?: boolean
    selectAllLabel?: string
    selectRowLabel?: (rowNumber: number) => string
    /** Header text of the `actions` slot column. */
    actionsLabel?: string
    /** Per-row state, e.g. a denied audit entry -> 'error'; undefined leaves the row plain. */
    rowVariant?: (row: TableRow) => TableRowVariant | undefined
    /** Case-insensitive text matched against the `searchable` columns. */
    search?: string
    /** Column key -> wanted value (or any of an array); blank values are inactive. */
    filters?: TableFilters
    /** Shown when `search`/`filters` removed every row (rows exist, none match). */
    noMatchesTitle?: string
    noMatchesDescription?: string
    /** Rows per page; unset shows every row. */
    pageSize?: number
    /** Controlled page (1-based); pair with `update:page`. */
    page?: number
    paginationLabels?: PaginationLabels
    /** Names the pagination landmark. */
    paginationLabel?: string
    /** "Page 2 of 7" text, composed by the app. */
    paginationSummary?: (page: number, pageCount: number) => string
    /** Controlled visible column keys; pair with `update:visibleColumns`. */
    visibleColumns?: string[]
    /** Renders the columns menu, named by this text. */
    columnsMenuLabel?: string
  }>(),
  {
    rowKey: 'id',
    caption: undefined,
    ariaLabel: undefined,
    size: 'comfortable',
    zebra: false,
    loading: false,
    loadingLabel: undefined,
    emptyTitle: undefined,
    emptyDescription: undefined,
    sortKey: undefined,
    sortOrder: 'asc',
    selectable: false,
    selectAllLabel: undefined,
    selectRowLabel: undefined,
    actionsLabel: undefined,
    rowVariant: undefined,
    search: undefined,
    filters: undefined,
    noMatchesTitle: undefined,
    noMatchesDescription: undefined,
    pageSize: undefined,
    page: undefined,
    paginationLabels: undefined,
    paginationLabel: undefined,
    paginationSummary: undefined,
    visibleColumns: undefined,
    columnsMenuLabel: undefined,
  },
)

const emit = defineEmits<{
  sort: [key: string, order: SortOrder]
  'selection-change': [keys: TableRowKey[]]
  'update:page': [page: number]
  'update:visibleColumns': [keys: string[]]
}>()

const slots = useSlots()
const localKey = ref('')
const localOrder = ref<SortOrder>('asc')
const selected = ref<Set<TableRowKey>>(new Set())

const controlled = computed(() => props.sortKey !== undefined)
const activeKey = computed(() => (controlled.value ? props.sortKey : localKey.value))
const activeOrder = computed(() => (controlled.value ? props.sortOrder : localOrder.value))
const localPage = ref(1)
const localVisible = ref<string[]>(defaultVisibleKeys(props.columns))

const shownColumns = computed(() => {
  const on = new Set(props.visibleColumns ?? localVisible.value)
  return props.columns.filter((c) => c.hideable === false || on.has(c.key))
})
const menuItems = computed(() =>
  props.columns
    .filter((c) => c.hideable !== false)
    .map((c) => ({ key: c.key, label: c.label, shown: shownColumns.value.some((s) => s.key === c.key) })),
)
const filteredRows = computed(() => filterRows(props.rows, props.columns, props.search, props.filters))
const sortedRows = computed(() =>
  controlled.value || !activeKey.value
    ? filteredRows.value
    : sortRows(filteredRows.value, activeKey.value, activeOrder.value),
)
const pageCount = computed(() => pageCountOf(sortedRows.value.length, props.pageSize))
const activePage = computed(() => clampPage(props.page ?? localPage.value, pageCount.value))
const shownRows = computed(() => pageRows(sortedRows.value, activePage.value, props.pageSize))
const paged = computed(() => !!props.pageSize && props.pageSize > 0 && !!props.paginationLabels && !!props.paginationLabel)
const noMatches = computed(() => props.rows.length > 0 && filteredRows.value.length === 0)
const colspan = computed(
  () => shownColumns.value.length + (props.selectable ? 1 : 0) + (slots.actions ? 1 : 0),
)
// The same key rows render with (identity fallback included), so select-all never collects undefined.
const keysOf = (rows: TableRow[]): TableRowKey[] => rows.map((r) => rowKeyOf(r))
const allSelected = computed(
  () => props.rows.length > 0 && keysOf(props.rows).every((k) => selected.value.has(k)),
)

function ariaSortOf(col: BaseTableColumn): 'ascending' | 'descending' | 'none' | undefined {
  if (!col.sortable) return undefined
  if (activeKey.value !== col.key) return 'none'
  return activeOrder.value === 'asc' ? 'ascending' : 'descending'
}

function rowClasses(row: TableRow, index: number): Record<string, boolean> {
  const variant = props.rowVariant?.(row)
  return {
    'aui-table__row--zebra': props.zebra && index % 2 === 1,
    [`aui-table__row--${variant}`]: variant !== undefined,
    'aui-table__row--selected': selected.value.has(rowKeyOf(row)),
  }
}

function arrowClasses(key: string): Record<string, boolean> {
  const on = activeKey.value === key
  return { 'aui-table__arrow--on': on, 'aui-table__arrow--asc': on && activeOrder.value === 'asc' }
}

function onSort(key: string): void {
  const order: SortOrder = activeKey.value === key && activeOrder.value === 'asc' ? 'desc' : 'asc'
  if (!controlled.value) {
    localKey.value = key
    localOrder.value = order
  }
  emit('sort', key, order)
}

function commitSelection(next: Set<TableRowKey>): void {
  selected.value = next
  emit('selection-change', Array.from(next))
}

function toggleRow(key: TableRowKey): void {
  const next = new Set(selected.value)
  if (!next.delete(key)) next.add(key)
  commitSelection(next)
}

function toggleAll(): void {
  commitSelection(allSelected.value ? new Set() : new Set(keysOf(props.rows)))
}

function alignOf(col: BaseTableColumn): 'left' | 'center' | 'right' {
  return col.align ?? (col.numeric ? 'right' : 'left')
}

function cellClasses(col: BaseTableColumn): Record<string, boolean> {
  return {
    'aui-table__cell--numeric': !!col.numeric,
    'aui-table__cell--mono': !!col.monospace,
    'aui-table__cell--wrap': !!col.wrap,
    [`aui-table__cell--${alignOf(col)}`]: true,
  }
}

function formatCell(row: TableRow, col: BaseTableColumn): string {
  return cellText(row[col.key], col.formatter)
}

function setPage(next: number): void {
  localPage.value = next
  emit('update:page', next)
}

function toggleColumn(key: string): void {
  const current = props.visibleColumns ?? localVisible.value
  const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key]
  localVisible.value = next
  emit('update:visibleColumns', next)
}

// A new search/filter starts from the first page, so the user is never left on a page that no longer exists.
watch(
  () => [props.search, props.filters],
  () => {
    if (activePage.value !== 1 || localPage.value !== 1) setPage(1)
  },
  { deep: true },
)

// A row without its `rowKey` field is keyed by its object identity, never its position:
// `rows` and the sorted `shownRows` order differ, so a positional key would select a
// different row after a sort. The keys are negative so they cannot collide with ids.
const identityKeys = new WeakMap<TableRow, number>()
let nextIdentityKey = -1

function rowKeyOf(row: TableRow): TableRowKey {
  const own = row[props.rowKey] as TableRowKey | undefined
  if (own !== undefined && own !== null) return own
  let key = identityKeys.get(row)
  if (key === undefined) {
    key = nextIdentityKey--
    identityKeys.set(row, key)
  }
  return key
}

// Rows the app removed stop being selected, so a later toggle never re-emits their keys.
// The source is the key list, not the array reference, so an in-place splice prunes too.
watch(
  () => keysOf(props.rows),
  (keys) => {
    const present = new Set(keys)
    const kept = new Set([...selected.value].filter((k) => present.has(k)))
    if (kept.size !== selected.value.size) commitSelection(kept)
  },
)

watchEffect(() => {
  if (props.selectable && (!props.selectAllLabel || !props.selectRowLabel)) {
    warn('BaseTable: `selectable` needs `selectAllLabel` and `selectRowLabel`, or its checkboxes have no accessible name.')
  }
})
</script>

<template>
  <div class="aui-table" :class="`aui-table--${size}`">
    <div v-if="$slots.controls || columnsMenuLabel" class="aui-table__controls">
      <slot name="controls" />
      <BaseTableColumnsMenu
        v-if="columnsMenuLabel && menuItems.length"
        :label="columnsMenuLabel"
        :items="menuItems"
        @toggle="toggleColumn"
      />
    </div>
    <div v-if="loading && loadingLabel" class="aui-table__sr" role="status">{{ loadingLabel }}</div>
    <div class="aui-table__scroll">
      <table class="aui-table__table" :aria-label="caption ? undefined : ariaLabel" :aria-busy="loading">
        <caption v-if="$slots.caption || caption" class="aui-table__caption">
          <slot name="caption">{{ caption }}</slot>
        </caption>
        <thead>
          <tr>
            <th v-if="selectable" scope="col" class="aui-table__check">
              <input
                type="checkbox"
                class="aui-table__checkbox"
                :checked="allSelected"
                :aria-label="selectAllLabel"
                @change="toggleAll"
              />
            </th>
            <th
              v-for="col in shownColumns"
              :key="col.key"
              scope="col"
              class="aui-table__th"
              :class="cellClasses(col)"
              :style="{ width: col.width }"
              :aria-sort="ariaSortOf(col)"
            >
              <BaseTooltip v-if="col.tooltip" :text="col.tooltip" placement="bottom">
                <template #default="{ describedby }">
                  <button
                    v-if="col.sortable"
                    type="button"
                    class="aui-table__sort"
                    :aria-describedby="describedby"
                    @click="onSort(col.key)"
                  >
                    {{ col.label }}
                    <span class="aui-table__arrow" :class="arrowClasses(col.key)" aria-hidden="true" />
                  </button>
                  <span v-else tabindex="0" :aria-describedby="describedby">{{ col.label }}</span>
                </template>
              </BaseTooltip>
              <button v-else-if="col.sortable" type="button" class="aui-table__sort" @click="onSort(col.key)">
                {{ col.label }}
                <span class="aui-table__arrow" :class="arrowClasses(col.key)" aria-hidden="true" />
              </button>
              <template v-else>{{ col.label }}</template>
            </th>
            <th v-if="$slots.actions" scope="col" class="aui-table__th aui-table__cell--right">{{ actionsLabel }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="colspan" class="aui-table__state">
              <slot name="loading">{{ loadingLabel }}</slot>
            </td>
          </tr>
          <tr v-else-if="shownRows.length === 0">
            <td :colspan="colspan" class="aui-table__state">
              <slot v-if="noMatches" name="no-matches">
                <EmptyState :title="noMatchesTitle ?? emptyTitle" :description="noMatchesDescription ?? emptyDescription" />
              </slot>
              <slot v-else name="empty">
                <EmptyState :title="emptyTitle" :description="emptyDescription" />
              </slot>
            </td>
          </tr>
          <template v-else>
            <tr
              v-for="(row, index) in shownRows"
              :key="rowKeyOf(row)"
              class="aui-table__row"
              :class="rowClasses(row, index)"
            >
              <td v-if="selectable" class="aui-table__check">
                <input
                  type="checkbox"
                  class="aui-table__checkbox"
                  :checked="selected.has(rowKeyOf(row))"
                  :aria-label="selectRowLabel?.(index + 1)"
                  @change="toggleRow(rowKeyOf(row))"
                />
              </td>
              <td v-for="col in shownColumns" :key="col.key" class="aui-table__cell" :class="cellClasses(col)">
                <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">{{ formatCell(row, col) }}</slot>
              </td>
              <td v-if="$slots.actions" class="aui-table__cell aui-table__cell--right">
                <slot name="actions" :row="row" />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <div v-if="paged || $slots.footer" class="aui-table__footer">
      <BasePagination
        v-if="paged"
        :page="activePage"
        :total-pages="pageCount"
        :labels="paginationLabels!"
        :label="paginationLabel!"
        @update:page="setPage"
      >
        <template #summary>{{ paginationSummary?.(activePage, pageCount) }}</template>
      </BasePagination>
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.aui-table {
  display: flex;
  flex-direction: column;
  width: 100%;
  font-family: var(--aui-font-sans);
  font-size: var(--aui-table-font-size);
  color: var(--aui-color-text);
  background: var(--aui-color-surface);
  border: var(--aui-table-border);
  border-radius: var(--aui-radius-md);
}

.aui-table__controls,
.aui-table__footer {
  padding: var(--aui-space-3) var(--aui-space-4);
}

.aui-table__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--aui-space-3);
  border-bottom: var(--aui-table-border);
}

.aui-table__footer { border-top: var(--aui-table-border); }

.aui-table__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.aui-table__scroll {
  overflow-x: auto;
  width: 100%;
}

.aui-table__table {
  width: 100%;
  min-width: max-content;
  border-collapse: collapse;
  font-variant-numeric: var(--aui-table-num);
}

.aui-table__caption {
  padding: var(--aui-space-3) var(--aui-table-cell-px);
  text-align: left;
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.aui-table__th {
  height: var(--aui-table-head-h);
  padding: 0 var(--aui-table-cell-px);
  background: var(--aui-table-head-bg);
  color: var(--aui-table-head-fg);
  font: var(--aui-table-head-font);
  text-transform: var(--aui-table-head-case);
  letter-spacing: var(--aui-table-head-ls);
  border-bottom: var(--aui-table-head-border);
  white-space: nowrap;
}

.aui-table__check {
  width: var(--aui-table-check-w);
  padding: 0 var(--aui-table-cell-px);
  background: var(--aui-table-head-bg);
}

tbody .aui-table__check { background: transparent; }

.aui-table__cell {
  height: var(--aui-table-row-h);
  padding: var(--aui-table-cell-py) var(--aui-table-cell-px);
  min-width: var(--aui-table-min-col);
  border-bottom: var(--aui-table-border);
  white-space: nowrap;
}

.aui-table--compact .aui-table__cell { height: auto; }

.aui-table__cell--wrap {
  white-space: normal;
  overflow-wrap: anywhere;
}

.aui-table__cell--left { text-align: left; }
.aui-table__cell--center { text-align: center; }
.aui-table__cell--right { text-align: right; }

.aui-table__cell--numeric,
.aui-table__cell--mono { font-family: var(--aui-font-mono); }

.aui-table__cell--numeric { font-variant-numeric: var(--aui-table-num); }

/* Zebra first, so hover and selection (same specificity, later) win over it. */
.aui-table__row--zebra { background: var(--aui-table-zebra-bg); }
/* Row state (#19640): a light mix of the status colour, so it reads in both themes; hover and selection still win. */
.aui-table__row--success { background: color-mix(in srgb, var(--aui-color-success) var(--aui-table-row-tint), transparent); }
.aui-table__row--warning { background: color-mix(in srgb, var(--aui-color-warning) var(--aui-table-row-tint), transparent); }
.aui-table__row--error { background: color-mix(in srgb, var(--aui-color-error) var(--aui-table-row-tint), transparent); }
.aui-table__row--info { background: color-mix(in srgb, var(--aui-color-info) var(--aui-table-row-tint), transparent); }
.aui-table__row:hover { background: var(--aui-table-row-hover); }
.aui-table__row--selected { background: var(--aui-table-row-selected); }
.aui-table__row--selected > :first-child { border-left: var(--aui-table-row-selected-edge); }

.aui-table__state { padding: var(--aui-space-4); text-align: center; }

.aui-table__sort {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  cursor: pointer;
}

.aui-table__sort:focus-visible,
.aui-table__th span[tabindex]:focus-visible,
.aui-table__checkbox:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-table__arrow {
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid currentColor;
  opacity: 0.35;
}

.aui-table__arrow--on { opacity: 1; }
.aui-table__arrow--asc { transform: rotate(180deg); }

@media (prefers-reduced-motion: no-preference) {
  .aui-table__arrow { transition: transform var(--aui-transition-fast); }
}
</style>
