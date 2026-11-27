// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the voice overlay -- shown only while the voice session is active, bubbles, Close and Escape, the mode
// setter, the hands-free controls only in hands-free mode, and no colour literal in the source.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createVoiceFake, type VoiceFake } from './voiceConversationFake'
import source from '../VoiceConversationOverlay.vue?raw'

let fake: VoiceFake
vi.mock('@/composables/useVoiceConversation', () => ({ useVoiceConversation: () => fake }))
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import VoiceConversationOverlay from '../VoiceConversationOverlay.vue'

const find = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const mountOverlay = () =>
  mount(VoiceConversationOverlay, {
    attachTo: document.body,
    global: { mocks: { $t: (k: string) => k }, stubs: { Icon: true, Transition: false, TransitionGroup: false } },
  })

describe('VoiceConversationOverlay (#22349)', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    fake = createVoiceFake()
  })

  it('renders nothing while the voice session is inactive', () => {
    fake.isActive.value = false
    const wrapper = mountOverlay()
    expect(find('#chat-overlay-voice')).toBeNull()
    wrapper.unmount()
  })

  it('is a modal dialog named by the title with the live status', () => {
    fake.stateLabel.value = 'Speaking'
    const wrapper = mountOverlay()
    const dialog = find('[role="dialog"]')!
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.getAttribute('aria-label')).toBe('chat.voice.title')
    expect(find('[data-testid="voice-status"]')?.textContent).toBe('Speaking')
    wrapper.unmount()
  })

  it('lists the conversation bubbles', () => {
    fake.bubbles.value = [
      { id: '1', sender: 'user', content: 'hi' },
      { id: '2', sender: 'assistant', content: 'hello' },
    ]
    const wrapper = mountOverlay()
    expect(document.body.querySelectorAll('.voice-overlay__bubble')).toHaveLength(2)
    expect(find('.voice-overlay__bubble--assistant')?.textContent).toContain('hello')
    wrapper.unmount()
  })

  it('Close deactivates the session and emits close; Escape does the same', async () => {
    const wrapper = mountOverlay()
    find('[data-testid="voice-close"]')!.click()
    expect(fake.deactivate).toHaveBeenCalledTimes(1)
    find('#chat-overlay-voice')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(fake.deactivate).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('close')).toHaveLength(2)
    wrapper.unmount()
  })

  it('the mic button toggles listening', () => {
    const wrapper = mountOverlay()
    find('[data-testid="voice-mic"]')!.click()
    expect(fake.toggleListening).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('renders the hands-free controls only in hands-free mode', async () => {
    const wrapper = mountOverlay()
    expect(find('[data-testid="voice-level"]')).toBeNull()
    fake.mode.value = 'hands-free'
    await wrapper.vm.$nextTick()
    expect(find('[data-testid="voice-level"]')).not.toBeNull()
    wrapper.unmount()
  })

  it('holds no hex or rgb colour literal and no raw palette class', () => {
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(/)
    expect(source).not.toMatch(/\b(?:text|bg|border)-(?:red|green|blue|black|white)\b/)
  })
})
