// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Proves the server-side adoption of the shared @autobot/ui usePagination in
// ErrorMonitor + TracingView (#10885). Both views paginate server-side: the API
// returns one page of rows and a separate reactive total. This test locks in the
// behaviour those views depend on:
//   1. usePagination tracks a *reactive* serverTotalItems Ref, so
//      totalPages/hasNext/hasPrev stay in sync after each fetch resolves.
//   2. next/prev/goToPage re-fetch through onPageChange ONLY when navigation
//      actually changes the page (matching the prior hand-rolled guards).
//   3. Assigning currentPage.value directly (the filter-reset path) does NOT
//      trigger onPageChange, so a filter change does not double-fetch.

import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { usePagination } from '@autobot/ui'

describe('usePagination server-side reactive total (#10885)', () => {
  it('derives totalPages/hasNext from a reactive serverTotalItems ref', () => {
    const serverTotal = ref(0)
    const { totalPages, hasNext, hasPrev, currentPage } = usePagination(ref([]), {
      itemsPerPage: 20,
      serverTotalItems: serverTotal,
    })

    // Before the first fetch resolves: one empty page, no navigation.
    expect(totalPages.value).toBe(1)
    expect(hasNext.value).toBe(false)

    // Server responds with 45 items -> ceil(45 / 20) = 3 pages.
    serverTotal.value = 45
    expect(totalPages.value).toBe(3)
    expect(currentPage.value).toBe(1)
    expect(hasPrev.value).toBe(false)
    expect(hasNext.value).toBe(true)
  })

  it('re-fetches via onPageChange only when navigation changes the page', () => {
    const serverTotal = ref(45)
    const onPageChange = vi.fn()
    const { next, prev, goToPage, currentPage } = usePagination(ref([]), {
      itemsPerPage: 20,
      serverTotalItems: serverTotal,
      onPageChange,
    })

    // Already on page 1 -> prev is a no-op, no fetch (matches prevPage guard).
    prev()
    expect(currentPage.value).toBe(1)
    expect(onPageChange).not.toHaveBeenCalled()

    next()
    expect(currentPage.value).toBe(2)
    expect(onPageChange).toHaveBeenCalledTimes(1)
    expect(onPageChange).toHaveBeenLastCalledWith(2, 20)

    goToPage(3)
    expect(currentPage.value).toBe(3)
    expect(onPageChange).toHaveBeenCalledTimes(2)

    // Beyond the last page -> no-op, no extra fetch (matches nextPage guard).
    next()
    expect(currentPage.value).toBe(3)
    expect(onPageChange).toHaveBeenCalledTimes(2)
  })

  it('does not fetch when a filter reset assigns currentPage.value directly', () => {
    const serverTotal = ref(45)
    const onPageChange = vi.fn()
    const { next, currentPage } = usePagination(ref([]), {
      itemsPerPage: 20,
      serverTotalItems: serverTotal,
      onPageChange,
    })

    next()
    expect(currentPage.value).toBe(2)
    onPageChange.mockClear()

    // onFilterChange() resets to page 1 by assigning the ref, then fetches once
    // itself — the assignment must not also fire onPageChange (no double-fetch).
    currentPage.value = 1
    expect(onPageChange).not.toHaveBeenCalled()
  })
})
