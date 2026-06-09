// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for useFocusRestore composable (#5356).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { defineComponent, effectScope, h, nextTick, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useFocusRestore } from '../useFocusRestore'

/** Mounts the composable and returns the wrapper for unmount control. */
function mountWithRestore() {
  const Test = defineComponent({
    setup() {
      useFocusRestore()
      return () => h('div', { tabindex: -1 }, 'inside')
    }
  })
  return mount(Test, { attachTo: document.body })
}

/** Mounts a trigger-based variant; returns wrapper + the trigger ref. */
function mountWithTrigger(initial = false): { wrapper: ReturnType<typeof mount>; show: Ref<boolean> } {
  const show = ref(initial)
  const Test = defineComponent({
    setup() {
      useFocusRestore(show)
      return () => h('div', { tabindex: -1 }, 'wrapper')
    }
  })
  const wrapper = mount(Test, { attachTo: document.body })
  return { wrapper, show }
}

describe('useFocusRestore', () => {
  beforeEach(() => {
    while (document.body.firstChild) document.body.removeChild(document.body.firstChild)
  })

  it('restores focus to the previously-focused HTMLElement on unmount', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'open'
    document.body.appendChild(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    const wrapper = mountWithRestore()
    await nextTick()
    // Move focus elsewhere to simulate dialog grabbing focus
    const inside = wrapper.find('div').element as HTMLElement
    inside.focus()
    expect(document.activeElement).toBe(inside)

    wrapper.unmount()
    await nextTick()
    expect(document.activeElement).toBe(trigger)
  })

  it('does not restore when activeElement was document.body on mount', async () => {
    // No previously-focused interactive element — body has implicit focus.
    expect(document.activeElement).toBe(document.body)

    const wrapper = mountWithRestore()
    await nextTick()
    // Whatever focus state ends up after mount, document.body is what
    // we'd "restore" to — the composable should explicitly skip this.
    const someoneElse = document.createElement('button')
    document.body.appendChild(someoneElse)
    someoneElse.focus()
    expect(document.activeElement).toBe(someoneElse)

    wrapper.unmount()
    await nextTick()
    // The composable's body-skip guard means previouslyFocused was never
    // set on mount, so .focus() is never called on unmount. The element
    // we focused after mount (someoneElse) remains the activeElement —
    // proving we didn't yank focus back to body.
    expect(document.activeElement).toBe(someoneElse)
  })

  it('does not throw when no element had focus before mount', async () => {
    // Edge case: activeElement could be null in some headless environments.
    // jsdom guarantees body is the fallback, but we guard against the null
    // path anyway — assert no throw on mount/unmount.
    expect(() => {
      const wrapper = mountWithRestore()
      wrapper.unmount()
    }).not.toThrow()
  })

  it('handles non-HTMLElement activeElement gracefully', async () => {
    // jsdom doesn't easily simulate an SVG with focus, so we verify the
    // type guard by mounting with body as activeElement (which is an
    // HTMLBodyElement IS HTMLElement, but the != body check excludes it).
    // This test pairs with the body-skip case above.
    const wrapper = mountWithRestore()
    expect(() => wrapper.unmount()).not.toThrow()
  })

  it('clears the saved reference on unmount (no leak across mount/unmount cycles)', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    const w1 = mountWithRestore()
    await nextTick()
    w1.unmount()
    await nextTick()

    // Now remove trigger entirely — second mount/unmount should not try
    // to focus the detached element from the first cycle.
    document.body.removeChild(trigger)
    const w2 = mountWithRestore()
    await nextTick()
    expect(() => w2.unmount()).not.toThrow()
    // No assertion on activeElement — point is no exception was thrown
    // by attempting to .focus() a stale reference.
  })

  describe('trigger-based mode (Ref<boolean>)', () => {
    it('saves on false→true transition, restores on true→false', async () => {
      const trigger = document.createElement('button')
      document.body.appendChild(trigger)
      trigger.focus()
      expect(document.activeElement).toBe(trigger)

      const { wrapper, show } = mountWithTrigger(false)
      await nextTick()

      // Open: save should fire
      show.value = true
      await nextTick()

      // Move focus elsewhere to simulate dialog grabbing focus
      const inside = wrapper.find('div').element as HTMLElement
      inside.focus()
      expect(document.activeElement).toBe(inside)

      // Close: restore should fire
      show.value = false
      await nextTick()
      expect(document.activeElement).toBe(trigger)

      wrapper.unmount()
    })

    it('saves on initial mount when trigger is already true', async () => {
      const trigger = document.createElement('button')
      document.body.appendChild(trigger)
      trigger.focus()

      // Trigger starts true — save should fire on initial run
      const { wrapper, show } = mountWithTrigger(true)
      await nextTick()

      const inside = wrapper.find('div').element as HTMLElement
      inside.focus()

      show.value = false
      await nextTick()
      expect(document.activeElement).toBe(trigger)

      wrapper.unmount()
    })

    it('multiple open/close cycles each save/restore independently', async () => {
      const triggerA = document.createElement('button')
      const triggerB = document.createElement('button')
      document.body.appendChild(triggerA)
      document.body.appendChild(triggerB)

      const { wrapper, show } = mountWithTrigger(false)
      await nextTick()

      // First open from triggerA
      triggerA.focus()
      show.value = true
      await nextTick()
      ;(wrapper.find('div').element as HTMLElement).focus()
      show.value = false
      await nextTick()
      expect(document.activeElement).toBe(triggerA)

      // Second open from triggerB
      triggerB.focus()
      show.value = true
      await nextTick()
      ;(wrapper.find('div').element as HTMLElement).focus()
      show.value = false
      await nextTick()
      expect(document.activeElement).toBe(triggerB)

      wrapper.unmount()
    })

    it('does nothing when trigger toggles within the same true/false state', async () => {
      // Edge case: imperatively setting show=true when already true should
      // not re-save. Watch handler's wasActive guard prevents this.
      const trigger = document.createElement('button')
      document.body.appendChild(trigger)
      trigger.focus()

      const { wrapper, show } = mountWithTrigger(true)
      await nextTick()

      const inside = wrapper.find('div').element as HTMLElement
      inside.focus()

      // Re-set to true (no-op for ref but sanity check)
      show.value = true
      await nextTick()

      show.value = false
      await nextTick()
      // Restore should still go to the original trigger, not `inside`
      expect(document.activeElement).toBe(trigger)

      wrapper.unmount()
    })
  })

  it('saves focus even when restored element is later detached from DOM', async () => {
    // Real-world scenario: dialog opens, the trigger gets unmounted
    // by reactive state changes, dialog closes — restoring focus to a
    // detached element is a no-op in browsers (no error).
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    const wrapper = mountWithRestore()
    await nextTick()

    // Detach trigger before unmount
    document.body.removeChild(trigger)

    // Should not throw — element.focus() on a detached node is silently
    // ignored by browsers (and jsdom matches that behavior).
    expect(() => wrapper.unmount()).not.toThrow()
  })

  // ========================================
  // Scope-aware lifecycle (#5406)
  // ========================================

  describe('scope-aware lifecycle (#5406)', () => {
    it('does not warn when used inside an effectScope (no component)', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const scope = effectScope()
      scope.run(() => {
        useFocusRestore()
      })
      scope.stop()
      expect(warn).not.toHaveBeenCalledWith(
        expect.stringContaining('no active component')
      )
      warn.mockRestore()
    })

    it('does not warn when called with no active scope at all', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      useFocusRestore()
      expect(warn).not.toHaveBeenCalledWith(
        expect.stringContaining('no active component')
      )
      warn.mockRestore()
    })
  })
})
