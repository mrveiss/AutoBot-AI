// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** The stall question card (#21022): an answer is emitted; an empty answer means stop; an answered card has no form. */

import { beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import StallQuestionCard from '../StallQuestionCard.vue'

// vi.mock factories are hoisted above the imports and top-level declarations, so what they reference is built here too.
const { answerStallQuestion, FakeRejected } = vi.hoisted(() => {
  class FakeRejected extends Error {
    constructor(readonly status: number) {
      super(`resume failed: ${status}`)
    }
  }
  return { answerStallQuestion: vi.fn(), FakeRejected }
})
vi.mock('@/composables/useGraphApproval', () => ({
  useStallAnswer: () => answerStallQuestion,
  ResumeRejectedError: FakeRejected,
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ isTyping: false }) }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountCard = (metadata: Record<string, unknown> = {}) =>
  mount(StallQuestionCard, {
    props: { message: { id: 'm1', content: 'Which way?', sender: 'assistant', type: 'human_question', metadata } as never },
    global: { plugins: [i18n] },
  })

describe('StallQuestionCard', () => {
  beforeEach(() => {
    answerStallQuestion.mockReset() // call counts must not leak between tests
  })

  it('emits the typed answer', async () => {
    const wrapper = mountCard({})
    await wrapper.find('input').setValue('use host B')
    await wrapper.find('form').trigger('submit')
    expect(answerStallQuestion).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'm1' }), 'use host B')
  })

  it('emits an empty answer for "stop here"', async () => {
    const wrapper = mountCard({})
    const stop = wrapper.findAll('button').find((b) => b.text() === en.chat.stallQuestion.stop)
    await stop!.trigger('click')
    expect(answerStallQuestion).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'm1' }), '')
  })

  it('failure: a rejected answer keeps the form, shows the error and allows a retry', async () => {
    answerStallQuestion.mockRejectedValueOnce(new Error('resume failed: 500'))
    const wrapper = mountCard()
    await wrapper.find('input').setValue('use host B')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe(en.chat.stallQuestion.failed)
    expect(wrapper.find('form').exists()).toBe(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(answerStallQuestion).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('a policy block (400) tells the person to reword the answer and keeps the form', async () => {
    answerStallQuestion.mockRejectedValueOnce(new FakeRejected(400))
    const wrapper = mountCard()
    await wrapper.find('input').setValue('blocked text')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe(en.chat.stallQuestion.blocked)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('a question that is no longer pending (409) says so instead of the generic failure', async () => {
    answerStallQuestion.mockRejectedValueOnce(new FakeRejected(409))
    const wrapper = mountCard()
    await wrapper.find('input').setValue('late answer')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe(en.chat.stallQuestion.stale)
  })

  it('control: an answered card shows the answer and no form', () => {
    const wrapper = mountCard({ answered: true, answer_text: 'use host B' })
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('use host B')
  })
})
