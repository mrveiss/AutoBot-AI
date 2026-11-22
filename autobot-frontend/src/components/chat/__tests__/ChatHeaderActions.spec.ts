// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatHeaderActions + ChatHeaderIconButton (#18243): every icon-only button is named and has a
// tooltip, toggles reflect aria-pressed, advanced ones carry .adv, and intents are emitted.
import { describe, it, expect } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatHeaderActions from '../ChatHeaderActions.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = {
  voiceOutputEnabled: false, isSpeaking: false, voiceExpanded: false, voiceControlsId: 'voice-panel',
  hasSession: true, isCollaborative: true, showFilePanel: false, showComparePanel: false, showCollaborationPanel: false,
}
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatHeaderActions, { props: { ...base, ...props }, attachTo: document.body, global: { plugins: [i18n] } })
const btn = (w: ReturnType<typeof render>, label: string) =>
  w.findAll('button').find((b) => b.attributes('aria-label') === label)!

describe('ChatHeaderActions', () => {
  it('names every icon-only button', () => {
    const w = render()
    const buttons = w.findAll('button')
    expect(buttons).toHaveLength(5)
    expect(buttons.every((b) => !!b.attributes('aria-label'))).toBe(true)
    w.unmount()
  })

  it('reflects the panel state as aria-pressed and aria-expanded, keeping aria-controls', () => {
    const w = render({ showFilePanel: true, voiceExpanded: true })
    const file = btn(w, 'Toggle file panel')
    expect(file.attributes('aria-pressed')).toBe('true')
    expect(file.attributes('aria-expanded')).toBe('true')
    expect(file.attributes('aria-controls')).toBe('chat-panel-files')
    expect(btn(w, 'Voice chat').attributes('aria-controls')).toBe('voice-panel')
    expect(btn(w, en.chat.compare.toggleTitle).attributes('aria-pressed')).toBe('false')
    w.unmount()
  })

  it('marks Voice chat and Compare advanced, but not the file panel or voice output', () => {
    const w = render()
    const adv = w.findAll('.adv').map((el) => el.find('button').attributes('aria-label'))
    expect(adv.sort()).toEqual([en.chat.interface.voiceChat, en.chat.compare.toggleTitle].sort())
    w.unmount()
  })

  it('hides the file and collaboration toggles without a session / collaborative session', () => {
    const w = render({ hasSession: false, isCollaborative: false })
    expect(w.findAll('button')).toHaveLength(3)
    w.unmount()
  })

  it('emits the intents', async () => {
    const w = render()
    await btn(w, 'Toggle file panel').trigger('click')
    await btn(w, 'Collaboration').trigger('click')
    await btn(w, 'Voice chat').trigger('click')
    await btn(w, 'Voice output off').trigger('click')
    expect(w.emitted('toggle-panel')).toEqual([['files'], ['collaboration']])
    expect(w.emitted('toggle-voice-conversation')).toHaveLength(1)
    expect(w.emitted('toggle-voice-output')).toHaveLength(1)
    w.unmount()
  })

  it('reports each panel button element for focus return', async () => {
    const w = render()
    await flushPromises()
    // 'fallback' is the voice-output toggle, which stays visible in every mode (#18243).
    const reported = (w.emitted('button-el') ?? []).map((e) => e[0])
    expect([...new Set(reported)].sort()).toEqual(['collaboration', 'fallback', 'files', 'voice'])
    w.unmount()
  })

  it('shows a tooltip bubble naming the button when focused', async () => {
    const w = render()
    const bubble = () => document.querySelector('.aui-tooltip__bubble')
    expect(bubble()?.classList.contains('aui-tooltip__bubble--open')).toBeFalsy()
    await btn(w, 'Toggle file panel').trigger('focusin')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 0))
    const open = document.querySelector('.aui-tooltip__bubble--open')
    expect(open?.textContent).toContain('Toggle file panel')
    expect(btn(w, 'Toggle file panel').attributes('aria-describedby')).toBe(open?.id)
    w.unmount()
  })

  it('orders voice output, Voice, Files, collaboration, Compare (mockup order plus the extras beside their neighbour)', () => {
    const w = render()
    const labels = w.findAll('button').map((b) => b.attributes('aria-label'))
    expect(labels).toEqual(['Voice output off', 'Voice chat', 'Toggle file panel', 'Collaboration', en.chat.compare.toggleTitle])
    w.unmount()
  })
})

describe('ChatHeaderActions element reports (#18243)', () => {
  it('reports a button element, and null when the button unmounts with its session', async () => {
    const w = render({ hasSession: true })
    await flushPromises()
    const files = w.emitted('button-el')!.filter(([panel]) => panel === 'files')
    expect(files.at(-1)?.[1]).toBeInstanceOf(HTMLElement)
    await w.setProps({ hasSession: false })
    await flushPromises()
    expect(w.emitted('button-el')!.filter(([panel]) => panel === 'files').at(-1)?.[1]).toBeNull()
    w.unmount()
  })

  it('reports the voice-output toggle as the always-visible fallback', async () => {
    const w = render()
    await flushPromises()
    const fallback = w.emitted('button-el')!.find(([panel]) => panel === 'fallback')
    expect((fallback![1] as HTMLElement).getAttribute('aria-label')).toBe(en.chat.interface.voiceOutputOff)
    w.unmount()
  })
})
