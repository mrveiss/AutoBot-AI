// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for useBodyScrollLock composable (#5422).
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { defineComponent, h, ref, nextTick, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useBodyScrollLock, __resetLockStateForTests } from '../useBodyScrollLock'

function mountWithLock(initial: boolean): {
  wrapper: ReturnType<typeof mount>
  active: Ref<boolean>
} {
  const active = ref(initial)
  const Test = defineComponent({
    setup() {
      useBodyScrollLock(active)
      return () => h('div', 'inside')
    }
  })
  const wrapper = mount(Test, { attachTo: document.body })
  return { wrapper, active }
}

describe('useBodyScrollLock', () => {
  beforeEach(() => {
    __resetLockStateForTests()
  })

  it('locks body scroll when active becomes true', async () => {
    expect(document.body.style.overflow).toBe('')
    const { wrapper, active } = mountWithLock(false)
    await nextTick()
    expect(document.body.style.overflow).toBe('')

    active.value = true
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')

    wrapper.unmount()
  })

  it('unlocks body scroll when active becomes false', async () => {
    const { wrapper, active } = mountWithLock(true)
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')

    active.value = false
    await nextTick()
    expect(document.body.style.overflow).toBe('')

    wrapper.unmount()
  })

  it('locks immediately on mount when active starts true', async () => {
    const { wrapper } = mountWithLock(true)
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')
    wrapper.unmount()
  })

  it('does nothing when active stays false throughout lifecycle', async () => {
    const { wrapper } = mountWithLock(false)
    await nextTick()
    expect(document.body.style.overflow).toBe('')
    wrapper.unmount()
    await nextTick()
    expect(document.body.style.overflow).toBe('')
  })

  describe('reference counting across stacked consumers', () => {
    it('inner close does not release the lock while outer is still active', async () => {
      const outer = mountWithLock(true)
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')

      const inner = mountWithLock(true)
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')

      // Close inner first
      inner.active.value = false
      await nextTick()
      // Outer is still active — scroll must still be locked
      expect(document.body.style.overflow).toBe('hidden')

      // Close outer
      outer.active.value = false
      await nextTick()
      expect(document.body.style.overflow).toBe('')

      inner.wrapper.unmount()
      outer.wrapper.unmount()
    })

    it('unmount while active releases the lock correctly', async () => {
      const a = mountWithLock(true)
      const b = mountWithLock(true)
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')

      // Unmount b while still active — should decrement but not unlock (a still holds)
      b.wrapper.unmount()
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')

      // Unmount a — now the lock releases
      a.wrapper.unmount()
      await nextTick()
      expect(document.body.style.overflow).toBe('')
    })
  })

  describe('preserves pre-existing overflow value', () => {
    it('restores body.style.overflow to its prior value on full unlock', async () => {
      document.body.style.overflow = 'scroll'
      const { wrapper, active } = mountWithLock(false)

      active.value = true
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')

      active.value = false
      await nextTick()
      // Should restore to 'scroll', not ''
      expect(document.body.style.overflow).toBe('scroll')

      wrapper.unmount()
      document.body.style.overflow = ''
    })
  })

  describe('rapid toggle', () => {
    it('does not double-acquire when active is imperatively set true while already true', async () => {
      const { wrapper, active } = mountWithLock(true)
      await nextTick()

      // Re-setting to true (same state) should be a no-op
      active.value = true
      await nextTick()

      // Closing once should still fully unlock (not leave count at 1)
      active.value = false
      await nextTick()
      expect(document.body.style.overflow).toBe('')

      wrapper.unmount()
    })
  })
})
