// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useFocusTrap activate/deactivate (#19688): initial focus, focus restoration and the
// optional document listener, merged in from the SLM's former local copy.

import { describe, it, expect, afterEach } from 'vitest'
import { effectScope, ref } from 'vue'
import { useFocusTrap } from '../useFocusTrap'

let outside: HTMLButtonElement
let container: HTMLDivElement
let first: HTMLButtonElement
let last: HTMLButtonElement

function build() {
  outside = document.createElement('button')
  container = document.createElement('div')
  first = document.createElement('button')
  last = document.createElement('button')
  container.append(first, last)
  document.body.append(outside, container)
  outside.focus()
  return ref<HTMLElement | null>(container)
}

function tab(shift = false) {
  const e = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: shift, cancelable: true })
  document.dispatchEvent(e)
  return e
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useFocusTrap activate/deactivate', () => {
  it('focuses the first tabbable element on activate when initialFocus is set', () => {
    const { activate } = useFocusTrap(build(), { initialFocus: true })
    activate()
    expect(document.activeElement).toBe(first)
  })

  it('does not move focus on activate by default', () => {
    const { activate } = useFocusTrap(build())
    activate()
    expect(document.activeElement).toBe(outside)
  })

  it('restores focus to the prior element on deactivate when restoreFocus is set', () => {
    const { activate, deactivate } = useFocusTrap(build(), { initialFocus: true, restoreFocus: true })
    activate()
    expect(document.activeElement).toBe(first)
    deactivate()
    expect(document.activeElement).toBe(outside)
  })

  it('does not restore focus by default', () => {
    const { activate, deactivate } = useFocusTrap(build(), { initialFocus: true })
    activate()
    deactivate()
    expect(document.activeElement).toBe(first)
  })

  it('skips aria-hidden elements for initial focus', () => {
    const target = build()
    const hidden = document.createElement('div')
    hidden.setAttribute('aria-hidden', 'true')
    hidden.append(document.createElement('button'))
    container.prepend(hidden)
    useFocusTrap(target, { initialFocus: true }).activate()
    expect(document.activeElement).toBe(first)
  })

  it('wraps Tab on the document only between activate and deactivate with listenOnDocument', () => {
    const { activate, deactivate } = useFocusTrap(build(), { listenOnDocument: true })
    activate()
    last.focus()
    expect(tab().defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
    deactivate()
    last.focus()
    expect(tab().defaultPrevented).toBe(false)
  })

  it('deactivates when its effect scope stops', () => {
    const scope = effectScope()
    const trap = scope.run(() => useFocusTrap(build(), { restoreFocus: true, initialFocus: true }))!
    trap.activate()
    scope.stop()
    expect(document.activeElement).toBe(outside)
  })

  it('deactivate before activate is a no-op', () => {
    const { deactivate } = useFocusTrap(build(), { restoreFocus: true })
    deactivate()
    expect(document.activeElement).toBe(outside)
  })

  it('leaves no document listener after activate twice and one deactivate', () => {
    const { activate, deactivate } = useFocusTrap(build(), { listenOnDocument: true })
    activate()
    activate()
    deactivate()
    last.focus()
    expect(tab().defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(last)
  })

  it('does not throw restoring focus to an element removed from the DOM', () => {
    const { activate, deactivate } = useFocusTrap(build(), { restoreFocus: true, initialFocus: true })
    activate()
    outside.remove()
    expect(() => deactivate()).not.toThrow()
  })
})
