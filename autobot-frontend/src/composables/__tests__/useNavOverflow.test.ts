// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick, createApp, defineComponent, effectScope } from 'vue'
import { useNavOverflow } from '../useNavOverflow'

let observeCallback: ((entries: any[]) => void) | null = null

beforeEach(() => {
  observeCallback = null
  vi.stubGlobal('ResizeObserver', class {
    constructor(cb: (entries: any[]) => void) {
      observeCallback = cb
    }
    observe() { }
    disconnect() { }
  })
})

function makeContainer(width: number, itemWidths: number[]): HTMLElement {
  const container = document.createElement('div')
  Object.defineProperty(container, 'clientWidth', { get: () => width, configurable: true })
  itemWidths.forEach(w => {
    const el = document.createElement('a')
    el.setAttribute('data-nav-item', '')
    el.getBoundingClientRect = () => ({ width: w } as DOMRect)
    container.appendChild(el)
  })
  return container
}

function useComposableInComponent(container: HTMLElement, itemCount: number) {
  let result: any
  const Comp = defineComponent({
    setup() {
      result = useNavOverflow(ref(container), ref(itemCount))
      return result
    },
    render: () => null
  })

  const app = createApp(Comp)
  const root = document.createElement('div')
  document.body.appendChild(root)
  app.mount(root)

  return {
    get visibleCount() { return result.visibleCount.value },
    dispose: () => { app.unmount() }
  }
}

describe('useNavOverflow', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('shows all items when they fit', async () => {
    const container = makeContainer(800, [80, 80, 80, 80])
    const test = useComposableInComponent(container, 4)
    await nextTick()
    expect(test.visibleCount).toBe(4)
    test.dispose()
  })

  it('clamps when container is narrow', async () => {
    const container = makeContainer(250, [80, 80, 80, 80])
    const test = useComposableInComponent(container, 4)
    await nextTick()
    expect(test.visibleCount).toBe(1)
    test.dispose()
  })

  it('recalculates when ResizeObserver fires', async () => {
    const container = makeContainer(250, [80, 80, 80, 80])
    const test = useComposableInComponent(container, 4)
    await nextTick()
    expect(test.visibleCount).toBe(1)
    Object.defineProperty(container, 'clientWidth', { get: () => 800, configurable: true })
    observeCallback?.([])
    await nextTick()
    expect(test.visibleCount).toBe(4)
    test.dispose()
  })

  it('always shows at least 1 item', async () => {
    const container = makeContainer(50, [200, 200, 200])
    const test = useComposableInComponent(container, 3)
    await nextTick()
    expect(test.visibleCount).toBe(1)
    test.dispose()
  })

  it('shows all items at exact fit boundary (no trailing-gap false overflow)', async () => {
    // 4 items × 80px + 3 gaps × 16px = 368px; container = 368px exactly — should show all 4
    const container = makeContainer(368, [80, 80, 80, 80])
    const test = useComposableInComponent(container, 4)
    await nextTick()
    expect(test.visibleCount).toBe(4)
    test.dispose()
  })

  it('re-measures when itemCount changes', async () => {
    const container = makeContainer(800, [80, 80])
    const itemCountRef = ref(2)
    let result: any
    const Comp = defineComponent({
      setup() {
        result = useNavOverflow(ref(container), itemCountRef)
        return result
      },
      render: () => null
    })

    const app = createApp(Comp)
    const root = document.createElement('div')
    document.body.appendChild(root)
    app.mount(root)

    await nextTick()
    expect(result.visibleCount.value).toBe(2)

    // Add a third item to the container and update itemCount
    const el = document.createElement('a')
    el.setAttribute('data-nav-item', '')
    el.getBoundingClientRect = () => ({ width: 80 } as DOMRect)
    container.appendChild(el)
    itemCountRef.value = 3
    await nextTick()
    await nextTick()  // second tick for watch + remeasure
    expect(result.visibleCount.value).toBe(3)

    app.unmount()
  })

  // ========================================
  // Scope-aware lifecycle (#5406)
  // ========================================

  describe('scope-aware lifecycle (#5406)', () => {
    it('does not warn when used inside an effectScope (no component)', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const container = makeContainer(400, [100, 100])
      const itemCount = ref(2)
      const scope = effectScope()
      scope.run(() => {
        useNavOverflow(ref(container), itemCount)
      })
      scope.stop()
      expect(warn).not.toHaveBeenCalledWith(
        expect.stringContaining('no active component')
      )
      warn.mockRestore()
    })
  })
})
