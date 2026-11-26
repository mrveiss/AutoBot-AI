// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21997: the session list carries the active company's chats and, apart, the Unassigned ones.
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api', getBackendUrl: () => 'http://backend' }))

import { ChatRepository } from '../ChatRepository'

async function list(data: unknown) {
  const repo = new ChatRepository()
  vi.spyOn(repo as unknown as { get: () => Promise<unknown> }, 'get').mockResolvedValue({ data })
  return repo.getChatList()
}

describe('ChatRepository.getChatList Unassigned (#21997)', () => {
  it('flags the unassigned chats and keeps the company chats unflagged', async () => {
    const out = await list({ sessions: [{ id: 'a1', title: 'A' }], unassigned: [{ id: 'u1', title: 'U' }] })
    expect(out.map((c) => [c.id, c.unassigned])).toEqual([['a1', undefined], ['u1', true]])
  })

  it('lists a chat once when the backend returns it in both lists (no active company)', async () => {
    const out = await list({ sessions: [{ id: 'u1' }, { id: 'u2' }], unassigned: [{ id: 'u1' }, { id: 'u2' }] })
    expect(out.map((c) => c.id)).toEqual(['u1', 'u2'])
    expect(out.every((c) => c.unassigned === true)).toBe(true)
  })

  it('still reads a response without an unassigned list', async () => {
    const out = await list({ sessions: [{ id: 'a1' }] })
    expect(out.map((c) => c.id)).toEqual(['a1'])
  })
})
