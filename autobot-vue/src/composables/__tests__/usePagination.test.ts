/**
 * Tests for usePagination Composable
 *
 * Coverage:
 * - Basic client-side pagination
 * - Navigation controls (next, prev, goToPage, etc.)
 * - Items per page configuration
 * - Show all toggle
 * - Auto-reset on data changes
 * - Server-side pagination
 * - Edge cases and error handling
 * - Helper functions (useSimplePagination, useShowAllToggle)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import {
  usePagination,
  useSimplePagination,
  useShowAllToggle,
  type PaginationOptions
} from '../usePagination'

// ========================================
// Test Data
// ========================================

interface TestItem {
  id: number
  name: string
}

const createTestData = (count: number): TestItem[] => {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    name: `Item ${i + 1}`
  }))
}

// ========================================
// Basic Pagination Tests
// ========================================

describe('usePagination - Basic Functionality', () => {
  it('should initialize with default options', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data)

    expect(pagination.currentPage.value).toBe(1)
    expect(pagination.itemsPerPage.value).toBe(10)
    expect(pagination.totalPages.value).toBe(5)
    expect(pagination.totalItems.value).toBe(50)
  })

  it('should initialize with custom options', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 25,
      initialPage: 2
    })

    expect(pagination.currentPage.value).toBe(2)
    expect(pagination.itemsPerPage.value).toBe(25)
    expect(pagination.totalPages.value).toBe(4)
  })

  it('should paginate data correctly', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.paginatedData.value).toHaveLength(10)
    expect(pagination.paginatedData.value[0].name).toBe('Item 1')
    expect(pagination.paginatedData.value[9].name).toBe('Item 10')
  })

  it('should calculate start and end indices correctly', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.startIndex.value).toBe(0)
    expect(pagination.endIndex.value).toBe(10)

    pagination.next()

    expect(pagination.startIndex.value).toBe(10)
    expect(pagination.endIndex.value).toBe(20)
  })

  it('should handle empty data', () => {
    const data = ref<TestItem[]>([])

    const pagination = usePagination(data)

    expect(pagination.paginatedData.value).toEqual([])
    expect(pagination.totalPages.value).toBe(1)
    expect(pagination.totalItems.value).toBe(0)
    expect(pagination.currentPage.value).toBe(1)
  })

  it('should handle single page data', () => {
    const data = ref(createTestData(5))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.totalPages.value).toBe(1)
    expect(pagination.paginatedData.value).toHaveLength(5)
    expect(pagination.hasNext.value).toBe(false)
    expect(pagination.hasPrev.value).toBe(false)
  })
})

// ========================================
// Navigation Tests
// ========================================

describe('usePagination - Navigation', () => {
  it('should navigate to next page', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.next()

    expect(pagination.currentPage.value).toBe(2)
    expect(pagination.paginatedData.value[0].name).toBe('Item 11')
  })

  it('should navigate to previous page', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      initialPage: 3
    })

    pagination.prev()

    expect(pagination.currentPage.value).toBe(2)
    expect(pagination.paginatedData.value[0].name).toBe('Item 11')
  })

  it('should not go beyond last page when calling next', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.goToPage(5)
    pagination.next()

    expect(pagination.currentPage.value).toBe(5)
  })

  it('should not go before first page when calling prev', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.prev()

    expect(pagination.currentPage.value).toBe(1)
  })

  it('should go to specific page', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.goToPage(7)

    expect(pagination.currentPage.value).toBe(7)
    expect(pagination.paginatedData.value[0].name).toBe('Item 61')
  })

  it('should not go to invalid page number', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    pagination.goToPage(10)  // Only 5 pages exist

    expect(pagination.currentPage.value).toBe(1)
    expect(consoleWarnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Invalid page number')
    )

    consoleWarnSpy.mockRestore()
  })

  it('should go to first page', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      initialPage: 3
    })

    pagination.goToFirst()

    expect(pagination.currentPage.value).toBe(1)
  })

  it('should go to last page', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.goToLast()

    expect(pagination.currentPage.value).toBe(5)
  })

  it('should update hasNext and hasPrev correctly', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.hasNext.value).toBe(true)
    expect(pagination.hasPrev.value).toBe(false)

    pagination.next()

    expect(pagination.hasNext.value).toBe(true)
    expect(pagination.hasPrev.value).toBe(true)

    pagination.goToLast()

    expect(pagination.hasNext.value).toBe(false)
    expect(pagination.hasPrev.value).toBe(true)
  })

  it('should update isFirstPage and isLastPage correctly', () => {
    const data = ref(createTestData(50))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.isFirstPage.value).toBe(true)
    expect(pagination.isLastPage.value).toBe(false)

    pagination.goToLast()

    expect(pagination.isFirstPage.value).toBe(false)
    expect(pagination.isLastPage.value).toBe(true)
  })
})

// ========================================
// Items Per Page Tests
// ========================================

describe('usePagination - Items Per Page', () => {
  it('should change items per page', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.totalPages.value).toBe(10)

    pagination.setItemsPerPage(25)

    expect(pagination.itemsPerPage.value).toBe(25)
    expect(pagination.totalPages.value).toBe(4)
    expect(pagination.currentPage.value).toBe(1)  // Reset to page 1
  })

  it('should reset to page 1 when changing items per page', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.goToPage(5)
    expect(pagination.currentPage.value).toBe(5)

    pagination.setItemsPerPage(20)

    expect(pagination.currentPage.value).toBe(1)
  })

  it('should not allow invalid items per page', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    pagination.setItemsPerPage(0)
    expect(pagination.itemsPerPage.value).toBe(10)  // Unchanged

    pagination.setItemsPerPage(-5)
    expect(pagination.itemsPerPage.value).toBe(10)  // Unchanged

    expect(consoleWarnSpy).toHaveBeenCalledTimes(2)

    consoleWarnSpy.mockRestore()
  })

  it('should allow Infinity for showing all items', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.setItemsPerPage(Infinity)

    expect(pagination.itemsPerPage.value).toBe(Infinity)
    expect(pagination.totalPages.value).toBe(1)
    expect(pagination.paginatedData.value).toHaveLength(100)
  })
})

// ========================================
// Show All Toggle Tests
// ========================================

describe('usePagination - Show All Toggle', () => {
  it('should toggle show all mode', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.isShowingAll.value).toBe(false)
    expect(pagination.paginatedData.value).toHaveLength(10)

    pagination.toggleShowAll()

    expect(pagination.isShowingAll.value).toBe(true)
    expect(pagination.paginatedData.value).toHaveLength(100)
  })

  it('should restore previous items per page when toggling off', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 25
    })

    pagination.toggleShowAll()
    expect(pagination.itemsPerPage.value).toBe(Infinity)

    pagination.toggleShowAll()
    expect(pagination.itemsPerPage.value).toBe(25)
  })

  it('should reset to page 1 when toggling show all', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.goToPage(5)
    pagination.toggleShowAll()

    expect(pagination.currentPage.value).toBe(1)
  })
})

// ========================================
// Auto-Reset Tests
// ========================================

describe('usePagination - Auto-Reset on Data Change', () => {
  it('should auto-reset to valid page when data shrinks', async () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      autoResetOnDataChange: true
    })

    pagination.goToPage(10)
    expect(pagination.currentPage.value).toBe(10)

    // Shrink data to 25 items (3 pages)
    data.value = createTestData(25)
    await nextTick()

    expect(pagination.currentPage.value).toBe(3)  // Clamped to max page
  })

  it('should not auto-reset when data grows', async () => {
    const data = ref(createTestData(25))

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      autoResetOnDataChange: true
    })

    pagination.goToPage(2)

    data.value = createTestData(100)
    await nextTick()

    expect(pagination.currentPage.value).toBe(2)  // Unchanged
  })

  it('should not auto-reset when disabled', async () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      autoResetOnDataChange: false
    })

    pagination.goToPage(10)

    data.value = createTestData(25)
    await nextTick()

    // Page is clamped to valid range (totalPages watch still runs)
    // autoResetOnDataChange only controls the data length watch
    expect(pagination.currentPage.value).toBe(3)  // Clamped to max page
  })
})

// ========================================
// Server-Side Pagination Tests
// ========================================

describe('usePagination - Server-Side Pagination', () => {
  it('should use server total items', () => {
    const data = ref<TestItem[]>([])

    const pagination = usePagination(data, {
      serverTotalItems: 1000,
      itemsPerPage: 20
    })

    expect(pagination.totalItems.value).toBe(1000)
    expect(pagination.totalPages.value).toBe(50)
  })

  it('should call onPageChange callback', async () => {
    const data = ref<TestItem[]>([])
    const onPageChange = vi.fn()

    const pagination = usePagination(data, {
      serverTotalItems: 1000,
      itemsPerPage: 20,
      onPageChange
    })

    pagination.next()
    await nextTick()

    expect(onPageChange).toHaveBeenCalledWith(2, 20)
  })

  it('should call onPageChange with correct params on goToPage', async () => {
    const data = ref<TestItem[]>([])
    const onPageChange = vi.fn()

    const pagination = usePagination(data, {
      serverTotalItems: 1000,
      itemsPerPage: 20,
      onPageChange
    })

    pagination.goToPage(15)
    await nextTick()

    expect(onPageChange).toHaveBeenCalledWith(15, 20)
  })

  it('should call onPageChange when items per page changes', async () => {
    const data = ref<TestItem[]>([])
    const onPageChange = vi.fn()

    const pagination = usePagination(data, {
      serverTotalItems: 1000,
      itemsPerPage: 20,
      onPageChange
    })

    pagination.setItemsPerPage(50)
    await nextTick()

    expect(onPageChange).toHaveBeenCalledWith(1, 50)
  })
})

// ========================================
// Reset Functionality Tests
// ========================================

describe('usePagination - Reset', () => {
  it('should reset to initial state', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      initialPage: 1
    })

    pagination.goToPage(5)
    pagination.setItemsPerPage(25)

    pagination.reset()

    expect(pagination.currentPage.value).toBe(1)
    expect(pagination.itemsPerPage.value).toBe(10)
  })

  it('should call onPageChange on reset', async () => {
    const data = ref(createTestData(100))
    const onPageChange = vi.fn()

    const pagination = usePagination(data, {
      itemsPerPage: 10,
      onPageChange
    })

    pagination.goToPage(5)
    onPageChange.mockClear()

    pagination.reset()
    await nextTick()

    expect(onPageChange).toHaveBeenCalledWith(1, 10)
  })
})

// ========================================
// Edge Cases Tests
// ========================================

describe('usePagination - Edge Cases', () => {
  it('should handle data with length exactly equal to items per page', () => {
    const data = ref(createTestData(10))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.totalPages.value).toBe(1)
    expect(pagination.paginatedData.value).toHaveLength(10)
  })

  it('should handle data with length one more than items per page', () => {
    const data = ref(createTestData(11))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.totalPages.value).toBe(2)

    pagination.next()
    expect(pagination.paginatedData.value).toHaveLength(1)
  })

  it('should handle single item', () => {
    const data = ref(createTestData(1))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    expect(pagination.totalPages.value).toBe(1)
    expect(pagination.paginatedData.value).toHaveLength(1)
  })

  it('should handle very large datasets', () => {
    const data = ref(createTestData(100000))

    const pagination = usePagination(data, {
      itemsPerPage: 100
    })

    expect(pagination.totalPages.value).toBe(1000)
    expect(pagination.paginatedData.value).toHaveLength(100)
  })

  it('should handle page navigation at boundaries', () => {
    const data = ref(createTestData(25))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    pagination.goToLast()
    expect(pagination.paginatedData.value).toHaveLength(5)

    pagination.next()
    expect(pagination.currentPage.value).toBe(3)

    pagination.prev()
    expect(pagination.currentPage.value).toBe(2)
  })
})

// ========================================
// Helper Functions Tests
// ========================================

describe('useSimplePagination Helper', () => {
  it('should show first N items', () => {
    const data = ref(createTestData(50))

    const firstFive = useSimplePagination(data, 5, 'first')

    expect(firstFive.value).toHaveLength(5)
    expect(firstFive.value[0].name).toBe('Item 1')
    expect(firstFive.value[4].name).toBe('Item 5')
  })

  it('should show last N items', () => {
    const data = ref(createTestData(50))

    const lastFive = useSimplePagination(data, 5, 'last')

    expect(lastFive.value).toHaveLength(5)
    expect(lastFive.value[0].name).toBe('Item 46')
    expect(lastFive.value[4].name).toBe('Item 50')
  })

  it('should handle empty array', () => {
    const data = ref<TestItem[]>([])

    const result = useSimplePagination(data, 5, 'first')

    expect(result.value).toEqual([])
  })

  it('should handle limit larger than data length', () => {
    const data = ref(createTestData(3))

    const result = useSimplePagination(data, 10, 'first')

    expect(result.value).toHaveLength(3)
  })

  it('should be reactive to data changes', async () => {
    const data = ref(createTestData(10))

    const firstThree = useSimplePagination(data, 3, 'first')

    expect(firstThree.value).toHaveLength(3)

    data.value = createTestData(50)
    await nextTick()

    expect(firstThree.value).toHaveLength(3)
    expect(firstThree.value[0].name).toBe('Item 1')
  })
})

describe('useShowAllToggle Helper', () => {
  it('should show limited items when showAll is false', () => {
    const data = ref(createTestData(50))
    const showAll = ref(false)

    const result = useShowAllToggle(data, showAll, 10)

    expect(result.value).toHaveLength(10)
  })

  it('should show all items when showAll is true', () => {
    const data = ref(createTestData(50))
    const showAll = ref(true)

    const result = useShowAllToggle(data, showAll, 10)

    expect(result.value).toHaveLength(50)
  })

  it('should toggle between limited and all', async () => {
    const data = ref(createTestData(50))
    const showAll = ref(false)

    const result = useShowAllToggle(data, showAll, 10)

    expect(result.value).toHaveLength(10)

    showAll.value = true
    await nextTick()

    expect(result.value).toHaveLength(50)

    showAll.value = false
    await nextTick()

    expect(result.value).toHaveLength(10)
  })

  it('should handle empty array', () => {
    const data = ref<TestItem[]>([])
    const showAll = ref(false)

    const result = useShowAllToggle(data, showAll, 10)

    expect(result.value).toEqual([])
  })
})

// ========================================
// Integration Tests
// ========================================

describe('usePagination - Integration Tests', () => {
  it('should handle complete pagination workflow', () => {
    const data = ref(createTestData(100))

    const pagination = usePagination(data, {
      itemsPerPage: 10
    })

    // Initial state
    expect(pagination.currentPage.value).toBe(1)
    expect(pagination.paginatedData.value).toHaveLength(10)

    // Navigate forward
    pagination.next()
    pagination.next()
    expect(pagination.currentPage.value).toBe(3)

    // Change items per page
    pagination.setItemsPerPage(25)
    expect(pagination.currentPage.value).toBe(1)
    expect(pagination.paginatedData.value).toHaveLength(25)

    // Go to specific page
    pagination.goToPage(3)
    expect(pagination.currentPage.value).toBe(3)
    expect(pagination.paginatedData.value).toHaveLength(25)

    // Toggle show all
    pagination.toggleShowAll()
    expect(pagination.paginatedData.value).toHaveLength(100)

    // Toggle back
    pagination.toggleShowAll()
    expect(pagination.itemsPerPage.value).toBe(25)

    // Reset
    pagination.reset()
    expect(pagination.currentPage.value).toBe(1)
    expect(pagination.itemsPerPage.value).toBe(10)
  })

  it('should handle filtering + pagination workflow', async () => {
    const allData = ref(createTestData(100))

    const searchQuery = ref('')

    const filteredData = computed(() => {
      if (!searchQuery.value) return allData.value
      return allData.value.filter(item =>
        item.name.toLowerCase().includes(searchQuery.value.toLowerCase())
      )
    })

    const pagination = usePagination(filteredData, {
      itemsPerPage: 10,
      autoResetOnDataChange: true
    })

    // Initial state
    expect(pagination.totalItems.value).toBe(100)
    pagination.goToPage(5)

    // Filter data
    searchQuery.value = '1'  // Matches "Item 1", "Item 10", "Item 11", etc.
    await nextTick()

    // Should auto-reset to valid page
    expect(pagination.totalItems.value).toBe(20)  // Items with '1' in name
    expect(pagination.currentPage.value).toBe(2)  // Clamped to total pages
  })
})
