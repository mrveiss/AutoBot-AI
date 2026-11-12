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
import { chatRepository } from '@/models/repositories'
import { keepUnansweredQuestions } from '../stallQuestions'

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

const question = (id: string, extra: Record<string, unknown> = {}) =>
  ({ id: `card-${id}`, type: 'human_question', content: 'How?', metadata: { question_id: id, ...extra } }) as never

describe('an unanswered question survives a history poll (#21022)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useChatStore().createNewSession()
  })

  it('keepUnansweredQuestions re-adds a local open card the loaded history lacks', () => {
    const loaded = [{ id: 'u1', type: 'message', metadata: {} }]
    const merged = keepUnansweredQuestions([question('q1')], loaded as never[])
    expect(merged.map((m: { id: string }) => m.id)).toEqual(['u1', 'card-q1'])
  })

  it('does not duplicate a card the history holds, nor keep an answered one', () => {
    const held = keepUnansweredQuestions([question('q1')], [question('q1')])
    expect(held).toHaveLength(1)
    const answered = keepUnansweredQuestions([question('q2', { answered: true })], [])
    expect(answered).toHaveLength(0)
  })

  it('a stale history response cannot reopen a question the person already answered (#21022)', () => {
    const local = [question('q1', { answered: true, answer_text: 'host B' })]
    const merged = keepUnansweredQuestions(local, [question('q1')]) // loaded before the answer was accepted
    expect(merged).toHaveLength(1)
    expect((merged[0] as { metadata?: object }).metadata).toMatchObject({ question_id: 'q1', answered: true, answer_text: 'host B' })
    const other = keepUnansweredQuestions(local, [question('q2')]) // control: another question is untouched
    expect((other[0] as { metadata?: { answered?: boolean } }).metadata?.answered).toBeUndefined()
  })

  it('loadChatMessages keeps the open card when the backend history is newer but lacks it', async () => {
    const store = useChatStore()
    const sessionId = store.currentSessionId as string
    const session = store.sessions.find((s) => s.id === sessionId)!
    session.messages = [question('q1')]
    vi.spyOn(chatRepository, 'getChatMessages').mockResolvedValue([
      { id: 'a', content: 'one', sender: 'user', timestamp: new Date() },
      { id: 'b', content: 'two', sender: 'assistant', timestamp: new Date() },
    ] as never)
    await new ChatController().loadChatMessages(sessionId)
    const types = store.sessions.find((s) => s.id === sessionId)!.messages.map((m) => m.type)
    expect(types).toContain('human_question')
    expect(store.sessions.find((s) => s.id === sessionId)!.messages).toHaveLength(3)
  })
})
