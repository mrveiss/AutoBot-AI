<template>
  <div class="base-table-wrapper" :class="wrapperClasses">
    <!-- Table Controls (Search, Filters, Actions) -->
    <div v-if="$slots.controls" class="table-controls">
      <slot name="controls"></slot>
    </div>

    <!-- Table Container with Scroll -->
    <div class="table-container" :class="{ 'table-scrollable': scrollable }">
      <table class="base-table">
        <!-- Table Head -->
        <thead class="table-head" :class="{ 'sticky-header': stickyHeader }">
          <tr>
            <!-- Selection Column -->
            <th v-if="selectable" class="select-cell">
              <input
                type="checkbox"
                :checked="allSelected"
                @change="toggleSelectAll"
                class="checkbox-input"
                aria-label="Select all rows"
              />
            </th>

            <!-- Data Columns -->
            <th
              v-for="column in columns"
              :key="column.key"
              :class="[
                'table-header-cell',
                {
                  'sortable-header': column.sortable,
                  'numeric-header': column.numeric,
                  'monospace-header': column.monospace
                }
              ]"
              :style="{ width: column.width, textAlign: column.align || 'left' }"
              @click="column.sortable && handleSort(column.key)"
            >
              <div class="header-content">
                <span>{{ column.label }}</span>
                <span v-if="column.sortable" class="sort-indicator">
                  <svg
                    v-if="sortKey === column.key"
                    class="sort-icon"
                    :class="{ 'sort-desc': sortOrder === 'desc' }"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/>
                  </svg>
                  <svg v-else class="sort-icon sort-inactive" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/>
                  </svg>
                </span>
              </div>
            </th>

            <!-- Actions Column -->
            <th v-if="$slots.actions" class="actions-header">Actions</th>
          </tr>
        </thead>

        <!-- Table Body -->
        <tbody class="table-body">
          <!-- Empty State -->
          <tr v-if="!data || data.length === 0" class="empty-row">
            <td :colspan="totalColumns" class="empty-cell">
              <slot name="empty">
                <div class="empty-state">
                  <p class="empty-text">No data available</p>
                </div>
              </slot>
            </td>
          </tr>

          <!-- Data Rows -->
          <tr
            v-for="(row, index) in data"
            :key="row[rowKey] || index"
            class="table-row"
            :class="{
              'row-selected': selectedRows.has(row[rowKey]),
              'row-zebra': zebra && index % 2 === 1,
              'row-clickable': rowClickable
            }"
            @click="handleRowClick(row)"
          >
            <!-- Selection Cell -->
            <td v-if="selectable" class="select-cell">
              <input
                type="checkbox"
                :checked="selectedRows.has(row[rowKey])"
                @change="toggleRowSelection(row[rowKey])"
                @click.stop
                class="checkbox-input"
                :aria-label="`Select row ${index + 1}`"
              />
            </td>

            <!-- Data Cells -->
            <td
              v-for="column in columns"
              :key="column.key"
              :class="[
                'table-cell',
                {
                  'numeric-cell': column.numeric,
                  'monospace-cell': column.monospace
                }
              ]"
              :style="{ textAlign: column.align || 'left' }"
            >
              <slot :name="`cell-${column.key}`" :row="row" :value="row[column.key]">
                {{ formatCellValue(row[column.key], column) }}
              </slot>
            </td>

            <!-- Actions Cell -->
            <td v-if="$slots.actions" class="actions-cell">
              <slot name="actions" :row="row"></slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Table Footer (Pagination, Summary) -->
    <div v-if="$slots.footer" class="table-footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface TableColumn {
  key: string
  label: string
  sortable?: boolean
  width?: string
  align?: 'left' | 'center' | 'right'
  numeric?: boolean
  monospace?: boolean
  formatter?: (value: any) => string
}

interface Props {
  columns: TableColumn[]
  data: any[]
  rowKey?: string
  size?: 'compact' | 'comfortable' | 'spacious'
  variant?: 'default' | 'bordered' | 'striped'
  zebra?: boolean
  stickyHeader?: boolean
  scrollable?: boolean
  selectable?: boolean
  rowClickable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  rowKey: 'id',
  size: 'comfortable',
  variant: 'default',
  zebra: true,
  stickyHeader: true,
  scrollable: true,
  selectable: false,
  rowClickable: false
})

const emit = defineEmits<{
  'row-click': [row: any]
  'selection-change': [selectedKeys: any[]]
  sort: [key: string, order: 'asc' | 'desc']
}>()

