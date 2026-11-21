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
})
