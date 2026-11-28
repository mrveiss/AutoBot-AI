// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Issue #20865: the chat history list showed 1970. ChatRepository.getChatList() maps the backend
// entry (createdTime / lastModified) to createdAt / updatedAt; ChatController then re-mapped those
// from created_at / updated_at, which the repository never returns, giving Invalid Date (persisted
// as null and rehydrated as epoch 0). These tests run the REAL repository, controller and store.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args) }))
vi.mock('@/config/ssot-config', async importOriginal => ({
  ...(await importOriginal<typeof import('@/config/ssot-config')>()),
  getApiBase: () => '/api'
}))
vi.mock('@/utils/ApiClient', () => ({ default: { invalidateCache: vi.fn() } }))
vi.mock('@/composables/useRequestQueue', () => ({
  requestQueue: { enqueue: vi.fn(({ fn }: { fn: () => unknown }) => fn()) }
}))

import { ChatController } from '../ChatController'
import { ChatRepository } from '../../repositories/ChatRepository'
import { toSessionDate } from '../../repositories/sessionDates'
import { useChatStore } from '@/stores/useChatStore'

vi.mock('@/models/repositories', async () => {
  const mod = await import('../../repositories/ChatRepository')
  return { chatRepository: new mod.ChatRepository() }
})

// Shape emitted by chat_history/session_listing.py (camelCase keys, ISO strings).
const backendPayload = {
  sessions: [
    {
      chatId: 'chat-dated',
      name: 'Dated chat',
      messageCount: 3,
      createdTime: '2026-10-01T08:30:00+00:00',
      lastModified: '2026-11-05T17:45:10.123456+00:00'
    },
    { chatId: 'chat-undated', name: 'No time', messageCount: 0, createdTime: '', lastModified: '' },
    { chatId: 'chat-epoch', name: 'Epoch', messageCount: 0, createdTime: '1970-01-01T00:00:00+00:00' }
  ]
}

describe('chat history dates (#20865)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => backendPayload
    })
  })

  it('repository maps createdTime/lastModified to Date objects', async () => {
    const list = await new ChatRepository().getChatList()
    expect(list[0].createdAt).toEqual(new Date('2026-10-01T08:30:00+00:00'))
    expect(list[0].updatedAt).toEqual(new Date('2026-11-05T17:45:10.123456+00:00'))
  })

  it('the store keeps the dates the session files carry', async () => {
    await new ChatController().loadChatSessions()
    const dated = useChatStore().sessions.find(s => s.id === 'chat-dated')!
    expect(dated.createdAt).toEqual(new Date('2026-10-01T08:30:00+00:00'))
    expect(dated.updatedAt).toEqual(new Date('2026-11-05T17:45:10.123456+00:00'))
  })

  it('a session with no usable time is undated, never 1970 or Invalid Date', async () => {
    await new ChatController().loadChatSessions()
    for (const id of ['chat-undated', 'chat-epoch']) {
      const s = useChatStore().sessions.find(x => x.id === id)!
      expect(s.updatedAt).toBeUndefined()
    }
    expect(useChatStore().sessions.find(x => x.id === 'chat-epoch')!.createdAt).toBeUndefined()
  })

  it('toSessionDate prefers the first usable candidate', () => {
    expect(toSessionDate(undefined, 'garbage', '2026-01-02T00:00:00Z')).toEqual(new Date('2026-01-02T00:00:00Z'))
    expect(toSessionDate(undefined, '')).toBeUndefined()
  })
})
