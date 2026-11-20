// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #21846: the backend stores each message time as ISO-8601 UTC with microseconds and a zone
 * (`2026-11-20T19:34:41.981705+00:00`). The reader must take it as that instant and keep messages that share a
 * second in their stored order.
 */
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api', getBackendUrl: () => 'http://backend' }))

import { ChatRepository } from '../ChatRepository'

const entry = (id: string, timestamp: string, messageType = 'response') => ({
  id,
  sender: 'assistant',
  text: id,
  messageType,
  timestamp,
  metadata: {}
})

async function load(entries: ReturnType<typeof entry>[]) {
  const repo = new ChatRepository()
  vi.spyOn(repo as unknown as { get: () => Promise<unknown> }, 'get').mockResolvedValue({
    data: { messages: entries }
  })
  return repo.getChatMessages('chat-1')
}

describe('ChatRepository.getChatMessages timestamps (#21846)', () => {
  it('reads the zone-carrying microsecond form as the right instant', async () => {
    const [message] = await load([entry('a', '2026-11-20T19:34:41.981705+00:00')])
    expect(message.timestamp.getTime()).toBe(Date.UTC(2026, 10, 20, 19, 34, 41, 981))
  })

  it('reads an offset form as the same instant as its UTC form', async () => {
    const [utc, riga] = await load([
      entry('a', '2026-11-20T19:34:41.981705+00:00'),
      entry('b', '2026-11-20T21:34:41.981705+02:00')
    ])
    expect(riga.timestamp.getTime()).toBe(utc.timestamp.getTime())
  })

  it('orders steps stored microseconds apart by their time', async () => {
    const messages = await load([
      entry('late', '2026-11-20T19:34:41.000003+00:00'),
      entry('early', '2026-11-20T19:34:41.000001+00:00'),
      entry('mid', '2026-11-20T19:34:41.000002+00:00')
    ])
    const sorted = [...messages].sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
    expect(sorted.map((m) => m.id)).toEqual(['early', 'mid', 'late'])
    expect(messages.every((m) => !Number.isNaN(m.timestamp.getTime()))).toBe(true)
  })
})
