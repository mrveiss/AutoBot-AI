// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for useInitialFocus composable (#5411).
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useInitialFocus } from '../useInitialFocus'

describe('useInitialFocus', () => {
  beforeEach(() => {
    while (document.body.firstChild) document.body.removeChild(document.body.firstChild)
  })

  it('focuses the first focusable descendant', async () => {
    const container = document.createElement('div')
    container.tabIndex = -1
    const a = document.createElement('button')
    a.textContent = 'a'
    const b = document.createElement('button')
    b.textContent = 'b'
    container.append(a, b)
    document.body.appendChild(container)

    const containerRef = ref<HTMLElement | null>(container)
    const { focusFirst } = useInitialFocus(containerRef)

    await focusFirst()
    expect(document.activeElement).toBe(a)
  })

  it('falls back to focusing the container when no focusable descendants exist', async () => {
    const container = document.createElement('div')
    container.tabIndex = -1
    document.body.appendChild(container)

    const containerRef = ref<HTMLElement | null>(container)
    const { focusFirst } = useInitialFocus(containerRef)

    await focusFirst()
    expect(document.activeElement).toBe(container)
  })

  it('no-ops without throwing when containerRef is null', async () => {
    const containerRef = ref<HTMLElement | null>(null)
    const { focusFirst } = useInitialFocus(containerRef)

    await expect(focusFirst()).resolves.toBeUndefined()
  })

  it('skips disabled buttons (FOCUSABLE_SELECTOR filter)', async () => {
    const container = document.createElement('div')
    container.tabIndex = -1
    const a = document.createElement('button')
    a.disabled = true
    const b = document.createElement('button')
    container.append(a, b)
    document.body.appendChild(container)

    const containerRef = ref<HTMLElement | null>(container)
    const { focusFirst } = useInitialFocus(containerRef)

    await focusFirst()
    // a is disabled, so the first FOCUSABLE_SELECTOR match is b
    expect(document.activeElement).toBe(b)
  })

  it('awaits nextTick before querying — picks up freshly-mounted children', async () => {
    const container = document.createElement('div')
    container.tabIndex = -1
    document.body.appendChild(container)

    const containerRef = ref<HTMLElement | null>(container)
    const { focusFirst } = useInitialFocus(containerRef)

    // Schedule the focus call before adding the child — simulates the
    // consumer firing focusFirst() immediately after toggling a v-if'd
    // child into the tree. The await nextTick() inside focusFirst means
    // children added in the same microtask still get found.
    const focusPromise = focusFirst()
    const child = document.createElement('button')
    container.appendChild(child)
    await focusPromise

    expect(document.activeElement).toBe(child)
  })

  it('returns a Promise — callers can await before asserting', async () => {
    const container = document.createElement('div')
    const btn = document.createElement('button')
    container.appendChild(btn)
    document.body.appendChild(container)

    const containerRef = ref<HTMLElement | null>(container)
    const { focusFirst } = useInitialFocus(containerRef)

    const result = focusFirst()
    expect(result).toBeInstanceOf(Promise)
    await result
    expect(document.activeElement).toBe(btn)
  })
})