const sortKey = ref<string>('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const selectedRows = ref<Set<any>>(new Set())

const wrapperClasses = computed(() => [
  `table-${props.variant}`,
  `table-${props.size}`
])

const totalColumns = computed(() => {
  let count = props.columns.length
  if (props.selectable) count++
  if (props.$slots.actions) count++
  return count
})

const allSelected = computed(() => {
  if (!props.data || props.data.length === 0) return false
  return props.data.every(row => selectedRows.value.has(row[props.rowKey]))
})

const handleSort = (key: string) => {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
  emit('sort', sortKey.value, sortOrder.value)
}

const toggleSelectAll = () => {
  if (allSelected.value) {
    selectedRows.value.clear()
  } else {
    props.data.forEach(row => {
      selectedRows.value.add(row[props.rowKey])
    })
  }
  emit('selection-change', Array.from(selectedRows.value))
}

const toggleRowSelection = (key: any) => {
  if (selectedRows.value.has(key)) {
    selectedRows.value.delete(key)
  } else {
    selectedRows.value.add(key)
  }
  emit('selection-change', Array.from(selectedRows.value))
}

const handleRowClick = (row: any) => {
  if (props.rowClickable) {
    emit('row-click', row)
  }
}

const formatCellValue = (value: any, column: TableColumn) => {
  if (column.formatter) {
    return column.formatter(value)
  }
  return value ?? '—'
}
</script>

<style scoped>
/* Issue #901: Technical Precision Table Design */

.base-table-wrapper {
  display: flex;
  flex-direction: column;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
}

/* Table Controls */
.table-controls {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
  background-color: var(--bg-secondary);
}

/* Table Container */
.table-container {
  width: 100%;
  overflow-x: auto;
}

.table-scrollable {
  max-height: 600px;
  overflow-y: auto;
}

/* Base Table */
.base-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-family: var(--font-sans);
}

/* Table Head */
.table-head {
  background-color: var(--bg-secondary);
}

.sticky-header {
  position: sticky;
  top: 0;
  z-index: 10;
}

.table-header-cell {
  padding: 12px 8px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  border-bottom: 2px solid var(--border-default);
  text-align: left;
  white-space: nowrap;
  user-select: none;
}

.sortable-header {
  cursor: pointer;
  transition: color 150ms ease;
}

.sortable-header:hover {
  color: var(--text-primary);
}

.header-content {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sort-indicator {
  display: flex;
  align-items: center;
}

.sort-icon {
  width: 14px;
  height: 14px;
  transition: transform 150ms ease, color 150ms ease;
  color: var(--color-info);
}

.sort-desc {
  transform: rotate(180deg);
}

.sort-inactive {
  opacity: 0.3;
  color: var(--text-muted);
}

.numeric-header,
.monospace-header {
  text-align: right;
}

/* Table Body */
.table-body {
  background-color: var(--bg-card);
}

.table-row {
  transition: background-color 150ms ease;
  border-bottom: 1px solid var(--border-subtle);
}

.table-row:hover {
  background-color: var(--bg-hover);
}

.row-selected {
  background-color: var(--color-info-bg);
}

.row-zebra {
  background-color: rgba(0, 0, 0, 0.02);
}

.row-clickable {
  cursor: pointer;
}

.table-cell {
  padding: 12px 8px;
  color: var(--text-primary);
  vertical-align: middle;
}

.numeric-cell {
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.monospace-cell {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* Selection Cells */
.select-cell {
  width: 40px;
  padding: 8px;
  text-align: center;
}

.checkbox-input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-info);
}

/* Actions */
.actions-header,
.actions-cell {
  width: 120px;
  text-align: right;
  padding-right: 16px;
}

.actions-cell {
  white-space: nowrap;
}

/* Empty State */
.empty-row {
  background-color: var(--bg-card);
}

.empty-cell {
  padding: 48px 16px;
  text-align: center;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.empty-text {
  margin: 0;
  font-size: 14px;
}

/* Table Footer */
.table-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
  background-color: var(--bg-secondary);
}

/* Size Variants */
.table-compact .table-header-cell,
.table-compact .table-cell {
  padding: 8px 8px;
}

.table-comfortable .table-header-cell,
.table-comfortable .table-cell {
  padding: 12px 8px;
}

.table-spacious .table-header-cell,
.table-spacious .table-cell {
  padding: 16px 12px;
}

/* Variant Styles */
.table-bordered .base-table {
  border: 1px solid var(--border-default);
}

.table-bordered .table-cell {
  border-right: 1px solid var(--border-subtle);
}

.table-bordered .table-cell:last-child {
  border-right: none;
}

.table-striped .table-row:nth-child(even) {
  background-color: var(--bg-secondary);
}

/* Dark Mode Adjustments */
@media (prefers-color-scheme: dark) {
  .row-zebra {
    background-color: rgba(255, 255, 255, 0.02);
  }
}
</style>
