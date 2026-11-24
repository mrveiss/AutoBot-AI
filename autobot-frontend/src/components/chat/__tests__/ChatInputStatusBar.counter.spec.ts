// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatInputStatusBar (#18243): the character counter appears with the first character, names the room left near
// the limit, and the recording and typing hints follow their props.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useStopGeneration', async () => {
  const { ref } = await import('vue')
  return { useStopGeneration: () => ({ stopping: ref(false), failed: ref(false), stop: vi.fn() }) }
})

import ChatInputStatusBar from '../ChatInputStatusBar.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = { typingVisible: false, characterCount: 0, maxCharacters: 4000, nearLimit: false, voiceRecording: false }
const render = (props: Record<string, unknown> = {}) => {
  setActivePinia(createPinia())
  return mount(ChatInputStatusBar, { props: { ...base, ...props }, global: { plugins: [i18n] } })
}

describe('ChatInputStatusBar', () => {
  it('shows no counter for an empty draft', () => {
    expect(render().find('[data-testid="character-count"]').exists()).toBe(false)
  })

  it('shows count/limit, with no room-left text below the limit zone', () => {
    const w = render({ characterCount: 182 })
    expect(w.get('[data-testid="character-count"]').text()).toBe('182/4000')
    expect(w.get('[data-testid="character-count"]').classes()).not.toContain('text-[var(--aui-color-warning)]')
  })

  it('names the room left and warns near the limit', () => {
    const w = render({ characterCount: 3870, nearLimit: true })
    const count = w.get('[data-testid="character-count"]')
    expect(count.text()).toBe('3870/4000 · 130 left')
    expect(count.classes()).toContain('text-[var(--aui-color-warning)]')
  })

  it('shows the typing and recording hints from their props', () => {
    const w = render({ typingVisible: true, voiceRecording: true })
    expect(w.text()).toContain(en.chat.input.typing)
    expect(w.text()).toContain(en.chat.input.recording)
  })
})
