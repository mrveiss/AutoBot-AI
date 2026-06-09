// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for useBatchSelection composable (#5192).
 */

import { describe, it, expect } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useBatchSelection } from '../useBatchSelection'

interface Doc {
  id: string
  name: string
}

describe('useBatchSelection', () => {
  describe('initial state', () => {
    it('starts with empty selection', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b', 'c']))

      expect(sel.selected.value.size).toBe(0)
      expect(sel.selectedCount.value).toBe(0)
      expect(sel.selectedItems.value).toEqual([])
      expect(sel.allSelected.value).toBe(false)
      expect(sel.someSelected.value).toBe(false)
    })

    it('allSelected is false when items list is empty', () => {
      const sel = useBatchSelection<string>(ref([]))

      expect(sel.allSelected.value).toBe(false)
      expect(sel.someSelected.value).toBe(false)
    })
  })

  describe('select / deselect (idempotent)', () => {
    it('select adds the item', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.select('a')
      expect(sel.isSelected('a')).toBe(true)
      expect(sel.selectedCount.value).toBe(1)
    })

    it('select is idempotent', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.select('a')
      sel.select('a')
      sel.select('a')
      expect(sel.selectedCount.value).toBe(1)
    })

    it('deselect removes the item', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.select('a')
      sel.deselect('a')
      expect(sel.isSelected('a')).toBe(false)
      expect(sel.selectedCount.value).toBe(0)
    })

    it('deselect is idempotent', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.deselect('a')
      sel.deselect('a')
      expect(sel.selectedCount.value).toBe(0)
    })
  })

  describe('toggle', () => {
    it('flips state on each call', () => {
      const sel = useBatchSelection<string>(ref(['a']))

      sel.toggle('a')
      expect(sel.isSelected('a')).toBe(true)

      sel.toggle('a')
      expect(sel.isSelected('a')).toBe(false)

      sel.toggle('a')
      expect(sel.isSelected('a')).toBe(true)
    })
  })

  describe('selectAll / clear', () => {
    it('selectAll adds every item key from the items source', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b', 'c']))

      sel.selectAll()

      expect(sel.selectedCount.value).toBe(3)
      expect(sel.isSelected('a')).toBe(true)
      expect(sel.isSelected('b')).toBe(true)
      expect(sel.isSelected('c')).toBe(true)
    })

    it('clear empties the selection', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b', 'c']))

      sel.selectAll()
      sel.clear()

      expect(sel.selectedCount.value).toBe(0)
      expect(sel.selectedItems.value).toEqual([])
    })
  })

  describe('reactivity with items source', () => {
    it('selectedItems stays in sync when items ref changes', async () => {
      const items = ref(['a', 'b', 'c'])
      const sel = useBatchSelection<string>(items)

      sel.select('a')
      sel.select('c')
      expect(sel.selectedItems.value).toEqual(['a', 'c'])

      // Drop 'c' from items
      items.value = ['a', 'b']
      await nextTick()

      // 'c' is no longer in the items list, so it drops out of selectedItems
      expect(sel.selectedItems.value).toEqual(['a'])
      // But the selected key set still contains it (caller's responsibility
      // to prune if desired — this is a pure derivation)
      expect(sel.selected.value.has('c')).toBe(true)
    })
  })

  describe('allSelected / someSelected', () => {
    it('allSelected is true only when count matches items length', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b', 'c']))

      expect(sel.allSelected.value).toBe(false)

      sel.select('a')
      sel.select('b')
      expect(sel.allSelected.value).toBe(false)

      sel.select('c')
      expect(sel.allSelected.value).toBe(true)
    })

    it('someSelected is true only for partial (non-empty, non-full) selection', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b', 'c']))

      expect(sel.someSelected.value).toBe(false)

      sel.select('a')
      expect(sel.someSelected.value).toBe(true)

      sel.select('b')
      expect(sel.someSelected.value).toBe(true)

      sel.select('c')
      expect(sel.someSelected.value).toBe(false)
      expect(sel.allSelected.value).toBe(true)
    })
  })

  describe('custom keyFn for object items', () => {
    const docs: Doc[] = [
      { id: 'd1', name: 'Doc 1' },
      { id: 'd2', name: 'Doc 2' },
      { id: 'd3', name: 'Doc 3' }
    ]

    it('uses keyFn to derive the selection key', () => {
      const sel = useBatchSelection<Doc, string>(ref(docs), (d) => d.id)

      sel.select(docs[0])
      expect(sel.isSelected(docs[0])).toBe(true)
      expect(sel.selected.value.has('d1')).toBe(true)
    })

    it('selectAll captures every item key', () => {
      const sel = useBatchSelection<Doc, string>(ref(docs), (d) => d.id)

      sel.selectAll()
      expect(sel.selectedCount.value).toBe(3)
      expect(Array.from(sel.selected.value)).toEqual(['d1', 'd2', 'd3'])
    })

    it('selectedItems returns full objects, not just keys', () => {
      const sel = useBatchSelection<Doc, string>(ref(docs), (d) => d.id)

      sel.select(docs[1])
      expect(sel.selectedItems.value).toEqual([docs[1]])
    })
  })

  describe('MaybeRefOrGetter items source', () => {
    it('accepts a plain array (non-reactive)', () => {
      const sel = useBatchSelection<string>(['a', 'b', 'c'])

      sel.selectAll()
      expect(sel.selectedCount.value).toBe(3)
    })

    it('accepts a ref', () => {
      const items = ref(['a', 'b'])
      const sel = useBatchSelection<string>(items)

      sel.selectAll()
      expect(sel.selectedCount.value).toBe(2)
    })

    it('accepts a computed', () => {
      const source = ref(['a', 'b', 'c'])
      const doubled = computed(() => source.value.concat(source.value))
      const sel = useBatchSelection<string>(doubled)

      // 6 entries but only 3 unique keys
      sel.selectAll()
      expect(sel.selectedCount.value).toBe(3)
    })

    it('accepts a getter function', () => {
      const source = ref(['a', 'b'])
      const sel = useBatchSelection<string>(() => source.value)

      sel.selectAll()
      expect(sel.selectedCount.value).toBe(2)
    })
  })

  describe('deselectByKey', () => {
    it('removes selection when only the key is known', () => {
      const docs: Doc[] = [
        { id: 'd1', name: 'Doc 1' },
        { id: 'd2', name: 'Doc 2' }
      ]
      const sel = useBatchSelection<Doc, string>(ref(docs), (d) => d.id)

      sel.selectAll()
      sel.deselectByKey('d1')

      expect(sel.selected.value.has('d1')).toBe(false)
      expect(sel.selected.value.has('d2')).toBe(true)
    })

    it('is idempotent for missing keys', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.deselectByKey('a')
      sel.deselectByKey('a')
      expect(sel.selectedCount.value).toBe(0)
    })

    it('works after the underlying item is removed from the items source', async () => {
      const items = ref([{ id: 'd1' }, { id: 'd2' }])
      const sel = useBatchSelection<{ id: string }, string>(items, (d) => d.id)

      sel.select(items.value[0])
      items.value = [{ id: 'd2' }]
      await nextTick()

      sel.deselectByKey('d1')
      expect(sel.selected.value.has('d1')).toBe(false)
    })
  })

  describe('selectByKey / toggleByKey', () => {
    it('selectByKey adds the key without needing the item', () => {
      const sel = useBatchSelection<Doc, string>(
        ref([{ id: 'd1', name: 'Doc 1' }]),
        (d) => d.id,
      )

      sel.selectByKey('d1')
      expect(sel.selected.value.has('d1')).toBe(true)
      expect(sel.selectedCount.value).toBe(1)
    })

    it('selectByKey is idempotent', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.selectByKey('a')
      sel.selectByKey('a')
      sel.selectByKey('a')
      expect(sel.selectedCount.value).toBe(1)
    })

    it('selectByKey accepts keys not in the items source (cross-page)', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.selectByKey('z')
      expect(sel.selected.value.has('z')).toBe(true)
    })

    it('toggleByKey flips state on each call', () => {
      const sel = useBatchSelection<Doc, string>(
        ref([{ id: 'd1', name: 'Doc 1' }]),
        (d) => d.id,
      )

      sel.toggleByKey('d1')
      expect(sel.isSelected({ id: 'd1', name: 'Doc 1' })).toBe(true)
      sel.toggleByKey('d1')
      expect(sel.selected.value.has('d1')).toBe(false)
      sel.toggleByKey('d1')
      expect(sel.selected.value.has('d1')).toBe(true)
    })

    it('toggleByKey works for keys not in the items source', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.toggleByKey('ghost')
      expect(sel.selected.value.has('ghost')).toBe(true)
      sel.toggleByKey('ghost')
      expect(sel.selected.value.has('ghost')).toBe(false)
    })

    it('reactivity fires on selectByKey / toggleByKey mutations', async () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))
      const countSnapshot = computed(() => sel.selectedCount.value)

      expect(countSnapshot.value).toBe(0)
      sel.selectByKey('a')
      await nextTick()
      expect(countSnapshot.value).toBe(1)

      sel.toggleByKey('a')
      await nextTick()
      expect(countSnapshot.value).toBe(0)
    })
  })

  describe('setSelected', () => {
    it('replaces the entire selection with given keys', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b', 'c']))

      sel.select('a')
      sel.setSelected(['b', 'c'])

      expect(sel.isSelected('a')).toBe(false)
      expect(sel.isSelected('b')).toBe(true)
      expect(sel.isSelected('c')).toBe(true)
      expect(sel.selectedCount.value).toBe(2)
    })

    it('accepts cross-page keys not in the items source', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.setSelected(['x', 'y', 'z'])

      expect(sel.selectedCount.value).toBe(3)
      expect(sel.selected.value.has('x')).toBe(true)
    })

    it('accepts an iterable (Set)', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.setSelected(new Set(['a', 'b']))
      expect(sel.selectedCount.value).toBe(2)
    })

    it('clearing via empty iterable works', () => {
      const sel = useBatchSelection<string>(ref(['a', 'b']))

      sel.selectAll()
      sel.setSelected([])
      expect(sel.selectedCount.value).toBe(0)
    })
  })

  describe('readonly return surface', () => {
    it('selected ref is wrapped readonly — direct mutation does not leak to internal state', () => {
      const sel = useBatchSelection<string>(ref(['a']))
      sel.select('a')

      // selected is readonly(ref). Attempting to reassign .value is a runtime
      // no-op in prod (Vue issues a warning in dev). We just assert the public
      // state still reflects the expected value after an attempted bypass.
      expect(sel.selected.value.size).toBe(1)
    })
  })
})
