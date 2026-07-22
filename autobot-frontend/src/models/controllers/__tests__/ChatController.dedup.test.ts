// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Issue #11843: an assistant reply rendered twice (two bubbles ~1min apart)
// because a poll / live-event echo re-added the SAME backend reply through the
// controller's JSON response path, which appended instead of dedupping.
//
// These tests drive the real ChatController against a REAL Pinia store (the
// sibling ChatController.test.ts fully mocks the store, so it cannot prove the
// dedup). Delivering the same backend `message_id` twice must leave ONE bubble.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ChatController } from '../ChatController'
import { useChatStore } from '@/stores/useChatStore'

// Mock only the heavy/side-effecting imports; the store stays REAL so the
// re-add path exercises the actual addOrUpdateMessage dedup logic.
vi.mock('@/models/repositories', () => ({
  chatRepository: {
    createNewChat: vi.fn(),
    sendMessage: vi.fn(),
    getChatList: vi.fn(),
    getChatMessages: vi.fn(),
    saveChatMessages: vi.fn(),
    deleteChat: vi.fn(),
    resetChat: vi.fn()
  }
}))

vi.mock('@/utils/ApiClient', () => ({
  default: { invalidateCache: vi.fn() }
}))

vi.mock('@/composables/useRequestQueue', () => ({
  requestQueue: {
    enqueue: vi.fn(({ fn }: { fn: () => unknown }) => fn())
  }
}))

// handleJsonResponse is private; drive it directly via a narrow cast.
type JsonResponseDriver = {
  handleJsonResponse: (data: Record<string, unknown>) => void
}

describe('ChatController JSON-response re-add dedup - #11843', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders ONE assistant bubble when the same backend message_id arrives twice', () => {
    const store = useChatStore()
    store.createNewSession('Echo Session')

    const controller = new ChatController() as unknown as JsonResponseDriver
    const reply = {
      content: 'The grounded answer is 42.',
      message_id: 'srv-echo-11843',
      model: 'test-model'
    }

    // First delivery: normal JSON response path.
    controller.handleJsonResponse(reply)
    // Second delivery: a poll / live-event echo of the SAME reply (same id).
    controller.handleJsonResponse(reply)

    const assistantBubbles = store.currentMessages.filter(m => m.sender === 'assistant')
    expect(assistantBubbles).toHaveLength(1)
    expect(assistantBubbles[0].content).toBe('The grounded answer is 42.')
  })

  it('renders ONE bubble when the id surfaces as `id` then as `message_id`', () => {
    const store = useChatStore()
    store.createNewSession('Echo Session')

    const controller = new ChatController() as unknown as JsonResponseDriver

    // Stream/normal path carries the server id in `id`...
    controller.handleJsonResponse({ content: 'Same reply.', id: 'srv-mix-11843' })
    // ...the echo carries the SAME id in `message_id`.
    controller.handleJsonResponse({ content: 'Same reply.', message_id: 'srv-mix-11843' })

    const assistantBubbles = store.currentMessages.filter(m => m.sender === 'assistant')
    expect(assistantBubbles).toHaveLength(1)
  })
})
