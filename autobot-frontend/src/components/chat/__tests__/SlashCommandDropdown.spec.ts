// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SlashCommandDropdown (#18243): a listbox of preset options with the selected one marked, hover and click intents.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SlashCommandDropdown from '../SlashCommandDropdown.vue'
import type { SlashCommandPreset } from '@/types/api'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const presets = [
  { id: '1', name: 'summarize', description: 'Decisions and open items', content: 'x' },
  { id: '2', name: 'plan', description: 'Ask Overseer for a plan', content: 'y' },
] as unknown as SlashCommandPreset[]
const render = (props: Record<string, unknown> = {}) =>
  mount(SlashCommandDropdown, {
    props: { show: true, suggestions: presets, selectedIndex: 0, anchorEl: null, ...props },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })

describe('SlashCommandDropdown', () => {
  it('renders nothing while hidden', () => {
    const w = render({ show: false })
    expect(document.body.querySelector('[role="listbox"]')).toBeNull()
    w.unmount()
  })

  it('is a named listbox of options, with only the selected one aria-selected', () => {
    const w = render({ selectedIndex: 1 })
    const list = document.body.querySelector('[role="listbox"]')!
    expect(list.getAttribute('aria-label')).toBe(en.chat.input.slashSuggestions)
    const options = [...list.querySelectorAll('[role="option"]')]
    expect(options.map((o) => o.getAttribute('aria-selected'))).toEqual(['false', 'true'])
    expect(options[0].textContent).toContain('/summarize')
    // only options live inside the listbox: the heading and the key hint sit outside it
    expect([...list.children].every((c) => c.getAttribute('role') === 'option')).toBe(true)
    expect(document.body.textContent).toContain(en.chat.input.slashHint)
    w.unmount()
  })

  it('emits select on click and the hovered index on mouseenter', async () => {
    const w = render()
    const option = document.body.querySelectorAll('[role="option"]')[1] as HTMLElement
    option.dispatchEvent(new MouseEvent('mouseenter'))
    option.click()
    expect(w.emitted('update:selectedIndex')).toEqual([[1]])
    expect(w.emitted('select')?.[0]).toEqual([presets[1]])
    w.unmount()
  })
})
