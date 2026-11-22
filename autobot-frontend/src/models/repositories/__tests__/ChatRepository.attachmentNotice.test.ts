// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #21006: a reloaded chat renders a stored attachment notice through the same `chat.attachmentNotice.<code>`
 * path as the live stream, so a refreshed page still explains a dropped file.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api', getBackendUrl: () => 'http://backend' }))
vi.mock('@/i18n', () => ({
  default: {
    global: {
      t: (key: string, params: Record<string, unknown>) => `${key}|${params.filename}|${params.limit}`,
    },
  },
}))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

import { ChatRepository } from '../ChatRepository'
import { attachmentNoticeText } from '@/utils/attachmentNotice'

const stored = {
  id: 'n1',
  sender: 'system',
  text: 'English fallback stored by the backend',
  messageType: 'attachment_notice',
  metadata: { code: 'truncated', filename: 'big.txt' },
  timestamp: '2026-11-09 10:00:00',
}

describe('ChatRepository.getChatMessages stored attachment notices (#21006)', () => {
  beforeEach(() => {
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ data: { messages: [stored] } }),
    })
  })

  it('renders the same text as the live notice, not the stored fallback', async () => {
    const [message] = await new ChatRepository().getChatMessages('chat-1')
    expect(message.content).toBe(attachmentNoticeText({ code: 'truncated', filename: 'big.txt' }))
    expect(message.content).toBe('chat.attachmentNotice.truncated|big.txt|')
  })

  it('leaves an ordinary stored message text alone', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ data: { messages: [{ ...stored, messageType: 'response', text: 'hello' }] } }),
    })
    const [message] = await new ChatRepository().getChatMessages('chat-1')
    expect(message.content).toBe('hello')
  })
})
