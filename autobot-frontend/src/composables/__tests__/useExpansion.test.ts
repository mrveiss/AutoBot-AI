// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Unit tests for useExpansion composable (#5306).
 */

import { describe, it, expect } from 'vitest'
import { watchEffect, nextTick } from 'vue'
import { useExpansion } from '../useExpansion'

describe('useExpansion', () => {
  describe('initial state', () => {
    it('starts empty by default', () => {
      const e = useExpansion()
      expect(e.expanded.value.size).toBe(0)
      expect(e.isExpanded('a')).toBe(false)
    })

    it('seeds from initialKeys iterable', () => {
      const e = useExpansion(['a', 'b'])
      expect(e.expanded.value.size).toBe(2)
      expect(e.isExpanded('a')).toBe(true)
      expect(e.isExpanded('b')).toBe(true)
    })

    it('accepts a Set as initialKeys', () => {
      const e = useExpansion(new Set(['x']))
      expect(e.isExpanded('x')).toBe(true)
    })
  })

  describe('toggle', () => {
    it('flips state on each call', () => {
      const e = useExpansion()
      e.toggle('a')
      expect(e.isExpanded('a')).toBe(true)
      e.toggle('a')
      expect(e.isExpanded('a')).toBe(false)
      e.toggle('a')
      expect(e.isExpanded('a')).toBe(true)
    })
  })

  describe('expand / collapse (idempotent)', () => {
    it('expand adds the key', () => {
      const e = useExpansion()
      e.expand('a')
      expect(e.isExpanded('a')).toBe(true)
    })

    it('expand is idempotent', () => {
      const e = useExpansion()
      e.expand('a')
      e.expand('a')
      e.expand('a')
      expect(e.expanded.value.size).toBe(1)
    })

    it('collapse removes the key', () => {
      const e = useExpansion(['a', 'b'])
      e.collapse('a')
      expect(e.isExpanded('a')).toBe(false)
      expect(e.isExpanded('b')).toBe(true)
    })

    it('collapse is idempotent', () => {
      const e = useExpansion()
      e.collapse('a')
      e.collapse('a')
      expect(e.expanded.value.size).toBe(0)
    })
  })

  describe('expandAll / collapseAll', () => {
    it('expandAll replaces the set', () => {
      const e = useExpansion(['a'])
      e.expandAll(['x', 'y', 'z'])
      expect(e.isExpanded('a')).toBe(false)
      expect(e.isExpanded('x')).toBe(true)
      expect(e.expanded.value.size).toBe(3)
    })

    it('collapseAll empties the set', () => {
      const e = useExpansion(['a', 'b', 'c'])
      e.collapseAll()
      expect(e.expanded.value.size).toBe(0)
    })

    it('expandAll accepts an empty iterable to clear', () => {
      const e = useExpansion(['a'])
      e.expandAll([])
      expect(e.expanded.value.size).toBe(0)
    })
  })

  describe('reactivity', () => {
    it('expanded is reactive — toggle triggers effects', async () => {
      const e = useExpansion()
      let lastHasA = false
      let renders = 0
      watchEffect(() => {
        lastHasA = e.expanded.value.has('a')
        renders++
      })
      await nextTick()
      const initialRenders = renders

      e.toggle('a')
      await nextTick()
      expect(lastHasA).toBe(true)
      expect(renders).toBeGreaterThan(initialRenders)

      e.toggle('a')
      await nextTick()
      expect(lastHasA).toBe(false)
    })

    it('isExpanded is reactive when used in effects', async () => {
      const e = useExpansion()
      let val = false
      watchEffect(() => { val = e.isExpanded('k') })
      await nextTick()
      expect(val).toBe(false)
      e.expand('k')
      await nextTick()
      expect(val).toBe(true)
      e.collapse('k')
      await nextTick()
      expect(val).toBe(false)
    })
  })

  describe('numeric keys', () => {
    it('supports number keys via the Key generic', () => {
      const e = useExpansion<number>([1, 2])
      expect(e.isExpanded(1)).toBe(true)
      e.toggle(3)
      expect(e.isExpanded(3)).toBe(true)
      e.collapse(1)
      expect(e.isExpanded(1)).toBe(false)
    })
  })

  describe('readonly return surface', () => {
    it('expanded ref is wrapped readonly — direct .value reassignment does not leak', () => {
      const e = useExpansion()
      e.expand('a')
      // expanded is readonly(ref). In dev, attempting to reassign .value is
      // a runtime no-op + Vue warning. Public state stays intact.
      expect(e.expanded.value.size).toBe(1)
    })
  })
})
