// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatHeader (#18243): kit buttons with names and tooltips, advanced controls marked .adv, the
// Minimal-mode note with its way back, and the connection badge variant.
import { describe, it, expect, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatHeader from '../ChatHeader.vue'
import ChatHeaderActions from '../ChatHeaderActions.vue'
import { useUiMode } from '@/composables/useUiMode'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/useChatStore'
import { resetChatKnowledgeState, useChatKnowledge } from '@/composables/chat/useChatKnowledge'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = {
  currentSessionId: 's1', currentSessionTitle: 'Fleet check', sessionInfo: 'Session s1 - 3 messages', connectionStatus: 'Connected', isConnected: true,
}
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatHeader, { props: { ...base, ...props }, attachTo: document.body, global: { plugins: [i18n] } })

beforeEach(() => {
  useUiMode().setMode('full')
  setActivePinia(createPinia())
  resetChatKnowledgeState()
})

describe('ChatHeader', () => {
  it('shows Knowledge on or off from the state the composer chip shares (#18243)', async () => {
    const w = render()
    expect(w.get('[data-testid="header-knowledge"]').text()).toBe(en.chat.header.knowledgeOn)
    useChatKnowledge().enabled.value = false
    await flushPromises()
    expect(w.get('[data-testid="header-knowledge"]').text()).toBe(en.chat.header.knowledgeOff)
    w.unmount()
  })

  it('shows the Knowledge state of the current session when the chat is switched', async () => {
    const store = useChatStore()
    const a = store.createNewSession('A', 'session-a')
    useChatKnowledge().enabled.value = false
    const w = render()
    expect(w.get('[data-testid="header-knowledge"]').text()).toBe(en.chat.header.knowledgeOff)
    store.createNewSession('B', 'session-b')
    await flushPromises()
    expect(w.get('[data-testid="header-knowledge"]').text()).toBe(en.chat.header.knowledgeOn)
    store.switchToSession(a)
    await flushPromises()
    expect(w.get('[data-testid="header-knowledge"]').text()).toBe(en.chat.header.knowledgeOff)
    w.unmount()
  })

  it('shows the title and sub-line', () => {
    const w = render()
    expect(w.text()).toContain('Fleet check')
    expect(w.text()).toContain('Session s1')
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

  it('puts no toggle or disclosure state on the plain action buttons', () => {
    const w = render()
    for (const label of [en.chat.openSettings, en.chat.exportChat, en.chat.clearChat]) {
      const b = w.findAll('button').find((x) => x.attributes('aria-label') === label)!
      expect(b.attributes('aria-pressed')).toBeUndefined()
      expect(b.attributes('aria-expanded')).toBeUndefined()
    }
    w.unmount()
  })

  it('puts the sub-line above the title with real Overseer state and the start time', () => {
    const w = render({ overseerEnabled: true, startedAt: new Date(2026, 10, 21, 10, 42) })
    const html = w.html()
    expect(html.indexOf('Overseer on')).toBeLessThan(html.indexOf('Fleet check'))
    expect(w.text()).toContain('started')
    expect(w.text()).toContain('10:42')
    expect(w.text()).not.toContain('Knowledge')
    w.unmount()
  })

  it('shows Overseer off, and falls back to the session info without a start time', () => {
    const w = render({ overseerEnabled: false })
    expect(w.text()).toContain('Overseer off')
    expect(w.text()).toContain('Session s1 - 3 messages')
    w.unmount()
  })

  it('orders the buttons Export, Settings, Clear after the slotted ones', () => {
    const w = render()
    const labels = w.findAll('button').map((b) => b.attributes('aria-label')).filter(Boolean)
    const at = (l: string) => labels.indexOf(l)
    expect(at(en.chat.exportChat)).toBeLessThan(at(en.chat.openSettings))
    expect(at(en.chat.openSettings)).toBeLessThan(at(en.chat.clearChat))
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
    expect(w.emitted('restore-focus')).toHaveLength(1)
    w.unmount()
  })

  it('moves focus from the vanishing note button to the always-visible voice-output toggle', async () => {
    useUiMode().setMode('minimal')
    let fallback: HTMLElement | null = null
    const Harness = defineComponent({
      components: { ChatHeader, ChatHeaderActions },
      setup: () => ({ props: base, onEl: (panel: string, el: HTMLElement | null) => { if (panel === 'fallback') fallback = el }, restore: () => fallback?.focus() }),
      template: `<ChatHeader v-bind="props" @restore-focus="restore"><template #actions>
        <ChatHeaderActions :voice-output-enabled="false" :is-speaking="false" :voice-expanded="false" voice-controls-id="v"
          :has-session="true" :is-collaborative="false" :show-file-panel="false" :show-compare-panel="false"
          :show-collaboration-panel="false" @button-el="onEl" /></template></ChatHeader>`,
    })
    const w = mount(Harness, { attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()
    const note = w.get('.only-min button')
    ;(note.element as HTMLElement).focus()
    expect(document.activeElement).toBe(note.element)
    await note.trigger('click')
    expect((document.activeElement as HTMLElement).getAttribute('aria-label')).toBe(en.chat.interface.voiceOutputOff)
    w.unmount()
  })

  it.each([
    [{ isConnected: true, connectionStatus: 'Connected' }, 'success'],
    [{ isConnected: true, connectionStatus: 'Connecting' }, 'warning'],
    [{ isConnected: false, connectionStatus: 'Disconnected' }, 'error'],
  ])('shows %j as a %s badge', (props, variant) => {
    const w = render(props)
    expect(w.get('.aui-badge').classes()).toContain(`aui-badge--${variant}`)
    expect(w.get('.aui-badge').find('svg').exists()).toBe(false)
    w.unmount()
  })

  it('marks the context window indicator advanced', () => {
    const w = render({ contextWindowProps: { tokensUsed: 1, contextWindow: 10, usagePercent: 10, isWarning: false, isCritical: false, hasData: true } })
    expect(w.find('.adv .ctx-indicator').exists()).toBe(true)
    w.unmount()
  })
})

describe('ChatHeader mobile sidebar toggle (#18243)', () => {
  it('hides on desktop through an unstyled wrapper, not the tooltip root whose own display wins', () => {
    const w = render()
    const wrapper = w.get('[data-testid="mobile-sidebar-toggle"]')
    expect(wrapper.classes()).toContain('lg:hidden')
    const button = wrapper.get(`button[aria-label="${en.chat.sidebar.expandSidebar}"]`)
    expect(button.element.closest('.lg\\:hidden')).toBe(wrapper.element)
    expect(wrapper.element.firstElementChild?.classList.contains('lg:hidden')).toBe(false)
    w.unmount()
  })
})
