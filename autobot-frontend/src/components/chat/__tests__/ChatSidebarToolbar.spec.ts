// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatSidebarToolbar (#18243): New chat, the Select chats toggle and the title search.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatSidebarToolbar from '../ChatSidebarToolbar.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatSidebarToolbar, { props: { search: '', selectionMode: false, selectedCount: 0, ...props }, attachTo: document.body, global: { plugins: [i18n] } })

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
    expect(toggle.attributes('aria-pressed')).toBe('false')
    await toggle.trigger('click')
    expect(w.emitted('toggle-selection')).toHaveLength(1)
    w.unmount()
  })

  it('in selection mode offers Cancel and the selected count', () => {
    const w = render({ selectionMode: true, selectedCount: 3 })
    expect(w.get('[aria-label="Cancel"]').attributes('aria-pressed')).toBe('true')
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
})
