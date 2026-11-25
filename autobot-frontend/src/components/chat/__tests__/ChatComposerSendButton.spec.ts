// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatComposerSendButton (#18243): the accessible name follows the state, a send emits once, and a disabled or
// loading button does not.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatComposerSendButton from '../ChatComposerSendButton.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = (props: Record<string, unknown>) =>
  mount(ChatComposerSendButton, { props, attachTo: document.body, global: { plugins: [i18n] } })

describe('ChatComposerSendButton', () => {
  it.each([
    [{ canSend: false, sending: false }, en.chat.input.enterMessage, true],
    [{ canSend: true, sending: false }, en.chat.input.sendMessage, false],
    [{ canSend: true, sending: true }, en.chat.input.sending, true],
  ])('%j is named %s and is disabled=%s', (props, name, disabled) => {
    const w = render(props)
    expect(w.attributes('aria-label')).toBe(name)
    expect(w.attributes('disabled') !== undefined).toBe(disabled)
    w.unmount()
  })

  it('emits send on click when it can send', async () => {
    const w = render({ canSend: true, sending: false })
    await w.trigger('click')
    expect(w.emitted('send')).toHaveLength(1)
    w.unmount()
  })

  it('shows the queued count only while idle and something is queued', () => {
    expect(render({ canSend: true, sending: false }).find('[data-testid="send-queue-count"]').exists()).toBe(false)
    const w = render({ canSend: true, sending: false, queueLength: 3 })
    expect(w.get('[data-testid="send-queue-count"]').text()).toBe('3')
    expect(w.classes()).toContain('animate-pulse')
    w.unmount()
  })
})
