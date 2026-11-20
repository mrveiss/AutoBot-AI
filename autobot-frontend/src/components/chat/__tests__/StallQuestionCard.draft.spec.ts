// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** The typed answer survives the card being unmounted by the virtualised list and restored on mount (#21793). */

import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { setStallDraft } from '@/composables/chat/useStallDraft'
import StallQuestionCard from '../StallQuestionCard.vue'

vi.mock('@/composables/useGraphApproval', () => ({
  useStallAnswer: () => vi.fn(),
  ResumeRejectedError: class extends Error {},
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ isTyping: false }) }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountCard = (id: string) =>
  mount(StallQuestionCard, {
    props: { message: { id, content: 'Which way?', sender: 'assistant', type: 'human_question', metadata: {} } as never },
    global: { plugins: [i18n] },
  })

describe('StallQuestionCard draft', () => {
  beforeEach(() => {
    setStallDraft('m1', '')
    setStallDraft('m2', '')
  })

  it('restores the typed answer when the card mounts again', async () => {
    const first = mountCard('m1')
    await first.find('input').setValue('use host B')
    first.unmount() // scrolled out of the virtual window
    const second = mountCard('m1')
    expect((second.find('input').element as HTMLInputElement).value).toBe('use host B')
  })

  it('keeps one draft per message', async () => {
    const first = mountCard('m1')
    await first.find('input').setValue('answer one')
    const other = mountCard('m2')
    expect((other.find('input').element as HTMLInputElement).value).toBe('')
  })
})
