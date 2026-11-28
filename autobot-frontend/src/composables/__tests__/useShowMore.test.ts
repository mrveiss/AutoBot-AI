// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useShowMore (#12741): a visible-row limit per named list, grown a page at a time and reset to
 * the first page when the source (data or filter) changes.
 */
import { describe, it, expect } from 'vitest'
import { nextTick, ref } from 'vue'
import { useShowMore } from '@autobot/ui'

const rows = (n: number) => Array.from({ length: n }, (_, i) => i)

describe('useShowMore', () => {
  it('starts at one page and grows by one page per showMore', () => {
    const { visible, shown, showMore } = useShowMore(10)
    const list = rows(25)
    expect(visible('a', list)).toHaveLength(10)
    expect(shown('a', list.length)).toBe(10)
    showMore('a')
    expect(visible('a', list)).toHaveLength(20)
    showMore('a')
    expect(visible('a', list)).toHaveLength(25)
    expect(shown('a', list.length)).toBe(25)
  })

  it('keeps each key independent and honours a per-key size', () => {
    const { visible, showMore } = useShowMore(10)
    showMore('a')
    expect(visible('a', rows(50))).toHaveLength(20)
    expect(visible('b', rows(50))).toHaveLength(10)
    expect(visible('tags', rows(10), 3)).toHaveLength(3)
    showMore('tags', 3)
    expect(visible('tags', rows(10), 3)).toHaveLength(6)
  })

  it('returns an empty list for a missing source', () => {
    expect(useShowMore(5).visible('a', undefined)).toEqual([])
  })

  it('returns to the first page when the reset source changes', async () => {
    const filter = ref('all')
    const { visible, showMore } = useShowMore(10, filter)
    showMore('a')
    expect(visible('a', rows(50))).toHaveLength(20)
    filter.value = 'high'
    await nextTick()
    expect(visible('a', rows(50))).toHaveLength(10)
  })
})
