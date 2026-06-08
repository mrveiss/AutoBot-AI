// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Unit tests for useFocusTrap composable (#5130).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { useFocusTrap, FOCUSABLE_SELECTOR } from '../useFocusTrap'

/** Build a container with the given number of tabbable buttons. */
function makeContainer(buttonCount: number): {
  container: HTMLElement
  buttons: HTMLButtonElement[]
} {
  const container = document.createElement('div')
  const buttons: HTMLButtonElement[] = []
  for (let i = 0; i < buttonCount; i++) {
    const btn = document.createElement('button')
    btn.textContent = `btn-${i}`
    container.appendChild(btn)
    buttons.push(btn)
  }
  document.body.appendChild(container)
  return { container, buttons }
}

function tabEvent(shift = false): KeyboardEvent {
  return new KeyboardEvent('keydown', {
    key: 'Tab',
    shiftKey: shift,
    cancelable: true,
    bubbles: true
  })
}

describe('useFocusTrap', () => {
  beforeEach(() => {
    while (document.body.firstChild) document.body.removeChild(document.body.firstChild)
  })

  it('exports a FOCUSABLE_SELECTOR matching the BaseModal/#5121 pattern', () => {
    // Guard against drift — consumers rely on the module-level constant.
    expect(FOCUSABLE_SELECTOR).toContain('button:not(:disabled)')
    expect(FOCUSABLE_SELECTOR).toContain('[tabindex]:not([tabindex="-1"])')
    expect(FOCUSABLE_SELECTOR).toContain('[href]')
    expect(FOCUSABLE_SELECTOR).toContain('input:not(:disabled)')
    expect(FOCUSABLE_SELECTOR).toContain('select:not(:disabled)')
    expect(FOCUSABLE_SELECTOR).toContain('textarea:not(:disabled)')
  })

  describe('Tab wrap', () => {
    it('wraps focus from last element to first when Tab pressed on last', () => {
      const { container, buttons } = makeContainer(3)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      buttons[2].focus()
      expect(document.activeElement).toBe(buttons[2])

      const ev = tabEvent(false)
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      onKeydown(ev)

      expect(preventSpy).toHaveBeenCalledOnce()
      expect(document.activeElement).toBe(buttons[0])
    })

    it('lets Tab fall through when focus is in the middle', () => {
      const { container, buttons } = makeContainer(3)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      buttons[1].focus()
      const ev = tabEvent(false)
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      onKeydown(ev)

      // Browser handles the Tab. We only assert we did NOT intercept.
      expect(preventSpy).not.toHaveBeenCalled()
      expect(document.activeElement).toBe(buttons[1])
    })
  })

  describe('Shift+Tab wrap', () => {
    it('wraps focus from first element to last when Shift+Tab pressed on first', () => {
      const { container, buttons } = makeContainer(3)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      buttons[0].focus()
      expect(document.activeElement).toBe(buttons[0])

      const ev = tabEvent(true)
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      onKeydown(ev)

      expect(preventSpy).toHaveBeenCalledOnce()
      expect(document.activeElement).toBe(buttons[2])
    })

    it('lets Shift+Tab fall through when focus is in the middle', () => {
      const { container, buttons } = makeContainer(3)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      buttons[1].focus()
      const ev = tabEvent(true)
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      onKeydown(ev)

      expect(preventSpy).not.toHaveBeenCalled()
    })
  })

  describe('edge cases', () => {
    it('no-ops on empty container (no focusable descendants)', () => {
      const container = document.createElement('div')
      document.body.appendChild(container)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      const ev = tabEvent(false)
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      onKeydown(ev)

      expect(preventSpy).not.toHaveBeenCalled()
    })

    it('no-ops when container ref is null', () => {
      const ref_ = ref<HTMLElement | null>(null)
      const { onKeydown } = useFocusTrap(ref_)

      const ev = tabEvent(false)
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      // Should not throw.
      expect(() => onKeydown(ev)).not.toThrow()
      expect(preventSpy).not.toHaveBeenCalled()
    })

    it('no-ops for non-Tab keys', () => {
      const { container } = makeContainer(2)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      const ev = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true })
      const preventSpy = vi.spyOn(ev, 'preventDefault')
      onKeydown(ev)

      expect(preventSpy).not.toHaveBeenCalled()
    })

    it('picks up new focusables added to the container after mount', () => {
      // Regression guard: the handler re-runs querySelectorAll on every
      // keypress, so dynamically-added buttons participate in the trap.
      const { container, buttons } = makeContainer(2)
      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      const added = document.createElement('button')
      container.appendChild(added)

      added.focus()
      expect(document.activeElement).toBe(added)

      const ev = tabEvent(false)
      onKeydown(ev)
      // New button was last in document order — Tab wraps to buttons[0].
      expect(document.activeElement).toBe(buttons[0])
    })

    it('skips disabled buttons (FOCUSABLE_SELECTOR filter)', () => {
      const container = document.createElement('div')
      const a = document.createElement('button')
      const b = document.createElement('button')
      b.disabled = true
      const c = document.createElement('button')
      container.append(a, b, c)
      document.body.appendChild(container)

      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      c.focus()
      const ev = tabEvent(false)
      onKeydown(ev)
      // b is disabled, so the "last" is c and the "first" is a.
      expect(document.activeElement).toBe(a)
    })
  })

  describe('isTabbable filter (#5373)', () => {
    it('skips buttons inside aria-hidden subtrees', () => {
      const container = document.createElement('div')
      const a = document.createElement('button')
      const hiddenWrap = document.createElement('div')
      hiddenWrap.setAttribute('aria-hidden', 'true')
      const insideHidden = document.createElement('button')
      hiddenWrap.appendChild(insideHidden)
      const c = document.createElement('button')
      container.append(a, hiddenWrap, c)
      document.body.appendChild(container)

      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      // Focus c (the visible last). Tab should wrap to a (visible first),
      // skipping insideHidden which is in an aria-hidden subtree.
      c.focus()
      const ev = tabEvent(false)
      onKeydown(ev)
      expect(document.activeElement).toBe(a)
    })

    it('skips buttons inside [inert] containers', () => {
      const container = document.createElement('div')
      const a = document.createElement('button')
      const inertWrap = document.createElement('div')
      inertWrap.setAttribute('inert', '')
      const insideInert = document.createElement('button')
      inertWrap.appendChild(insideInert)
      const c = document.createElement('button')
      container.append(a, inertWrap, c)
      document.body.appendChild(container)

      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      c.focus()
      const ev = tabEvent(false)
      onKeydown(ev)
      // insideInert filtered out → wrap from c to a.
      expect(document.activeElement).toBe(a)
    })

    it('skips buttons whose ancestor has display:none (offsetParent === null)', () => {
      const container = document.createElement('div')
      const a = document.createElement('button')
      const hiddenWrap = document.createElement('div')
      hiddenWrap.style.display = 'none'
      const insideHidden = document.createElement('button')
      hiddenWrap.appendChild(insideHidden)
      const c = document.createElement('button')
      container.append(a, hiddenWrap, c)
      document.body.appendChild(container)

      const ref_ = ref<HTMLElement | null>(container)
      const { onKeydown } = useFocusTrap(ref_)

      c.focus()
      const ev = tabEvent(false)
      onKeydown(ev)
      // insideHidden's offsetParent is null → filtered out → wrap c → a.
      expect(document.activeElement).toBe(a)
    })
  })
})
