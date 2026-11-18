// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #13424: a browser screenshot keeps its ImageCell payload on the chat message.
// #21846: a message flagged metadata.internal is never shown, streamed or buffered.
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
import { isInternalMessage, visibleMessages } from '@/utils/internalMessage'

type Internals = {
  _processStreamLine(line: string, ids: Map<string, string>, fallback: string | null): string | null
  flushStreamUpdate(): void
  handleJsonResponse(data: Record<string, unknown>): void
}

function controller() {
  return new ChatController() as unknown as Internals
}

function feed(chunk: Record<string, unknown>) {
  const c = controller()
  c._processStreamLine(`data: ${JSON.stringify(chunk)}`, new Map(), null)
  c.flushStreamUpdate()
  return useChatStore().currentMessages
}

const marker = {
  type: 'segment_complete',
  content: 'x',
  metadata: { internal: true, completed_type: 'response', message_id: 'seg-1' }
}

describe('screenshot message (#13424)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useChatStore().createNewSession()
  })

  it('keeps display_type and the image_payload ImageCell reads', () => {
    const payload = { images: [{ url: 'data:image/png;base64,AAAA' }], provider: 'browser' }
    const messages = feed({
      type: 'command_output',
      content: 'Screenshot captured successfully.',
      metadata: { message_id: 'm1', display_type: 'image', image_payload: payload }
    })
    expect(messages).toHaveLength(1)
    expect(messages[0].metadata).toMatchObject({ display_type: 'image', image_payload: payload })
  })
})

describe('internal messages (#21846)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useChatStore().createNewSession()
  })

  it('a streamed internal message is not added', () => {
    expect(feed(marker)).toHaveLength(0)
  })

  it('a buffered internal workflow message reaches the store but never the visible list', () => {
    controller().handleJsonResponse({
      workflow_messages: [marker, { type: 'thought', content: 'thinking', metadata: {} }]
    })
    const all = useChatStore().currentMessages
    expect(all).toHaveLength(2)
    expect(visibleMessages(all).map((m) => m.type)).toEqual(['thought'])
  })

  it('the predicate flags only metadata.internal === true', () => {
    expect(isInternalMessage(marker)).toBe(true)
    expect(isInternalMessage({ metadata: { internal: 'yes' } })).toBe(false)
    expect(isInternalMessage({ metadata: {} })).toBe(false)
    expect(isInternalMessage(undefined)).toBe(false)
  })
})
