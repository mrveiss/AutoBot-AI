// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ChatMessageRow (#18243, step 5a batch 2): the bubble frame, header actions and send-status the stream had inline.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatMessageRow from '../ChatMessageRow.vue'
import type { ChatMessage } from '@/stores/useChatStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const msg = (over: Record<string, unknown> = {}) =>
  ({ id: 'm1', sender: 'assistant', content: 'hi', timestamp: '2026-01-01T10:00:00Z', ...over }) as unknown as ChatMessage
const render = (message: ChatMessage, slot = '<p class="body">body</p>') =>
  mount(ChatMessageRow, {
    props: { message },
    slots: { default: slot },
    global: { plugins: [i18n], stubs: { ProviderFallbackChip: true, MessageStatus: { template: '<button class="status" @click="$emit(\'retry\')">s</button>' } } },
  })

describe('ChatMessageRow', () => {
  it('carries the sender and type classes and renders the slot after the header', () => {
    const w = render(msg({ sender: 'user', type: 'thought' }))
    const root = w.get('.message-wrapper')
    expect(root.classes()).toEqual(expect.arrayContaining(['message', 'user-message', 'type-thought']))
    const kids = Array.from(root.element.children).map((c) => c.className)
    expect(kids[0]).toContain('message-header')
    expect(kids[kids.length - 1]).toBe('body')
  })

  it('offers Edit only on a user message; Copy and Delete on every one', () => {
    const labels = (w: ReturnType<typeof render>) => w.findAll('.message-actions button').map((b) => b.attributes('aria-label'))
    expect(labels(render(msg({ sender: 'user' })))).toEqual(['Edit message', 'Copy message', 'Delete message'])
    expect(labels(render(msg()))).toEqual(['Copy message', 'Delete message'])
  })

  it('emits the message for edit, copy and delete', async () => {
    const message = msg({ sender: 'user' })
    const w = render(message)
    const buttons = w.findAll('.message-actions button')
    for (const b of buttons) await b.trigger('click')
    expect(w.emitted('edit')?.[0]).toEqual([message])
    expect(w.emitted('copy')?.[0]).toEqual([message])
    expect(w.emitted('delete')?.[0]).toEqual([message])
  })

  it('shows the send status and its retry only for a user message', async () => {
    const user = render(msg({ sender: 'user', status: 'error' }))
    await user.get('.status').trigger('click')
    expect(user.emitted('retry')?.[0]).toEqual(['m1'])
    expect(render(msg()).find('.status').exists()).toBe(false)
  })

  it('shows the type badge for a typed message and none for a plain one', () => {
    expect(render(msg({ type: 'debug' })).text()).toContain('Debug')
    expect(render(msg()).find('[data-slot="badge"]').exists()).toBe(false)
  })
})
