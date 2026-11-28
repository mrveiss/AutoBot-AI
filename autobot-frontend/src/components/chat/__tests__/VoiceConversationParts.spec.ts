// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the presentational parts the voice panel and the voice overlay share -- state ring, mic button, notices,
// hands-free controls and the mode controls.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { BaseSelectMenu } from '@autobot/ui'
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import VoiceStateRing from '../VoiceStateRing.vue'
import VoiceMicButton from '../VoiceMicButton.vue'
import VoiceConversationNotices from '../VoiceConversationNotices.vue'
import VoiceHandsFreeControls from '../VoiceHandsFreeControls.vue'
import VoiceModeControls from '../VoiceModeControls.vue'

const global = { mocks: { $t: (k: string, p?: unknown) => (p ? `${k}|${JSON.stringify(p)}` : k) }, stubs: { Icon: true } }

describe('VoiceStateRing (#22349)', () => {
  it.each(['idle', 'listening', 'processing', 'speaking'] as const)('carries the %s state class on the ring and the label', (state) => {
    const wrapper = mount(VoiceStateRing, { props: { state, icon: 'microphone', label: 'L' }, global })
    expect(wrapper.get('[data-testid="voice-state-ring"]').classes()).toContain(`voice-state__ring--${state}`)
    expect(wrapper.get('[data-testid="voice-state-label"]').classes()).toContain(`voice-state__label--${state}`)
    expect(wrapper.get('[data-testid="voice-state-label"]').text()).toBe('L')
  })
})

describe('VoiceMicButton (#22349)', () => {
  const mountMic = (state: 'idle' | 'listening' | 'processing' | 'speaking') =>
    mount(VoiceMicButton, { props: { state, icon: 'microphone', label: 'Listening', hint: 'Tap to stop' }, global })

  it('names the button with the label, shows the hint and emits click', async () => {
    const wrapper = mountMic('idle')
    const button = wrapper.get('[data-testid="voice-mic"]')
    expect(button.attributes('aria-label')).toBe('Listening')
    expect(wrapper.get('[data-testid="voice-hint"]').text()).toBe('Tap to stop')
    await button.trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('is disabled only while processing', () => {
    expect(mountMic('processing').get('[data-testid="voice-mic"]').attributes('disabled')).toBeDefined()
    expect(mountMic('speaking').get('[data-testid="voice-mic"]').attributes('disabled')).toBeUndefined()
  })

  it('shows the two pulse rings only while listening', () => {
    expect(mountMic('listening').findAll('[data-testid="voice-pulse"]')).toHaveLength(2)
    expect(mountMic('idle').findAll('[data-testid="voice-pulse"]')).toHaveLength(0)
  })
})

describe('VoiceConversationNotices (#22349)', () => {
  it('renders the error as an alert, and nothing else when the context is secure', () => {
    const wrapper = mount(VoiceConversationNotices, { props: { error: 'boom', showInsecureContext: false, origin: 'o' }, global })
    expect(wrapper.get('[data-testid="voice-error"]').attributes('role')).toBe('alert')
    expect(wrapper.find('[data-testid="voice-cert-warning"]').exists()).toBe(false)
  })

  it('renders the mic-blocked warning with the origin in the second step', () => {
    const wrapper = mount(VoiceConversationNotices, { props: { error: null, showInsecureContext: true, origin: 'https://host' }, global })
    expect(wrapper.find('[data-testid="voice-error"]').exists()).toBe(false)
    const warning = wrapper.get('[data-testid="voice-cert-warning"]')
    expect(warning.attributes('role')).toBe('status')
    expect(warning.text()).toContain('chat.voice.micBlocked')
    expect(warning.text()).toContain('https://host')
  })
})

describe('VoiceHandsFreeControls (#22349)', () => {
  const mountControls = (silenceMs = 1500) =>
    mount(VoiceHandsFreeControls, { props: { level: 0.5, silenceMs, label: 'Silence' }, global })

  it('names the level bar and shows the level', () => {
    const bar = mountControls().get('[role="progressbar"]')
    expect(bar.attributes('aria-label')).toBe('chat.voice.inputLevel')
    expect(bar.attributes('aria-valuenow')).toBe('50')
  })

  it('labels the slider and shows its value in seconds', () => {
    const wrapper = mountControls(1500)
    const slider = wrapper.get('[data-testid="voice-silence"]')
    expect(wrapper.get('label').attributes('for')).toBe(slider.attributes('id'))
    expect(wrapper.get('[data-testid="voice-silence-value"]').text()).toContain('"seconds":"1.5"')
  })

  it('emits the slider value as a number', async () => {
    const wrapper = mountControls()
    const slider = wrapper.get('[data-testid="voice-silence"]')
    ;(slider.element as HTMLInputElement).value = '2000'
    await slider.trigger('input')
    expect(wrapper.emitted('update:silenceMs')?.[0]).toEqual([2000])
  })
})

describe('VoiceModeControls (#22349)', () => {
  const mountModes = (connection: { connected: boolean } | null = null) =>
    mount(VoiceModeControls, {
      props: { mode: 'hands-free', language: 'en', connection },
      global: { ...global, mocks: { $t: (k: string) => k } },
    })

  it('offers the four modes in a labelled select and emits the chosen one', () => {
    const wrapper = mountModes()
    const select = wrapper.findComponent(BaseSelectMenu)
    expect((select.props('options') as { value: string }[]).map((o) => o.value)).toEqual([
      'walkie-talkie', 'hands-free', 'full-duplex', 'realtime-webrtc',
    ])
    expect(select.props('label')).toBe('chat.voice.conversationMode')
    select.vm.$emit('update:modelValue', 'full-duplex')
    expect(wrapper.emitted('update:mode')?.[0]).toEqual(['full-duplex'])
  })

  it('shows the language upper-cased', () => {
    expect(mountModes().get('[data-testid="voice-language"]').text()).toBe('EN')
  })

  it('shows the connection dot, named, only when there is a connection to report', () => {
    expect(mountModes().find('[data-testid="voice-connection"]').exists()).toBe(false)
    const dot = mountModes({ connected: true }).get('[data-testid="voice-connection"]')
    expect(dot.attributes('role')).toBe('img')
    expect(dot.attributes('aria-label')).toBe('chat.voice.connectionLabel')
    expect(dot.classes()).toContain('bg-[var(--aui-color-success)]')
  })
})
