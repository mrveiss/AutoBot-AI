// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatHeader (#18243): kit buttons with names and tooltips, advanced controls marked .adv, the
// Minimal-mode note with its way back, and the connection badge variant.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatHeader from '../ChatHeader.vue'
import { useUiMode } from '@/composables/useUiMode'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = {
  currentSessionId: 's1', currentSessionTitle: 'Fleet check', sessionInfo: 'Overseer on', connectionStatus: 'Connected', isConnected: true,
}
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatHeader, { props: { ...base, ...props }, attachTo: document.body, global: { plugins: [i18n] } })

beforeEach(() => useUiMode().setMode('full'))

describe('ChatHeader', () => {
  it('shows the title and sub-line', () => {
    const w = render()
    expect(w.text()).toContain('Fleet check')
    expect(w.text()).toContain('Overseer on')
    w.unmount()
  })

  it('names every icon-only button, and marks Settings and Export advanced but not Clear', () => {
    const w = render()
    const icon = w.findAll('button').filter((b) => b.find('svg').exists() && !b.text())
    expect(icon.length).toBeGreaterThanOrEqual(4)
    expect(icon.every((b) => !!b.attributes('aria-label'))).toBe(true)
    const adv = w.findAll('.adv').map((el) => el.find('button').attributes('aria-label'))
    expect(adv).toEqual(expect.arrayContaining([en.chat.openSettings, en.chat.exportChat]))
    expect(adv).not.toContain(en.chat.clearChat)
    w.unmount()
  })

  it('emits settings, export and clear', async () => {
    const w = render()
    for (const label of [en.chat.openSettings, en.chat.exportChat, en.chat.clearChat]) {
      await w.findAll('button').find((b) => b.attributes('aria-label') === label)!.trigger('click')
    }
    expect(w.emitted('open-settings')).toHaveLength(1)
    expect(w.emitted('export-session')).toHaveLength(1)
    expect(w.emitted('clear-session')).toHaveLength(1)
    w.unmount()
  })

  it('has no session actions without a session', () => {
    const w = render({ currentSessionId: null })
    expect(w.find('[aria-label="' + en.chat.clearChat + '"]').exists()).toBe(false)
    w.unmount()
  })

  it('carries the Minimal-mode note with .only-min, and its button restores Full', async () => {
    useUiMode().setMode('minimal')
    const w = render()
    const note = w.get('.only-min')
    expect(note.text()).toContain(en.chat.header.essentialsNote)
    await note.get('button').trigger('click')
    expect(useUiMode().uiMode.value).toBe('full')
    w.unmount()
  })

  it.each([
    [{ isConnected: true, connectionStatus: 'Connected' }, 'success'],
    [{ isConnected: true, connectionStatus: 'Connecting' }, 'warning'],
    [{ isConnected: false, connectionStatus: 'Disconnected' }, 'error'],
  ])('shows %j as a %s badge', (props, variant) => {
    const w = render(props)
    expect(w.get('.aui-badge').classes()).toContain(`aui-badge--${variant}`)
    w.unmount()
  })

  it('marks the context window indicator advanced', () => {
    const w = render({ contextWindowProps: { tokensUsed: 1, contextWindow: 10, usagePercent: 10, isWarning: false, isCritical: false, hasData: true } })
    expect(w.find('.adv .ctx-indicator').exists()).toBe(true)
    w.unmount()
  })
})
