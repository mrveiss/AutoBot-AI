// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #21022: a `human_question` stream chunk becomes a message of that type carrying the question metadata the card needs.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/utils/ApiClient', () => ({ default: { invalidateCache: vi.fn() } }))
vi.mock('@/composables/useRequestQueue', () => ({
  requestQueue: { enqueue: vi.fn(({ fn }: { fn: () => unknown }) => fn()) }
}))
vi.mock('@/models/repositories', async () => {
  const mod = await import('../../repositories/ChatRepository')
  return { chatRepository: new mod.ChatRepository() }
})

import { ChatController } from '../ChatController'
import { useChatStore } from '@/stores/useChatStore'

type Internals = {
  _processStreamLine(line: string, ids: Map<string, string>, fallback: string | null): string | null
  flushStreamUpdate(): void
}

function feed(chunk: Record<string, unknown>) {
  const controller = new ChatController() as unknown as Internals
  controller._processStreamLine(`data: ${JSON.stringify(chunk)}`, new Map(), null)
  controller.flushStreamUpdate()
  return useChatStore().currentMessages
}

describe('ChatController human_question (#21022)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useChatStore().createNewSession()
  })

  it('yields a human_question message with the question metadata', () => {
    const messages = feed({
      type: 'human_question',
      content: 'How should I proceed?',
      metadata: { session_id: 's1', question_id: 'q1' }
    })
    const card = messages.find((m) => m.type === 'human_question')
    expect(card?.content).toBe('How should I proceed?')
    expect(card?.metadata).toMatchObject({ session_id: 's1', question_id: 'q1' })
  })

  it('control: an ordinary response chunk is not a question', () => {
    const messages = feed({ type: 'response', content: 'hello', metadata: {} })
    expect(messages.some((m) => m.type === 'human_question')).toBe(false)
  })
})
