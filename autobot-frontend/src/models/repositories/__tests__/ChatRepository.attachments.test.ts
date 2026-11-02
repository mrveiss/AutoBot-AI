// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #20195: a sent message carries the SERVER file ids of the uploaded files in `context.attachments`,
 * never browser File objects or anything that is not an id.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api', getBackendUrl: () => 'http://backend' }))

import { ChatRepository } from '../ChatRepository'

const sentContext = (): Record<string, unknown> => {
  const init = fetchWithAuth.mock.calls[0][1] as { body: string }
  return JSON.parse(init.body).context
}

describe('ChatRepository.sendMessage attachments (#20195)', () => {
  beforeEach(() => {
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({}),
    })
  })

  it('forwards the server file ids as strings', async () => {
    await new ChatRepository().sendMessage('hi', 'chat-1', { attachments: ['file-a', 'file-b'] })
    expect(sentContext().attachments).toEqual(['file-a', 'file-b'])
  })

  it('never forwards an object (a browser File stand-in) as an attachment', async () => {
    const options = { attachments: ['file-a', { id: 'x', name: 'n.txt', data: {} }] } as unknown as { attachments: string[] }
    await new ChatRepository().sendMessage('hi', 'chat-1', options)
    expect(sentContext().attachments).toEqual(['file-a'])
  })

  it('sends no attachments key when there are none', async () => {
    await new ChatRepository().sendMessage('hi', 'chat-1', { attachments: [] })
    expect(sentContext()).not.toHaveProperty('attachments')
  })
})
