// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** The stall question card (#21022): an answer is emitted; an empty answer means stop; an answered card has no form. */

import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import StallQuestionCard from '../StallQuestionCard.vue'

const answerStallQuestion = vi.fn()
vi.mock('@/composables/useGraphApproval', () => ({ useStallAnswer: () => answerStallQuestion }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ isTyping: false }) }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountCard = (metadata: Record<string, unknown> = {}) =>
  mount(StallQuestionCard, {
    props: { message: { id: 'm1', content: 'Which way?', sender: 'assistant', type: 'human_question', metadata } as never },
    global: { plugins: [i18n] },
  })

describe('StallQuestionCard', () => {
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

  it('control: an answered card shows the answer and no form', () => {
    const wrapper = mountCard({ answered: true, answer_text: 'use host B' })
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('use host B')
  })
})
