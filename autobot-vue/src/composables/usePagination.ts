/**
 * Pagination Composable
 *
 * Centralized pagination logic to eliminate duplicate pagination patterns across components.
 * Supports client-side array slicing, server-side pagination, and various pagination modes.
 *
 * Features:
 * - Client-side array pagination with automatic slicing
 * - Server-side pagination metadata tracking
 * - Configurable items per page
 * - Page navigation (next, prev, first, last, goToPage)
 * - Auto-reset on data source changes
 * - "Show all" mode support
 * - Total pages and current page tracking
 * - TypeScript type safety
 *
 * Usage:
 * ```typescript
 * import { usePagination } from '@/composables/usePagination'
 *
 * const documents = ref([...100 items...])
 *
 * const {
 *   paginatedData,
 *   currentPage,
 *   totalPages,
 *   hasNext,
 *   hasPrev,
 *   next,
 *   prev,
 *   goToPage
 * } = usePagination(documents, {
 *   itemsPerPage: 20,
 *   autoResetOnDataChange: true
 * })
 *
 * // In template
 * <div v-for="item in paginatedData" :key="item.id">{{ item }}</div>
 * <button @click="prev" :disabled="!hasPrev">Previous</button>
 * <span>Page {{ currentPage }} of {{ totalPages }}</span>
 * <button @click="next" :disabled="!hasNext">Next</button>
 * ```
 */

import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for usePagination
const logger = createLogger('usePagination')

// ========================================
// Types & Interfaces
// ========================================

export interface PaginationOptions {
  /**
   * Number of items per page (default: 10)
   * Set to Infinity to show all items
   */
  itemsPerPage?: number

  /**
   * Initial page number (default: 1)
   */
  initialPage?: number

  /**
   * Auto-reset to page 1 when data source changes (default: true)
   */
  autoResetOnDataChange?: boolean

  /**
   * For server-side pagination: total number of items
   * If provided, switches to server-side pagination mode
   */
  serverTotalItems?: number

  /**
   * For server-side pagination: current page data
   * Used instead of slicing the data array
   */
  serverPageData?: any[]

  /**
   * Callback when page changes (for server-side pagination)
   * @param page - New page number
   * @param itemsPerPage - Items per page
   */
  onPageChange?: (page: number, itemsPerPage: number) => void | Promise<void>
}

export interface UsePaginationReturn<T> {
  /**
   * Paginated data (current page items)
   */
  paginatedData: ComputedRef<T[]>

  /**
   * Current page number (1-indexed)
   */
  currentPage: Ref<number>

  /**
   * Total number of pages
   */
  totalPages: ComputedRef<number>

  /**
   * Items per page
   */
  itemsPerPage: Ref<number>

  /**
   * Total number of items
   */
  totalItems: ComputedRef<number>

  /**
   * Has next page
   */
  hasNext: ComputedRef<boolean>

  /**
   * Has previous page
   */
  hasPrev: ComputedRef<boolean>

  /**
   * Is on first page
   */
  isFirstPage: ComputedRef<boolean>

  /**
   * Is on last page
   */
  isLastPage: ComputedRef<boolean>

  /**
   * Start index of current page items (0-indexed)
   */
  startIndex: ComputedRef<number>

  /**
   * End index of current page items (0-indexed, exclusive)
   */
  endIndex: ComputedRef<number>

  /**
   * Go to next page
   */
  next: () => void

  /**
   * Go to previous page
   */
  prev: () => void

  /**
   * Go to specific page
   * @param page - Page number (1-indexed)
   */
  goToPage: (page: number) => void

  /**
   * Go to first page
   */
  goToFirst: () => void

  /**
   * Go to last page
   */
  goToLast: () => void

  /**
   * Reset to initial state
   */
  reset: () => void

  /**
   * Set items per page
   * @param count - Number of items per page (use Infinity to show all)
   */
  setItemsPerPage: (count: number) => void

  /**
   * Toggle "show all" mode
   */
  toggleShowAll: () => void

  /**
   * Is showing all items (no pagination)
   */
  isShowingAll: ComputedRef<boolean>
}

// ========================================
// Main Composable
// ========================================

