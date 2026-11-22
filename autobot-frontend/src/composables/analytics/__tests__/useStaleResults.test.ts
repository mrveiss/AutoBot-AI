// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useStaleResults: a flag is true only when a cached route said `stale: true` (#17982).
 */
import { describe, it, expect } from 'vitest'
import { nextTick, ref } from 'vue'
import { useStaleResults } from '../useStaleResults'

describe('useStaleResults (#17982)', () => {
  it('flags a cached body that says stale: true', () => {
    const stale = useStaleResults(() => 'a')
    stale.markFromCached('duplicates', { status: 'success', stale: true })
    expect(stale.flags.duplicates).toBe(true)
    expect(stale.flags.dependencies).toBe(false)
  })

  it('a cached body that is current, or says nothing, is not flagged', () => {
    const stale = useStaleResults(() => 'a')
    stale.markFromCached('dependencies', { status: 'success', stale: false })
    expect(stale.flags.dependencies).toBe(false)
    stale.markFromCached('importTree', { status: 'success' })
    expect(stale.flags.importTree).toBe(false)
    stale.markFromCached('importTree', null)
    expect(stale.flags.importTree).toBe(false)
  })

  it('a later current body un-flags, and clear() un-flags', () => {
    const stale = useStaleResults(() => 'a')
    stale.markFromCached('duplicates', { stale: true })
    stale.markFromCached('duplicates', { stale: false })
    expect(stale.flags.duplicates).toBe(false)
    stale.markFromCached('importTree', { stale: true })
    stale.clear('importTree')
    expect(stale.flags.importTree).toBe(false)
  })

  it('selecting another source drops every flag', async () => {
    const source = ref('a')
    const stale = useStaleResults(() => source.value)
    stale.markFromCached('duplicates', { stale: true })
    stale.markFromCached('dependencies', { stale: true })
    stale.markFromCached('importTree', { stale: true })
    source.value = 'b'
    await nextTick()
    expect(stale.flags).toEqual({ duplicates: false, dependencies: false, importTree: false })
  })

  it('a cached body for a source that is no longer selected neither sets nor clears the flag', async () => {
    const source = ref('a')
    const stale = useStaleResults(() => source.value)
    source.value = 'b'
    await nextTick()
    stale.markFromCached('duplicates', { stale: true }, 'a') // a late answer for the previous source
    expect(stale.flags.duplicates).toBe(false)
    stale.markFromCached('duplicates', { stale: true }, 'b')
    stale.markFromCached('duplicates', { stale: false }, 'a')
    stale.clear('duplicates', 'a')
    expect(stale.flags.duplicates).toBe(true)
    stale.clear('duplicates', 'b')
    expect(stale.flags.duplicates).toBe(false)
  })
})
