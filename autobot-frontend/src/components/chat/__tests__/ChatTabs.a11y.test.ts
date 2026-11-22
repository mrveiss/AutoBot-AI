// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * ChatTabs is a WAI-ARIA tablist (#18243): roles, roving tabindex, aria-controls
 * on the active tab only, and Arrow / Home / End keys that wrap and skip the
 * permission-hidden desktop tab.
 */
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

import type ChatTabsType from '../ChatTabs.vue'
import { useUserStore } from '@/stores/useUserStore'
import { useUiMode } from '@/composables/useUiMode'

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

  it('selects an inactive tab on a bare click, once, even when mousedown precedes it', async () => {
    const w = mountTabs('admin')
    ;(w.get('#tab-files').element as HTMLElement).click()
    expect(w.emitted('tab-change')).toEqual([['files']])
    await w.get('#tab-browser').trigger('mousedown')
    ;(w.get('#tab-browser').element as HTMLElement).click()
    expect(w.emitted('tab-change')).toEqual([['files'], ['browser']])
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

  it('sets the mockup tab metrics: 44px high, 13.5px type, 12px side padding, 17px icons', () => {
    const w = mountTabs('admin')
    expect(w.get('.chat-tabs').classes()).toEqual(
      expect.arrayContaining(['[--aui-tabs-trigger-height:2.75rem]', '[--aui-tabs-font-size:0.84375rem]', '[--aui-tabs-trigger-pad-x:0.75rem]']),
    )
    expect(w.get('[role="tab"] svg').classes()).toContain('size-[1.0625rem]!')
    expect(w.get('[role="tab"] svg').attributes('style')).toBeUndefined()
    w.unmount()
  })

  it('renders no tabpanel of its own: ChatTabContent owns it', () => {
    const w = mountTabs('admin')
    expect(w.find('[role="tabpanel"]').exists()).toBe(false)
    w.unmount()
  })

  describe('Minimal mode (#18243)', () => {
    beforeEach(() => useUiMode().setMode('minimal'))
    afterEach(() => useUiMode().setMode('full'))

    it('drops the advanced tabs from the tablist, so arrow keys cannot land on a hidden one', async () => {
      const w = mountTabs('admin', 'chat')
      expect(keys(w)).toEqual(['tab-chat', 'tab-files'])
      await pressOn(w, 'chat', 'ArrowLeft')
      expect(w.emitted('tab-change')?.[0]).toEqual(['files'])
      await w.setProps({ activeTab: 'files' })
      await pressOn(w, 'files', 'ArrowRight')
      expect(w.emitted('tab-change')?.[1]).toEqual(['chat'])
      await w.setProps({ activeTab: 'chat' })
      await pressOn(w, 'chat', 'End')
      expect(w.emitted('tab-change')?.[2]).toEqual(['files'])
      w.unmount()
    })

    it('keeps a bookmarked advanced tab that is already active', () => {
      const w = mountTabs('admin', 'terminal')
      expect(keys(w)).toEqual(['tab-chat', 'tab-files', 'tab-terminal'])
      w.unmount()
    })

    it('switching to Minimal on an advanced tab moves to Chat; on Chat or Files it does not', async () => {
      useUiMode().setMode('full')
      const w = mountTabs('admin', 'browser')
      useUiMode().setMode('minimal')
      await flushPromises()
      expect(w.emitted('tab-change')).toEqual([['chat']])
      w.unmount()
      useUiMode().setMode('full')
      const onFiles = mountTabs('admin', 'files')
      useUiMode().setMode('minimal')
      await flushPromises()
      expect(onFiles.emitted('tab-change')).toBeUndefined()
      onFiles.unmount()
    })

    it('falls back to a supplied non-advanced tab when the list has no Chat, and stays put with none', async () => {
      useUserStore().currentUser = { role: 'admin' } as never
      useUiMode().setMode('full')
      const tabs = [
        { key: 'files', label: 'Files', icon: 'folder' },
        { key: 'terminal', label: 'Terminal', icon: 'terminal', adv: true },
      ]
      const w = mount(ChatTabs, { props: { activeTab: 'terminal', tabs }, attachTo: document.body, global: { plugins: [i18n] } })
      useUiMode().setMode('minimal')
      await flushPromises()
      expect(w.emitted('tab-change')).toEqual([['files']])
      w.unmount()
      useUiMode().setMode('full')
      const advOnly = mount(ChatTabs, { props: { activeTab: 'terminal', tabs: [tabs[1]] }, attachTo: document.body, global: { plugins: [i18n] } })
      useUiMode().setMode('minimal')
      await flushPromises()
      expect(advOnly.emitted('tab-change')).toBeUndefined()
      advOnly.unmount()
    })
  })
})
