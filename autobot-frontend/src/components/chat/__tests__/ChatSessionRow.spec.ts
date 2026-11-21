// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatSessionRow (#18243): the title and message count, the current-chat mark, the selection
// checkbox, and the action menu that replaced the four hover buttons.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatSessionRow from '../ChatSessionRow.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = { title: 'NPU plan', messageCount: 22, current: false, selected: false, selectionMode: false, focused: false, folders: [] }
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatSessionRow, { props: { ...base, ...props }, attachTo: document.body, global: { plugins: [i18n] } })

describe('ChatSessionRow', () => {
  it('shows the title and the message count', () => {
    const w = render()
    expect(w.text()).toContain('NPU plan')
    expect(w.text()).toContain('22 msgs')
    w.unmount()
  })

  it('marks the open chat with aria-current and is a roving-tabindex button', () => {
    const w = render({ current: true, focused: true })
    const row = w.get('[role="button"]')
    expect(row.attributes('aria-current')).toBe('page')
    expect(row.attributes('tabindex')).toBe('0')
    expect(render().get('[role="button"]').attributes('tabindex')).toBe('-1')
    w.unmount()
  })

  it('emits open on click and keydown intents', async () => {
    const w = render()
    await w.get('[role="button"]').trigger('click')
    await w.get('[role="button"]').trigger('keydown', { key: 'ArrowDown' })
    expect(w.emitted('open')).toHaveLength(1)
    expect(w.emitted('keydown')).toHaveLength(1)
    w.unmount()
  })

  it('in selection mode shows a named checkbox and no action menu', async () => {
    const w = render({ selectionMode: true, selected: true })
    const box = w.get('input[type="checkbox"]')
    expect((box.element as HTMLInputElement).checked).toBe(true)
    expect(box.attributes('aria-label')).toBe('NPU plan')
    await box.trigger('click')
    expect(w.emitted('toggle-select')).toHaveLength(1)
    expect(w.emitted('open')).toBeUndefined()
    expect(w.find('[aria-label="Chat actions"]').exists()).toBe(false)
    w.unmount()
  })

  it('has a named actions button that does not open the chat', async () => {
    const w = render()
    const actions = w.get('[aria-label="Chat actions"]')
    await actions.trigger('click')
    expect(w.emitted('open')).toBeUndefined()
    w.unmount()
  })
})
