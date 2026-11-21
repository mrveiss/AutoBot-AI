// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * ChatTabs is a WAI-ARIA tablist (#18243): roles, roving tabindex, aria-controls
 * on the active tab only, and Arrow / Home / End keys that wrap and skip the
 * permission-hidden desktop tab.
 */
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

import type ChatTabsType from '../ChatTabs.vue'
import { useUserStore } from '@/stores/useUserStore'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
let ChatTabs: typeof ChatTabsType

beforeAll(async () => {
  ChatTabs = (await import('../ChatTabs.vue')).default
}, 60_000)

function mountTabs(role: string, activeTab = 'chat'): VueWrapper {
  useUserStore().currentUser = { role } as never
  return mount(ChatTabs, {
    props: { activeTab },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}

/** Focus the tab, then dispatch a real keydown: the kit's tabs listen on the trigger itself. */
async function pressOn(w: VueWrapper, tabKey: string, key: string): Promise<void> {
  await flushPromises() // the kit registers its roving-focus items after mount
  const tab = w.get(`#tab-${tabKey}`).element as HTMLElement
  tab.focus()
  tab.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

const keys = (w: VueWrapper) => w.findAll('[role="tab"]').map((t) => t.attributes('id'))

describe('ChatTabs tablist semantics (#18243)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders a labelled tablist of tabs with one selected, tabbable tab', () => {
    const w = mountTabs('admin', 'files')
    const list = w.get('[role="tablist"]')
    expect(list.attributes('aria-label')).toBe(en.chat.tabs.ariaLabel)
    const tabs = w.findAll('[role="tab"]')
    expect(tabs).toHaveLength(5)
    const selected = tabs.filter((t) => t.attributes('aria-selected') === 'true')
    expect(selected.map((t) => t.attributes('id'))).toEqual(['tab-files'])
    // The kit's roving focus makes the tablist the one tab stop and hands focus to the active tab.
    expect(tabs.filter((t) => t.attributes('tabindex') === '0').length).toBeLessThanOrEqual(1)
    expect(selected[0].attributes('aria-controls')).toBe('tabpanel-files')
    expect(tabs.filter((t) => t.attributes('aria-controls'))).toHaveLength(1)
    w.unmount()
  })

  it('selecting a tab emits tab-change', async () => {
    const w = mountTabs('admin')
    await w.get('#tab-terminal').trigger('mousedown')
    expect(w.emitted('tab-change')?.[0]).toEqual(['terminal'])
    w.unmount()
  })

  it.each([
    ['ArrowRight', 'chat', 'files'],
    ['ArrowLeft', 'chat', 'novnc'],
    ['ArrowRight', 'novnc', 'chat'],
    ['Home', 'browser', 'chat'],
    ['End', 'chat', 'novnc'],
  ])('%s from %s selects %s', async (key, from, to) => {
    const w = mountTabs('admin', from)
    await pressOn(w, from, key)
    expect(w.emitted('tab-change')?.[0]).toEqual([to])
    w.unmount()
  })

  it('moves focus to the newly selected tab', async () => {
    const w = mountTabs('admin')
    await pressOn(w, 'chat', 'ArrowRight')
    expect(document.activeElement?.id).toBe('tab-files')
    w.unmount()
  })

  it('skips the desktop tab for a role without the permission', async () => {
    const w = mountTabs('viewer', 'browser')
    expect(keys(w)).not.toContain('tab-novnc')
    await pressOn(w, 'browser', 'ArrowRight')
    expect(w.emitted('tab-change')?.[0]).toEqual(['chat'])
    w.unmount()
  })

  it('ignores unrelated keys', async () => {
    const w = mountTabs('admin')
    await pressOn(w, 'chat', 'a')
    expect(w.emitted('tab-change')).toBeUndefined()
    w.unmount()
  })

  it('gives every tab a rendered icon (the old class-string icons rendered nothing)', () => {
    const w = mountTabs('admin')
    const tabs = w.findAll('[role="tab"]')
    expect(tabs).toHaveLength(5)
    expect(tabs.every((t) => t.find('svg path').exists())).toBe(true)
    w.unmount()
  })

  it('marks Terminal, Browser and Remote desktop advanced, but never the active one', () => {
    const w = mountTabs('admin', 'chat')
    const adv = w.findAll('[role="tab"]').filter((t) => t.classes().includes('adv'))
    expect(adv.map((t) => t.attributes('id'))).toEqual(['tab-terminal', 'tab-browser', 'tab-novnc'])
    w.unmount()
    const onTerminal = mountTabs('admin', 'terminal')
    expect(onTerminal.get('#tab-terminal').classes()).not.toContain('adv')
    onTerminal.unmount()
  })

  it('renders no tabpanel of its own: ChatTabContent owns it', () => {
    const w = mountTabs('admin')
    expect(w.find('[role="tabpanel"]').exists()).toBe(false)
    w.unmount()
  })
})
