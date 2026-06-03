import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { defineComponent, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHashHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { useGlobalShortcuts } from '../useGlobalShortcuts'

function makeKeyEvent(key: string, opts: { ctrlKey?: boolean; metaKey?: boolean } = {}): KeyboardEvent {
  return new KeyboardEvent('keydown', {
    key,
    ctrlKey: opts.ctrlKey ?? false,
    metaKey: opts.metaKey ?? false,
    bubbles: true,
    cancelable: true
  })
}

describe('useGlobalShortcuts', () => {
  let router: ReturnType<typeof createRouter>

  beforeEach(() => {
    setActivePinia(createPinia())
    router = createRouter({
      history: createWebHashHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/chat', component: { template: '<div />' } }
      ]
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('Ctrl+K opens command palette', async () => {
    const openSpy = vi.fn()
    const commandPaletteRef = ref<{ open: () => void } | null>({ open: openSpy })

    const TestComp = defineComponent({
      setup() {
        useGlobalShortcuts({ commandPaletteRef })
        return {}
      },
      template: '<div />'
    })

    mount(TestComp, { global: { plugins: [router] } })
    await nextTick()

    document.dispatchEvent(makeKeyEvent('k', { ctrlKey: true }))

    expect(openSpy).toHaveBeenCalledTimes(1)
  })

  it('Meta+K opens command palette', async () => {
    const openSpy = vi.fn()
    const commandPaletteRef = ref<{ open: () => void } | null>({ open: openSpy })

    const TestComp = defineComponent({
      setup() {
        useGlobalShortcuts({ commandPaletteRef })
        return {}
      },
      template: '<div />'
    })

    mount(TestComp, { global: { plugins: [router] } })
    await nextTick()

    document.dispatchEvent(makeKeyEvent('k', { metaKey: true }))

    expect(openSpy).toHaveBeenCalledTimes(1)
  })

  it('Ctrl+N creates new session and navigates to /chat', async () => {
    const commandPaletteRef = ref<{ open: () => void } | null>(null)

    const { useChatStore } = await import('@/stores/useChatStore')
    const TestComp = defineComponent({
      setup() {
        useGlobalShortcuts({ commandPaletteRef })
        return {}
      },
      template: '<div />'
    })

    mount(TestComp, { global: { plugins: [router] } })
    await nextTick()

    const chatStore = useChatStore()
    const createSpy = vi.spyOn(chatStore, 'createNewSession')
    const pushSpy = vi.spyOn(router, 'push')

    document.dispatchEvent(makeKeyEvent('n', { ctrlKey: true }))

    expect(createSpy).toHaveBeenCalledTimes(1)
    expect(pushSpy).toHaveBeenCalledWith('/chat')
  })

  it('Ctrl+1 switches to first session and navigates to /chat', async () => {
    const commandPaletteRef = ref<{ open: () => void } | null>(null)

    const { useChatStore } = await import('@/stores/useChatStore')
    const TestComp = defineComponent({
      setup() {
        useGlobalShortcuts({ commandPaletteRef })
        return {}
      },
      template: '<div />'
    })

    mount(TestComp, { global: { plugins: [router] } })
    await nextTick()

    const chatStore = useChatStore()
    // Seed a session
    const sessionId = chatStore.createNewSession('Test session')
    const switchSpy = vi.spyOn(chatStore, 'switchToSession')
    const pushSpy = vi.spyOn(router, 'push')

    document.dispatchEvent(makeKeyEvent('1', { ctrlKey: true }))

    expect(switchSpy).toHaveBeenCalledWith(sessionId)
    expect(pushSpy).toHaveBeenCalledWith('/chat')
  })

  it('Ctrl+1 does nothing when no sessions exist', async () => {
    const commandPaletteRef = ref<{ open: () => void } | null>(null)

    const { useChatStore } = await import('@/stores/useChatStore')
    const TestComp = defineComponent({
      setup() {
        useGlobalShortcuts({ commandPaletteRef })
        return {}
      },
      template: '<div />'
    })

    mount(TestComp, { global: { plugins: [router] } })
    await nextTick()

    const chatStore = useChatStore()
    const switchSpy = vi.spyOn(chatStore, 'switchToSession')
    const pushSpy = vi.spyOn(router, 'push')

    // No sessions — shortcut should be a no-op
    document.dispatchEvent(makeKeyEvent('1', { ctrlKey: true }))

    expect(switchSpy).not.toHaveBeenCalled()
    expect(pushSpy).not.toHaveBeenCalled()
  })

  it('Ctrl+9 switches to ninth session when available', async () => {
    const commandPaletteRef = ref<{ open: () => void } | null>(null)

    const { useChatStore } = await import('@/stores/useChatStore')
    const TestComp = defineComponent({
      setup() {
        useGlobalShortcuts({ commandPaletteRef })
        return {}
      },
      template: '<div />'
    })

    mount(TestComp, { global: { plugins: [router] } })
    await nextTick()

    const chatStore = useChatStore()
    const ids: string[] = []
    for (let i = 0; i < 9; i++) {
      ids.push(chatStore.createNewSession(`Session ${i + 1}`))
    }
    // sessions are prepended (unshift), so index 8 = oldest = ids[0]
    const switchSpy = vi.spyOn(chatStore, 'switchToSession')
    const pushSpy = vi.spyOn(router, 'push')

    document.dispatchEvent(makeKeyEvent('9', { ctrlKey: true }))

    expect(switchSpy).toHaveBeenCalledTimes(1)
    expect(pushSpy).toHaveBeenCalledWith('/chat')
  })
})
