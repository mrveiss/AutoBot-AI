// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ChatMessages (#18243, step 5a batch 2): the stream keeps the message order, shows the empty state and the typing
// indicator, and its approval context is provided once for every row.
import { describe, it, expect, vi } from 'vitest'
import { computed, reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({ store: null as unknown }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => h.store }))
vi.mock('@/composables/useDisplaySettings', () => ({ useDisplaySettings: () => ({ displaySettings: { value: { showJson: true } }, getSetting: () => false }) }))
vi.mock('@/composables/useProviderFallbackChip', () => ({ useProviderFallbackChip: () => ({ start: () => () => {}, getFallbackForMessage: () => null }) }))
vi.mock('@/composables/chat/useChatMessageActions', () => ({
  useChatMessageActions: () => ({ copyMessage: vi.fn(), deleteMessage: vi.fn(), retryMessage: vi.fn(), saveEdit: vi.fn() }),
}))
vi.mock('@/composables/chat/useMessageApprovalContext', () => ({ provideMessageApproval: () => ({ permissionStore: { initialize: vi.fn(), isEnabled: false } }) }))
vi.mock('@/composables/useVirtualChatScroll', () => ({
  useVirtualChatScroll: ({ filteredMessages }: { filteredMessages: { value: unknown[] } }) => ({
    virtualItems: computed(() => filteredMessages.value.map((_, index) => ({ key: index, index, start: index * 10 }))),
    totalSize: computed(() => filteredMessages.value.length * 10), measureElement: vi.fn(), scrollToBottom: vi.fn(), scrollToStep: vi.fn(),
  }),
}))

import ChatMessages from '../ChatMessages.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const mk = (id: string, sender = 'assistant') => ({ id, sender, content: id, timestamp: 't' })
function render(messages: unknown[], isTyping = false) {
  h.store = reactive({ currentMessages: messages, currentSessionId: 's1', isTyping, streamingPreview: '', sessions: [] })
  return mount(ChatMessages, {
    global: {
      plugins: [i18n],
      stubs: {
        ChatMessageRow: { props: ['message'], template: '<section class="row">{{ message.id }}<slot/></section>' },
        ChatMessageContent: { props: ['message', 'isLast'], template: '<i class="content" :data-last="isLast"/>' },
        ChatMessageEditModal: true, TypingIndicator: { template: '<div class="typing"/>' }, StableLoadingState: true, SkeletonLoader: true,
      },
    },
  })
}

describe('ChatMessages stream', () => {
  it('shows the empty state for an idle empty chat', () => {
    expect(render([]).find('[role="log"]').exists()).toBe(false)
  })

  it('renders the messages in store order and flags only the last one', () => {
    const w = render([mk('a'), mk('b', 'user'), mk('c')])
    expect(w.findAll('.row').map((r) => r.text())).toEqual(['a', 'b', 'c'])
    expect(w.findAll('.content').map((c) => c.attributes('data-last'))).toEqual(['false', 'false', 'true'])
    expect(w.find('[role="log"]').attributes('aria-live')).toBe('polite')
  })

  it('appends a streamed message to the end and shows the typing indicator while typing', async () => {
    const w = render([mk('a')], true)
    expect(w.find('.typing').exists()).toBe(true)
    ;(h.store as { currentMessages: unknown[] }).currentMessages.push(mk('b'))
    await w.vm.$nextTick()
    expect(w.findAll('.row').map((r) => r.text())).toEqual(['a', 'b'])
  })

  it('hides internal-marker and display-gated messages', () => {
    const w = render([mk('a'), { ...mk('b'), type: 'debug' }])
    expect(w.findAll('.row').map((r) => r.text())).toEqual(['a'])
  })
})
