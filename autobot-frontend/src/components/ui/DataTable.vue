<template>
  <div class="data-table-container">
    <!-- Table Header with Search & Actions -->
    <div v-if="showHeader" class="table-header">
      <div class="header-left">
        <slot name="header-left">
          <h3 v-if="title">{{ title }}</h3>
        </slot>
      </div>
      <div class="header-right">
        <slot name="header-actions"></slot>
      </div>
    </div>

    <!-- Table -->
    <div
      v-if="loading || sortedData.length === 0"
      aria-live="polite"
      aria-atomic="true"
      class="sr-only"
    >
      {{ loading ? t('ui.dataTable.loading') : t('ui.dataTable.noDataAvailable') }}
    </div>
    <div class="table-wrapper">
      <table
        class="data-table"
        :aria-label="title || t('ui.dataTable.dataTable')"
        :aria-busy="loading"
      >
        <thead>
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              scope="col"
              :class="{ sortable: column.sortable }"
              @click="column.sortable ? handleSort(column.key) : null"
              :role="column.sortable ? 'columnheader' : undefined"
              :tabindex="column.sortable ? 0 : undefined"
              :aria-sort="column.sortable && sortKey === column.key ? (sortDirection === 'asc' ? 'ascending' : 'descending') : (column.sortable ? 'none' : undefined)"
              :aria-label="column.sortable ? t('ui.dataTable.sortBy', { column: column.label }) : undefined"
              @keydown.enter="column.sortable ? handleSort(column.key) : null"
              @keydown.space.prevent="column.sortable ? handleSort(column.key) : null"
            >
              {{ column.label }}
              <Icon
                v-if="column.sortable"
                :name="getSortIcon(column.key)"
                size="xs"
              />
            </th>
            <th v-if="$slots.actions" scope="col" class="actions-column">{{ t('ui.dataTable.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="loading-cell">
              <LoadingSpinner />
            </td>
          </tr>
          <tr v-else-if="sortedData.length === 0">
            <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="empty-cell">
              <EmptyState
                :icon="emptyIcon"
                :title="emptyTitle || t('ui.dataTable.noDataAvailable')"
                :message="emptyMessage || t('ui.dataTable.noItemsToDisplay')"
                compact
              />
            </td>
          </tr>
          <tr v-else v-for="(row, index) in sortedData" :key="index">
            <td v-for="column in columns" :key="column.key">
              <slot :name="`cell-${column.key}`" :row="row" :value="row[column.key]">
                {{ formatCell(row[column.key], column) }}
              </slot>
            </td>
            <td v-if="$slots.actions" class="actions-cell">
              <slot name="actions" :row="row"></slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <nav
      v-if="pagination && totalPages > 1"
      class="table-pagination"
      :aria-label="t('ui.dataTable.pagination')"
    >
      <button
        class="pagination-btn"
        :disabled="currentPage === 1"
        :aria-label="t('ui.dataTable.previousPage')"
        @click="handlePageChange(currentPage - 1)"
      >
        <Icon name="chevron-left" size="sm" />
      </button>
      <span class="pagination-info" aria-live="polite" aria-atomic="true">
        {{ t('ui.dataTable.pageOf', { current: currentPage, total: totalPages }) }}
      </span>
      <button
        class="pagination-btn"
        :disabled="currentPage === totalPages"
        :aria-label="t('ui.dataTable.nextPage')"
        @click="handlePageChange(currentPage + 1)"
      >
        <Icon name="chevron-right" size="sm" />
      </button>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyState from './EmptyState.vue'
import LoadingSpinner from './LoadingSpinner.vue'
import Icon, { type IconName } from './Icon.vue'

/**
 * Reusable Data Table Component
 *
 * Provides consistent table behavior across the application.
 * Features: sorting, pagination, custom cell rendering, actions column.
 *
 * Usage:
 * ```vue
 * <DataTable
 *   :columns="[
 *     { key: 'name', label: 'Name', sortable: true },
 *     { key: 'status', label: 'Status' }
 *   ]"
 *   :data="items"
 *   :pagination="true"
 *   :items-per-page="10"
 * >
 *   <template #cell-status="{ value }">
 *     <StatusBadge :variant="value">{{ value }}</StatusBadge>
 *   </template>
 *   <template #actions="{ row }">
 *     <button @click="edit(row)">Edit</button>
 *   </template>
 * </DataTable>
 * ```
 */

interface Column {
  key: string
  label: string
  sortable?: boolean
  format?: (value: unknown) => string
}

interface Props {
  /** Table columns configuration */
  columns: Column[]
  /** Table data rows */
  data: Record<string, unknown>[]
  /** Show table header */
  showHeader?: boolean
  /** Table title */
  title?: string
  /** Enable pagination */
  pagination?: boolean
  /** Items per page (pagination) */
  itemsPerPage?: number
  /** Loading state */
  loading?: boolean
  /** Empty state icon (IconName from Icon.vue registry) */
  emptyIcon?: IconName
  /** Empty state title */
  emptyTitle?: string
  /** Empty state message */
  emptyMessage?: string
}

const { t } = useI18n()

const props = withDefaults(defineProps<Props>(), {
  showHeader: true,
  pagination: false,
  itemsPerPage: 10,
  loading: false,
  emptyIcon: 'inbox'
})

const emit = defineEmits<{
  'page-change': [page: number]
  'sort-change': [key: string, direction: 'asc' | 'desc']
}>()

// Sorting
const sortKey = ref<string | null>(null)
const sortDirection = ref<'asc' | 'desc'>('asc')

const handleSort = (key: string) => {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDirection.value = 'asc'
  }
  emit('sort-change', key, sortDirection.value)
}

const getSortIcon = (key: string): IconName => {
  if (sortKey.value !== key) return 'sort'
  return sortDirection.value === 'asc' ? 'chevron-up' : 'chevron-down'
}

// Pagination
const currentPage = ref(1)

const totalPages = computed(() =>
  Math.ceil(props.data.length / props.itemsPerPage)
)

const handlePageChange = (page: number) => {
  currentPage.value = page
  emit('page-change', page)
}

// Data processing
const sortedData = computed(() => {
  let result = [...props.data]

  // Apply sorting
  if (sortKey.value) {
    result.sort((a, b) => {
      const aVal = a[sortKey.value!] as string | number
      const bVal = b[sortKey.value!] as string | number
      const compare = aVal < bVal ? -1 : aVal > bVal ? 1 : 0
      return sortDirection.value === 'asc' ? compare : -compare
    })
  }

  // Apply pagination
  if (props.pagination) {
    const start = (currentPage.value - 1) * props.itemsPerPage
    const end = start + props.itemsPerPage
    result = result.slice(start, end)
  }

  return result
})

const formatCell = (value: unknown, column: Column) => {
  if (column.format) {
    return column.format(value)
  }
  return value
}
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * Issue #901: Technical Precision Design
 * All colors reference CSS custom properties from design-tokens.css
 */

/* Visually hidden but accessible to screen readers */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: var(--spacing-0);
  margin: var(--spacing-neg-px);
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.data-table-container {
  background: var(--bg-card);
  border-radius: var(--radius-default);
  border: 1px solid var(--border-default);
  overflow: hidden;
}

/* Header */
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
}

.header-left h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.header-right {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

/* Table */
.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table thead {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.data-table th {
  text-align: left;
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.data-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: all var(--duration-200);
}

.data-table th.sortable:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.data-table th.sortable:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -2px;
}

.data-table th.sortable i {
  margin-left: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.data-table th.actions-column {
  text-align: right;
}

.data-table td {
  padding: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-subtle);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.data-table td.actions-cell {
  text-align: right;
}

.loading-cell,
.empty-cell {
  text-align: center;
  padding: var(--spacing-8) var(--spacing-4);
}

/* Pagination */
.table-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

/* Issue #901: Technical Precision pagination buttons */
.pagination-btn {
  padding: var(--spacing-2) var(--spacing-3);
  min-height: 44px;
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-xs);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.pagination-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-hover);
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Issue #901: Monospace for page numbers */
.pagination-info {
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}
</style>