/**
 * Create pagination state and controls
 *
 * @param data - Reactive data array to paginate (for client-side pagination)
 * @param options - Pagination configuration
 * @returns Pagination state and methods
 *
 * @example Client-side pagination
 * ```typescript
 * const items = ref([...100 items...])
 * const pagination = usePagination(items, { itemsPerPage: 20 })
 * ```
 *
 * @example Server-side pagination
 * ```typescript
 * const pagination = usePagination(ref([]), {
 *   serverTotalItems: 1000,
 *   itemsPerPage: 20,
 *   onPageChange: async (page, perPage) => {
 *     const data = await fetchPage(page, perPage)
 *     pagination.paginatedData.value = data
 *   }
 * })
 * ```
 */
export function usePagination<T = any>(
  data: Ref<T[]>,
  options: PaginationOptions = {}
): UsePaginationReturn<T> {
  const {
    itemsPerPage: initialItemsPerPage = 10,
    initialPage = 1,
    autoResetOnDataChange = true,
    serverTotalItems = null,
    serverPageData = null,
    onPageChange
  } = options

  // State
  const currentPage = ref<number>(initialPage)
  const itemsPerPage = ref<number>(initialItemsPerPage)
  const previousItemsPerPage = ref<number>(initialItemsPerPage)

  // Is server-side pagination mode
  const isServerSide = serverTotalItems !== null

  // Computed: Total items
  const totalItems = computed(() => {
    if (isServerSide) {
      return serverTotalItems || 0
    }
    return data.value?.length || 0
  })

  // Computed: Total pages
  const totalPages = computed(() => {
    if (itemsPerPage.value === Infinity) return 1
    if (totalItems.value === 0) return 1
    return Math.ceil(totalItems.value / itemsPerPage.value)
  })

  // Computed: Start and end indices
  const startIndex = computed(() => {
    if (itemsPerPage.value === Infinity) return 0
    return (currentPage.value - 1) * itemsPerPage.value
  })

  const endIndex = computed(() => {
    if (itemsPerPage.value === Infinity) return totalItems.value
    return Math.min(startIndex.value + itemsPerPage.value, totalItems.value)
  })

  // Computed: Paginated data
  const paginatedData = computed(() => {
    // Server-side: use provided page data
    if (isServerSide && serverPageData) {
      return serverPageData
    }

    // Client-side: slice the data array
    if (!data.value) return []

    if (itemsPerPage.value === Infinity) {
      return data.value
    }

    return data.value.slice(startIndex.value, endIndex.value)
  })

  // Computed: Navigation state
  const hasNext = computed(() => currentPage.value < totalPages.value)
  const hasPrev = computed(() => currentPage.value > 1)
  const isFirstPage = computed(() => currentPage.value === 1)
  const isLastPage = computed(() => currentPage.value >= totalPages.value)
  const isShowingAll = computed(() => itemsPerPage.value === Infinity)

  /**
   * Ensure current page is within valid range
   */
  const ensureValidPage = (): void => {
    if (currentPage.value < 1) {
      currentPage.value = 1
    } else if (currentPage.value > totalPages.value && totalPages.value > 0) {
      currentPage.value = totalPages.value
    }
  }

  /**
   * Trigger page change callback
   */
  const triggerPageChange = async (): Promise<void> => {
    if (onPageChange) {
      await onPageChange(currentPage.value, itemsPerPage.value)
    }
  }

  /**
   * Go to next page
   */
  const next = (): void => {
    if (hasNext.value) {
      currentPage.value++
      triggerPageChange()
    }
  }

  /**
   * Go to previous page
   */
  const prev = (): void => {
    if (hasPrev.value) {
      currentPage.value--
      triggerPageChange()
    }
  }

  /**
   * Go to specific page
   */
  const goToPage = (page: number): void => {
    if (page >= 1 && page <= totalPages.value) {
      currentPage.value = page
      triggerPageChange()
    } else {
      logger.warn(`[usePagination] Invalid page number: ${page}. Must be between 1 and ${totalPages.value}`)
    }
  }

  /**
   * Go to first page
   */
  const goToFirst = (): void => {
    if (currentPage.value !== 1) {
      currentPage.value = 1
      triggerPageChange()
    }
  }

  /**
   * Go to last page
   */
  const goToLast = (): void => {
    if (currentPage.value !== totalPages.value) {
      currentPage.value = totalPages.value
      triggerPageChange()
    }
  }

  /**
   * Reset to initial state
   */
  const reset = (): void => {
    currentPage.value = initialPage
    itemsPerPage.value = initialItemsPerPage
    previousItemsPerPage.value = initialItemsPerPage
    triggerPageChange()
  }

  /**
   * Set items per page
   */
  const setItemsPerPage = (count: number): void => {
    if (count <= 0 && count !== Infinity) {
      logger.warn('[usePagination] itemsPerPage must be positive or Infinity')
      return
    }

    previousItemsPerPage.value = itemsPerPage.value
    itemsPerPage.value = count

    // Reset to page 1 when changing items per page
    currentPage.value = 1
    triggerPageChange()
  }

  /**
   * Toggle "show all" mode
   */
  const toggleShowAll = (): void => {
    if (isShowingAll.value) {
      // Restore previous items per page
      itemsPerPage.value = previousItemsPerPage.value
    } else {
      // Save current items per page and show all
      previousItemsPerPage.value = itemsPerPage.value
      itemsPerPage.value = Infinity
    }
    currentPage.value = 1
    triggerPageChange()
  }

  // Watch: Auto-reset on data change
  if (autoResetOnDataChange && !isServerSide) {
    watch(
      () => data.value?.length,
      (newLength, oldLength) => {
        if (newLength !== oldLength) {
          // Only reset if we're beyond the valid range
          ensureValidPage()
        }
      }
    )
  }

  // Watch: Ensure valid page when totalPages changes
  watch(totalPages, () => {
    ensureValidPage()
  })

  return {
    paginatedData,
    currentPage,
    totalPages,
    itemsPerPage,
    totalItems,
    hasNext,
    hasPrev,
    isFirstPage,
    isLastPage,
    startIndex,
    endIndex,
    next,
    prev,
    goToPage,
    goToFirst,
    goToLast,
    reset,
    setItemsPerPage,
    toggleShowAll,
    isShowingAll
  }
}

