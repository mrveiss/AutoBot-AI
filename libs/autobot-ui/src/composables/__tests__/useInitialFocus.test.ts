// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useInitialFocus (#18243): a data-autofocus target wins over the first focusable.
import { describe, it, expect, afterEach } from 'vitest'
import { ref } from 'vue'
import { useInitialFocus } from '../useInitialFocus'

function container(html: string) {
  const el = document.createElement('div')
  el.innerHTML = html
  document.body.append(el)
  return el
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useInitialFocus', () => {
  it('focuses the first focusable by default', async () => {
    const el = container('<button id="close"></button><input id="field">')
    await useInitialFocus(ref(el)).focusFirst()
    expect(document.activeElement?.id).toBe('close')
  })

  it('prefers a data-autofocus element', async () => {
    const el = container('<button id="close"></button><input id="field" data-autofocus>')
    await useInitialFocus(ref(el)).focusFirst()
    expect(document.activeElement?.id).toBe('field')
  })

  it('focuses the first focusable inside a data-autofocus wrapper', async () => {
    const el = container('<button id="close"></button><div data-autofocus><label>Name</label><input id="field"></div>')
    await useInitialFocus(ref(el)).focusFirst()
    expect(document.activeElement?.id).toBe('field')
  })

  it('skips a data-autofocus input that is display:none, so the first focusable still gets focus', async () => {
    const el = container('<button id="close"></button><div style="display:none"><input id="field" data-autofocus></div>')
    await useInitialFocus(ref(el)).focusFirst()
    expect(document.activeElement?.id).toBe('close')
  })

  it('keeps a visible data-autofocus input ahead of the close button', async () => {
    const el = container('<button id="close"></button><input id="hidden" data-autofocus style="display:none"><input id="field" data-autofocus>')
    await useInitialFocus(ref(el)).focusFirst()
    expect(document.activeElement?.id).toBe('field')
  })

  it('finds the first tabbable descendant of a marked wrapper when an earlier one is hidden', async () => {
    const el = container('<button id="close"></button><div data-autofocus><input id="hidden" style="display:none"><input id="field"></div>')
    await useInitialFocus(ref(el)).focusFirst()
    expect(document.activeElement?.id).toBe('field')
  })
})
