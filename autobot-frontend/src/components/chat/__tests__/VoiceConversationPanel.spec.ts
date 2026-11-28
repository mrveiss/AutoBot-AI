// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the "Voice chat" aside -- mode change, Close and Escape, the `adv` class, the hands-free controls only in
// hands-free mode, and no colour literal in the source. The `useVoiceConversation` transport is replaced by a fake.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createVoiceFake, type VoiceFake } from './voiceConversationFake'
import source from '../VoiceConversationPanel.vue?raw'

let fake: VoiceFake
vi.mock('@/composables/useVoiceConversation', () => ({ useVoiceConversation: () => fake }))
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import VoiceConversationPanel from '../VoiceConversationPanel.vue'

const mountPanel = () => mount(VoiceConversationPanel, { global: { mocks: { $t: (k: string) => k }, stubs: { Icon: true } } })

describe('VoiceConversationPanel (#22349)', () => {
  beforeEach(() => { fake = createVoiceFake() })

  it('is an advanced surface named by the title and shows the live status', () => {
    fake.stateLabel.value = 'Listening'
    const wrapper = mountPanel()
    const aside = wrapper.get('aside')
    expect(aside.classes()).toContain('adv')
    expect(aside.attributes('aria-label')).toBe('chat.voice.title')
    expect(wrapper.get('[data-testid="voice-status"]').text()).toBe('Listening')
  })

  it('Close deactivates the voice session and emits close', async () => {
    const wrapper = mountPanel()
    await wrapper.get('[data-testid="voice-close"] button').trigger('click')
    expect(fake.deactivate).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('Escape closes the same way', async () => {
    const wrapper = mountPanel()
    await wrapper.get('aside').trigger('keydown', { key: 'Escape' })
    expect(fake.deactivate).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('the mic button toggles listening', async () => {
    const wrapper = mountPanel()
    await wrapper.get('[data-testid="voice-mic"]').trigger('click')
    expect(fake.toggleListening).toHaveBeenCalledTimes(1)
  })

  it('renders the hands-free controls only in hands-free mode', async () => {
    const wrapper = mountPanel()
    expect(wrapper.find('[data-testid="voice-level"]').exists()).toBe(false)
    fake.mode.value = 'hands-free'
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="voice-level"]').exists()).toBe(true)
  })

  it('shows the live transcript only while there is one', async () => {
    const wrapper = mountPanel()
    expect(wrapper.find('[data-testid="voice-transcript"]').exists()).toBe(false)
    fake.currentTranscript.value = 'hello there'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="voice-transcript"]').text()).toContain('hello there')
  })

  it('cleans the session up when it unmounts', () => {
    mountPanel().unmount()
    expect(fake.cleanup).toHaveBeenCalledTimes(1)
  })

  it('holds no hex or rgb colour literal and no raw palette class', () => {
    // comments cite issue numbers (#22349 reads as a hex colour); only code is checked
    const code = source.replace(/<!--[\s\S]*?-->|\/\*[\s\S]*?\*\/|^\s*\/\/.*$/gm, '')
    expect(code).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(/)
    expect(code).not.toMatch(/\b(?:text|bg|border)-(?:red|green|blue|black|white)\b/)
  })
})
