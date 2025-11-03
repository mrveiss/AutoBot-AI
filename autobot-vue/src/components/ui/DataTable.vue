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
    <div class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              :class="{ sortable: column.sortable }"
              @click="column.sortable ? handleSort(column.key) : null"
            >
              {{ column.label }}
              <i
                v-if="column.sortable"
                class="fas"
                :class="getSortIcon(column.key)"
              ></i>
            </th>
            <th v-if="$slots.actions" class="actions-column">Actions</th>
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
                :title="emptyTitle"
                :message="emptyMessage"
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
    <div v-if="pagination && totalPages > 1" class="table-pagination">
      <button
        class="pagination-btn"
        :disabled="currentPage === 1"
        @click="handlePageChange(currentPage - 1)"
      >
        <i class="fas fa-chevron-left"></i>
      </button>
      <span class="pagination-info">
        Page {{ currentPage }} of {{ totalPages }}
      </span>
      <button
        class="pagination-btn"
        :disabled="currentPage === totalPages"
        @click="handlePageChange(currentPage + 1)"
      >
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import EmptyState from './EmptyState.vue'
import LoadingSpinner from './LoadingSpinner.vue'

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
  format?: (value: any) => string
}

interface Props {
  /** Table columns configuration */
  columns: Column[]
  /** Table data rows */
  data: any[]
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
  /** Empty state icon */
  emptyIcon?: string
  /** Empty state title */
  emptyTitle?: string
  /** Empty state message */
  emptyMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  showHeader: true,
  pagination: false,
  itemsPerPage: 10,
  loading: false,
  emptyIcon: 'fas fa-inbox',
  emptyTitle: 'No data available',
  emptyMessage: 'There are no items to display'
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

const getSortIcon = (key: string) => {
  if (sortKey.value !== key) return 'fa-sort'
  return sortDirection.value === 'asc' ? 'fa-sort-up' : 'fa-sort-down'
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
      const aVal = a[sortKey.value!]
      const bVal = b[sortKey.value!]
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

const formatCell = (value: any, column: Column) => {
  if (column.format) {
    return column.format(value)
  }
  return value
}
</script>

<style scoped>
.data-table-container {
  background: white;
  border-radius: 0.5rem;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

/* Header */
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.header-left h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-right {
  display: flex;
  gap: 0.75rem;
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
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.data-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.data-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.data-table th.sortable:hover {
  background: #f3f4f6;
  color: #374151;
}

.data-table th.sortable i {
  margin-left: 0.5rem;
  font-size: 0.75rem;
  color: #9ca3af;
}

.data-table th.actions-column {
  text-align: right;
}

.data-table td {
  padding: 1rem;
  font-size: 0.875rem;
  color: #374151;
  border-bottom: 1px solid #f3f4f6;
}

.data-table tbody tr:hover {
  background: #f9fafb;
}

.data-table td.actions-cell {
  text-align: right;
}

.loading-cell,
.empty-cell {
  text-align: center;
  padding: 2rem 1rem;
}

/* Pagination */
.table-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid #e5e7eb;
}

.pagination-btn {
  padding: 0.5rem 0.75rem;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 0.375rem;
  color: #374151;
  cursor: pointer;
  transition: all 0.2s;
}

.pagination-btn:hover:not(:disabled) {
  background: #f9fafb;
  border-color: #9ca3af;
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-info {
  font-size: 0.875rem;
  color: #6b7280;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .data-table-container {
    background: #1f2937;
    border-color: #374151;
  }

  .table-header {
    border-bottom-color: #374151;
  }

  .header-left h3 {
    color: #f9fafb;
  }

  .data-table thead {
    background: #374151;
    border-bottom-color: #4b5563;
  }

  .data-table th {
    color: #d1d5db;
  }

  .data-table th.sortable:hover {
    background: #4b5563;
    color: #f9fafb;
  }

  .data-table td {
    color: #d1d5db;
    border-bottom-color: #374151;
  }

  .data-table tbody tr:hover {
    background: #374151;
  }

  .table-pagination {
    border-top-color: #374151;
  }

  .pagination-btn {
    background: #374151;
    border-color: #4b5563;
    color: #d1d5db;
  }

  .pagination-btn:hover:not(:disabled) {
    background: #4b5563;
    border-color: #6b7280;
  }

  .pagination-info {
    color: #9ca3af;
  }
}
</style>
