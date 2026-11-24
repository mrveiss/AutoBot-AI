// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatSidebarToolbar (#18243): New chat, the Select chats toggle and the title search.
import { describe, it, expect } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatSidebarToolbar from '../ChatSidebarToolbar.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatSidebarToolbar, { props: { search: '', selectionMode: false, selectedCount: 0, hasCurrentSession: true, ...props }, attachTo: document.body, global: { plugins: [i18n] } })

describe('ChatSidebarToolbar', () => {
  it('emits new-chat from the primary button', async () => {
    const w = render()
    await w.get('.aui-btn--primary').trigger('click')
    expect(w.emitted('new-chat')).toHaveLength(1)
    w.unmount()
  })

  it('toggles selection mode from a named, pressed-aware icon button', async () => {
    const w = render()
    const toggle = w.get('[aria-label="Select chats"]')
    expect(toggle.attributes('aria-pressed')).toBeUndefined()
    await toggle.trigger('click')
    expect(w.emitted('toggle-selection')).toHaveLength(1)
    w.unmount()
  })

  it('in selection mode offers Cancel and the selected count', async () => {
    const w = render({ selectionMode: true, selectedCount: 3 })
    const cancel = w.get('[aria-label="Cancel"]')
    expect(cancel.attributes('aria-pressed')).toBeUndefined()
    await cancel.trigger('click')
    expect(w.emitted('toggle-selection')).toHaveLength(1)
    expect(w.text()).toContain('3 selected')
    w.unmount()
  })

  it('searches by title through a named search input', async () => {
    const w = render()
    const input = w.get('input[type="search"]')
    expect(input.attributes('aria-label')).toBe('Search chats')
    await input.setValue('npu')
    expect(w.emitted('update:search')?.[0]).toEqual(['npu'])
    w.unmount()
  })

  describe('the More menu (Reset, Delete, Refresh)', () => {
    const open = async (w: ReturnType<typeof render>) => {
      w.get('[aria-label="More actions"]').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
      await flushPromises()
    }
    const items = () => Array.from(document.querySelectorAll('[role="menuitem"]'))

    it('is advanced-only and lists the three kept actions', async () => {
      const w = render()
      expect(w.get('[aria-label="More actions"]').classes()).toContain('adv')
      await open(w)
      expect(items().map((i) => i.textContent?.trim())).toEqual(['Reset Chat', 'Delete Chat', 'Refresh List'])
      w.unmount()
    })

    it('emits the intent for each item', async () => {
      const w = render()
      await open(w)
      ;(items()[2] as HTMLElement).click()
      await flushPromises()
      expect(w.emitted('refresh')).toHaveLength(1)
      w.unmount()
    })

    it('disables Reset and Delete without an open chat, but not Refresh', async () => {
      const w = render({ hasCurrentSession: false })
      await open(w)
      expect(items().map((i) => i.hasAttribute('data-disabled'))).toEqual([true, true, false])
      w.unmount()
    })
  })

  it('in selection mode shows Delete N selected instead, disabled with nothing selected', async () => {
    const none = render({ selectionMode: true, selectedCount: 0 })
    expect(none.find('[aria-label="More actions"]').exists()).toBe(false)
    expect(none.get('[aria-label="Delete Selected"]').attributes('disabled')).toBeDefined()
    none.unmount()
    const some = render({ selectionMode: true, selectedCount: 2 })
    await some.get('[aria-label="Delete Selected"]').trigger('click')
    expect(some.emitted('delete-selected')).toHaveLength(1)
    some.unmount()
  })

  it('has a search icon before the field', () => {
    const w = render()
    expect(w.get('input[type="search"]').element.parentElement?.querySelector('svg')).not.toBeNull()
    w.unmount()
  })
})
