// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatSessionRow (#18243): the title and message count, the current-chat mark, the selection
// checkbox, and the action menu that replaced the four hover buttons.
import { describe, it, expect } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
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

  it('puts the actions trigger in the Tab order only while its row is the tab stop', () => {
    expect(render({ focused: true }).get('[aria-label="Chat actions"]').attributes('tabindex')).toBe('0')
    expect(render().get('[aria-label="Chat actions"]').attributes('tabindex')).toBe('-1')
  })

  it('Enter on the trigger does not open the chat through the row', async () => {
    const w = render({ focused: true })
    const trigger = w.get('[aria-label="Chat actions"]')
    await trigger.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('keydown')?.length).toBe(1) // reported to the list, which ignores a nested target
    expect(w.emitted('open')).toBeUndefined()
    w.unmount()
  })

  it('marks the open chat with a 3px primary left border, surface fill and bold text, and no full border', () => {
    const w = render({ current: true })
    const row = w.get('[role="button"]')
    expect(row.classes()).toEqual(
      expect.arrayContaining(['border-s-[3px]', 'border-[var(--primary)]', 'bg-[var(--surface2)]', 'font-semibold']),
    )
    expect(row.classes()).not.toContain('border')
    expect(w.get('[aria-hidden="true"]').classes()).toContain('bg-[var(--accent)]')
    expect(render().get('[aria-hidden="true"]').classes()).toContain('bg-[var(--dot-idle)]')
  })

  it('does not use aria-selected, which is invalid on a button', () => {
    expect(render({ focused: true }).get('[role="button"]').attributes('aria-selected')).toBeUndefined()
  })

  describe('keyboard route to the actions menu', () => {
    const menu = () => document.querySelector('[role="menu"]')
    const press = async (w: ReturnType<typeof render>, init: KeyboardEventInit) => {
      w.get('[role="button"]').element.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }))
      await flushPromises()
    }

    it.each([
      ['ContextMenu', { key: 'ContextMenu' }],
      ['Shift+F10', { key: 'F10', shiftKey: true }],
    ])('%s on the focused row opens the menu without telling the list', async (_name, init) => {
      const w = render({ focused: true })
      await press(w, init)
      expect(menu()).not.toBeNull()
      expect(w.emitted('keydown')).toBeUndefined()
      w.unmount()
    })

    it('F10 alone is passed on to the list, and selection mode has no menu to open', async () => {
      const w = render()
      await press(w, { key: 'F10' })
      expect(w.emitted('keydown')).toHaveLength(1)
      expect(menu()).toBeNull()
      w.unmount()
      const sel = render({ selectionMode: true })
      await press(sel, { key: 'ContextMenu' })
      expect(menu()).toBeNull()
      sel.unmount()
    })

    it('Escape closes the menu and focus returns to the row', async () => {
      const w = render({ focused: true })
      await press(w, { key: 'ContextMenu' })
      menu()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
      await flushPromises()
      await new Promise((resolve) => setTimeout(resolve, 20))
      expect(menu()).toBeNull()
      expect(document.activeElement).toBe(w.get('[role="button"]').element)
      w.unmount()
    })
  })
})
