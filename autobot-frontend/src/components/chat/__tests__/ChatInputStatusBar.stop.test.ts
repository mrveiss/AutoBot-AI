// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #17829 — a reply that is streaming can be stopped. The Stop control shows only while the
 * assistant is generating, and cancels the turn server-side (POST .../turn/cancel, #17273).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { post } }))

import ChatInputStatusBar from '../ChatInputStatusBar.vue'
import { useChatStore } from '@/stores/useChatStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const props = { typingVisible: false, characterCount: 0, maxCharacters: 4000, nearLimit: false, voiceRecording: false }

function mountBar() {
  return mount(ChatInputStatusBar, { props, global: { plugins: [i18n] } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  post.mockReset().mockResolvedValue({ success: true, data: { status: 'cancelled' } })
})

describe('Stop generating (#17829)', () => {
  it('is absent while the assistant is idle', () => {
    useChatStore().setTyping(false)
    expect(mountBar().find('[data-testid="stop-generating"]').exists()).toBe(false)
  })

  it('shows while a reply streams, labelled with the translated stopGenerating key', async () => {
    const store = useChatStore()
    store.setTyping(true)
    const wrapper = mountBar()
    expect(wrapper.get('[data-testid="stop-generating"]').text()).toContain(en.chat.stopGenerating)
    store.setTyping(false)
    await flushPromises()
    expect(wrapper.find('[data-testid="stop-generating"]').exists()).toBe(false)
  })

  it('cancels the current session turn on the server', async () => {
    const store = useChatStore()
    const sessionId = store.createNewSession('t', 'session-17829')
    store.setTyping(true)
    const wrapper = mountBar()
    await wrapper.get('[data-testid="stop-generating"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][0]).toMatch(new RegExp(`/chat/sessions/${sessionId}/turn/cancel$`))
    expect(wrapper.find('[data-testid="stop-failed"]').exists()).toBe(false)
  })

  it('says so when the stop request fails', async () => {
    post.mockRejectedValue(new Error('HTTP 500'))
    const store = useChatStore()
    store.createNewSession('t', 'session-fail')
    store.setTyping(true)
    const wrapper = mountBar()
    await wrapper.get('[data-testid="stop-generating"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="stop-failed"]').text()).toBe(en.chat.input.stopFailed)
  })
})