// ========================================
// Helper: Simple Pagination (for hardcoded limits)
// ========================================

/**
 * Simple helper for showing first/last N items
 *
 * @param data - Data array
 * @param limit - Number of items to show
 * @param mode - 'first' or 'last' (default: 'first')
 * @returns Limited data array
 *
 * @example
 * ```typescript
 * // Show first 5 items
 * const firstFive = useSimplePagination(items, 5, 'first')
 *
 * // Show last 5 items
 * const lastFive = useSimplePagination(items, 5, 'last')
 * ```
 */
export function useSimplePagination<T>(
  data: Ref<T[]>,
  limit: number,
  mode: 'first' | 'last' = 'first'
): ComputedRef<T[]> {
  return computed(() => {
    if (!data.value || data.value.length === 0) return []

    if (mode === 'last') {
      return data.value.slice(-limit)
    }

    return data.value.slice(0, limit)
  })
}

/**
 * Helper for "show all" toggle pattern
 *
 * @param data - Data array
 * @param showAll - Ref controlling show all state
 * @param limit - Number of items when not showing all
 * @returns Limited or full data array
 *
 * @example
 * ```typescript
 * const showAllProblems = ref(false)
 * const visibleProblems = useShowAllToggle(problems, showAllProblems, 10)
 *
 * // In template
 * <div v-for="problem in visibleProblems" :key="problem.id">...</div>
 * <button @click="showAllProblems = !showAllProblems">
 *   {{ showAllProblems ? 'Show Less' : 'Show All' }}
 * </button>
 * ```
 */
export function useShowAllToggle<T>(
  data: Ref<T[]>,
  showAll: Ref<boolean>,
  limit: number
): ComputedRef<T[]> {
  return computed(() => {
    if (!data.value || data.value.length === 0) return []

    if (showAll.value) {
      return data.value
    }

    return data.value.slice(0, limit)
  })
}
