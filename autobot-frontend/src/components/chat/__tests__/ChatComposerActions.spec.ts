// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatComposerActions (#18243): every icon-only button is named; voice reflects aria-pressed; the advanced tools
// carry .adv; intents are emitted; busy state disables the tools but never the Stop-recording button.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('../McpPromptPicker.vue', () => ({ default: { name: 'McpPromptPicker', props: ['disabled'], template: '<span class="mcp-stub" />' } }))

import ChatComposerActions from '../ChatComposerActions.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = { disabled: false, voiceRecording: false, imageGenerating: false, emojiOpen: false, quickActions: [] }
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatComposerActions, { props: { ...base, ...props }, attachTo: document.body, global: { plugins: [i18n] } })
const btn = (w: ReturnType<typeof render>, label: string) => w.findAll('button').find((b) => b.attributes('aria-label') === label)!

describe('ChatComposerActions', () => {
  it('names every icon-only button', () => {
    const w = render()
    const buttons = w.findAll('button')
    expect(buttons.length).toBeGreaterThanOrEqual(6)
    expect(buttons.every((b) => !!b.attributes('aria-label'))).toBe(true)
    w.unmount()
  })

  it('emits an intent per button', async () => {
    const w = render()
    const intents: [string, string][] = [
      [en.chat.input.attachFile, 'attach'], [en.chat.input.voiceInput, 'voice'], [en.chat.input.analyzeImage, 'vision'],
      [en.chat.input.managePresets, 'presets'], [en.chat.input.generateImage, 'image'], [en.chat.input.addEmoji, 'emoji'],
    ]
    for (const [label, event] of intents) {
      await btn(w, label).trigger('click')
      expect(w.emitted(event), event).toHaveLength(1)
    }
    w.unmount()
  })

  it('reflects recording as a pressed voice button with the stop icon, and keeps it clickable while busy', () => {
    const w = render({ voiceRecording: true, disabled: true })
    const voice = btn(w, en.chat.input.voiceInput)
    expect(voice.attributes('aria-pressed')).toBe('true')
    expect(voice.attributes('disabled')).toBeUndefined()
    expect(btn(w, en.chat.input.attachFile).attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('disables image generation while one is generating', () => {
    const w = render({ imageGenerating: true })
    expect(btn(w, en.chat.input.generateImage).attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('marks the advanced tools .adv and keeps attach, voice and emoji visible in Minimal mode', () => {
    const w = render()
    const wrapperOf = (label: string) => btn(w, label).element.closest('.adv')
    expect(wrapperOf(en.chat.input.analyzeImage)).not.toBeNull()
    expect(wrapperOf(en.chat.input.managePresets)).not.toBeNull()
    expect(wrapperOf(en.chat.input.generateImage)).not.toBeNull()
    expect(wrapperOf(en.chat.input.attachFile)).toBeNull()
    expect(wrapperOf(en.chat.input.voiceInput)).toBeNull()
    expect(wrapperOf(en.chat.input.addEmoji)).toBeNull()
    w.unmount()
  })

  it('tags the emoji button so a click on it is not an outside click, and exposes its open state', () => {
    const w = render({ emojiOpen: true })
    const emoji = btn(w, en.chat.input.addEmoji)
    expect(emoji.element.closest('[data-emoji-trigger]')).not.toBeNull()
    expect(emoji.attributes('aria-expanded')).toBe('true')
    w.unmount()
  })
})
