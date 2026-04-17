import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick, createApp, defineComponent } from 'vue'
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
})
