// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab sort state, split out of useFileBrowserActions.
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k }),
}))
import { sortFileItems, useFileBrowserSort } from '../file-browser/useFileBrowserSort'

const T = (k: string) => k
const items = [
  { name: 'b.txt', path: '/b', is_dir: false, size: 5 },
  { name: 'dir', path: '/dir', is_dir: true },
  { name: 'a.txt', path: '/a', is_dir: false, size: 9 },
] as never[]

describe('sortFileItems', () => {
  it('puts directories first, then sorts by the field in either order', () => {
    expect(sortFileItems(items, 'name', 'asc', T).map((f) => f.name)).toEqual(['dir', 'a.txt', 'b.txt'])
    expect(sortFileItems(items, 'name', 'desc', T).map((f) => f.name)).toEqual(['dir', 'b.txt', 'a.txt'])
    expect(sortFileItems(items, 'size', 'asc', T).map((f) => f.name)).toEqual(['dir', 'b.txt', 'a.txt'])
  })
})

describe('useFileBrowserSort', () => {
  it('sorting the same field flips the order, a new field starts ascending', () => {
    const s = useFileBrowserSort(ref(items))
    s.sortBy('name')
    expect(s.sortOrder.value).toBe('desc')
    s.sortBy('size')
    expect([s.sortField.value, s.sortOrder.value]).toEqual(['size', 'asc'])
    expect(s.sortedFiles.value.map((f) => f.name)).toEqual(['dir', 'b.txt', 'a.txt'])
  })
})
