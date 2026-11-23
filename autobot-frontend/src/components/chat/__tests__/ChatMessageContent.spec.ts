// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ChatMessageContent (#18243, step 5a batch 2): the branch order and the regular body the stream had inline.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/utils/chatMessageFormat', () => ({ formatChatMessageHtml: (c: string) => '<p>' + c + '</p>' }))
vi.mock('@/utils/sanitize', () => ({ sanitizeChatHtml: (h: string) => h }))

import ChatMessageContent from '../ChatMessageContent.vue'
import type { ChatMessage } from '@/stores/useChatStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const msg = (over: Record<string, unknown> = {}) =>
  ({ id: 'm1', sender: 'assistant', content: 'hello', timestamp: 't', ...over }) as unknown as ChatMessage
const stub = (name: string) => ({ name, template: '<div class="' + name + '"/>' })
const stubs = {
  OverseerPlanMessage: stub('plan'), OverseerStepMessage: stub('step'), StallQuestionCard: stub('question'),
  ImageCell: stub('image'), VideoCell: stub('video'), ChatMessageApproval: stub('approval'),
  CitationsDisplay: { template: '<button class="cites" @click="$emit(\'citation-click\', { step_id: \'s1\' })"/>' },
  MessageAttachments: stub('attachments'),
}
const render = (message: ChatMessage, props: Record<string, unknown> = {}) =>
  mount(ChatMessageContent, { props: { message, ...props }, global: { plugins: [i18n], stubs } })

describe('ChatMessageContent', () => {
  it.each([
    [{ type: 'overseer_plan', metadata: { plan: {} } }, '.plan'],
    [{ type: 'human_question' }, '.question'],
    [{ type: 'overseer_step', metadata: { step: {} } }, '.step'],
    [{ type: 'image', metadata: { image_payload: {} } }, '.image'],
    [{ metadata: { display_type: 'video', video_payload: {} } }, '.video'],
  ])('renders the typed branch %j', (over, selector) => {
    expect(render(msg(over)).find(selector).exists()).toBe(true)
  })

  it('falls through to the text body when a typed message has no payload', () => {
    const w = render(msg({ type: 'overseer_plan' }))
    expect(w.find('.plan').exists()).toBe(false)
    expect(w.find('.message-text').html()).toContain('<p>hello</p>')
  })

  it('renders the summary branch inside a details element', () => {
    const w = render(msg({ type: 'summary', content: 'the gist' }))
    expect(w.find('details.summary-details .summary-content').html()).toContain('the gist')
  })

  it('shows the streaming dots only for the last assistant message while typing', () => {
    expect(render(msg(), { isTyping: true, isLast: true }).find('.typing-dots').exists()).toBe(true)
    expect(render(msg(), { isTyping: true, isLast: false }).find('.typing-dots').exists()).toBe(false)
    expect(render(msg({ sender: 'user' }), { isTyping: true, isLast: true }).find('.typing-dots').exists()).toBe(false)
  })

  it('shows the metadata line only for an assistant message with showJson on', () => {
    const message = msg({ metadata: { tokens: 12, duration: 340 } })
    expect(render(message).find('.message-metadata').exists()).toBe(false)
    const text = render(message, { showJson: true }).get('.message-metadata').text()
    expect(text).toContain('340ms')
    expect(render(msg({ sender: 'user', metadata: { tokens: 1 } }), { showJson: true }).find('.message-metadata').exists()).toBe(false)
  })

  it('renders the approval block and attachments inside the text body', () => {
    const w = render(msg({ attachments: [{ id: 'a', name: 'f.txt', type: 'text/plain', size: 1, url: '' }] }))
    expect(w.find('.approval').exists()).toBe(true)
    expect(w.find('.attachments').exists()).toBe(true)
  })
})
