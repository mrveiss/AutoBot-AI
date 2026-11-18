// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #19951: one held call is one approval card; re-emitting the card or resuming the turn never makes a second prompt.
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

const card = {
  id: 'approval-0123456789abcdef',
  type: 'command_approval_request',
  content: 'click #buy',
  metadata: { command: 'click {"selector": "#buy"}', session_id: 's1' }
}

function stream(chunks: Record<string, unknown>[], ids = new Map<string, string>()) {
  const controller = new ChatController() as unknown as Internals
  let fallback: string | null = null
  for (const chunk of chunks) {
    fallback = controller._processStreamLine(`data: ${JSON.stringify(chunk)}`, ids, fallback)
  }
  controller.flushStreamUpdate()
  return useChatStore().currentMessages.filter((m) => m.type === 'command_approval_request')
}

describe('approval card identity (#19951)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useChatStore().createNewSession()
  })

  it('the same card emitted twice in one stream is one card', () => {
    expect(stream([card, card])).toHaveLength(1)
  })

  it('a resume stream that carries the answer and no card adds no second card', () => {
    expect(stream([card])).toHaveLength(1)
    const resumed = stream([{ type: 'response', content: 'done', metadata: {} }])
    expect(resumed).toHaveLength(1)
  })
})
