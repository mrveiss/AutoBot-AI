// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #18239 / #754: the sidebar menu's arrow / Home / End navigation comes from the shared
 * `useKeyboardNav`. The menu must keep one focusable slot per visible item, so removing the tail
 * item (an admin-only entry after a role change) never leaves End or wrap-around on a hole.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, reactive } from 'vue'
import Sidebar from './Sidebar.vue'

const auth = reactive({ isAuthenticated: false, isAdmin: true, logout: vi.fn() })

// @autobot/ui drags in reka-ui, which does not load under vitest here: stand in for what Sidebar uses.
vi.mock('@autobot/ui', () => ({
  BrandMark: defineComponent({ setup: () => () => h('span') }),
  usePollingJob: () => ({ start: vi.fn() }),
  useAnnounce: () => ({ announce: vi.fn() }),
  useFocusTrap: () => ({}),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/components/common/LanguageSwitcher.vue', () => ({
  default: defineComponent({ setup: () => () => h('span') }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/fleet' }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({ overallHealth: 'healthy', fleetSummary: {} }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/composables/useCodeSync', () => ({
  useCodeSync: () => ({ outdatedCount: { value: 0 }, fetchStatus: vi.fn() }),
}))
vi.mock('@/composables/useSystemUpdates', () => ({
  useSystemUpdates: () => ({ updateCount: { value: 0 }, fetchSummary: vi.fn() }),
}))
vi.mock('@/composables/useSlmTheme', () => ({
  useSlmTheme: () => ({ isContrast: { value: false }, toggleContrast: vi.fn() }),
}))

function mountSidebar() {
  return mount(Sidebar, {
    attachTo: document.body,
    global: {
      mocks: { $t: (key: string) => key },
    },
  })
}

function items(wrapper: ReturnType<typeof mountSidebar>): HTMLElement[] {
  return wrapper.findAll('[role="menuitem"]').map((w) => w.element as HTMLElement)
}

async function press(el: HTMLElement, key: string): Promise<void> {
  el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
  await nextTick()
}

describe('Sidebar keyboard navigation', () => {
  it('moves with ArrowDown / ArrowUp, jumps with Home / End, and wraps', async () => {
    auth.isAdmin = true
    const wrapper = mountSidebar()
    const nav = items(wrapper)
    const last = nav.length - 1

    nav[0].focus()
    await press(nav[0], 'ArrowDown')
    expect(document.activeElement).toBe(nav[1])
    await press(nav[1], 'ArrowUp')
    expect(document.activeElement).toBe(nav[0])
    await press(nav[0], 'ArrowUp')
    expect(document.activeElement).toBe(nav[last])
    await press(nav[last], 'ArrowDown')
    expect(document.activeElement).toBe(nav[0])
    await press(nav[0], 'End')
    expect(document.activeElement).toBe(nav[last])
    await press(nav[last], 'Home')
    expect(document.activeElement).toBe(nav[0])
    wrapper.unmount()
  })

  it('starts from the focused item, not from the top', async () => {
    auth.isAdmin = true
    const wrapper = mountSidebar()
    const nav = items(wrapper)

    nav[3].focus()
    await press(nav[3], 'ArrowDown')
    expect(document.activeElement).toBe(nav[4])
    wrapper.unmount()
  })

  it('still reaches the new last item with End and wrap-around once the tail item is removed', async () => {
    auth.isAdmin = true
    const wrapper = mountSidebar()
    const before = items(wrapper)

    auth.isAdmin = false
    await nextTick()
    await nextTick()
    const after = items(wrapper)
    expect(after.length).toBe(before.length - 1)
    const last = after.length - 1

    after[0].focus()
    await press(after[0], 'End')
    expect(document.activeElement).toBe(after[last])
    await press(after[last], 'ArrowDown')
    expect(document.activeElement).toBe(after[0])
    await press(after[0], 'ArrowUp')
    expect(document.activeElement).toBe(after[last])
    wrapper.unmount()
  })
})
