// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatImageGenDialog (#18243): Ctrl+Enter submits committed text and never confirms an IME composition.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatImageGenDialog from '../ChatImageGenDialog.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = () =>
  mount(ChatImageGenDialog, {
    props: { open: true, prompt: 'a city', provider: 'dalle', generating: false },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })

describe('ChatImageGenDialog', () => {
  it('submits on Ctrl+Enter', () => {
    const w = render()
    const area = document.getElementById('image-gen-prompt')!
    area.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
    expect(w.emitted('submit')).toHaveLength(1)
    w.unmount()
  })

  it('ignores Ctrl+Enter while an IME composition is open', () => {
    const w = render()
    const area = document.getElementById('image-gen-prompt')!
    area.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, isComposing: true, bubbles: true }))
    expect(w.emitted('submit')).toBeUndefined()
    w.unmount()
  })
})
