// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #21237: a chat reloaded while the graph waits on an approval gets the card back from the backend's history
 * entry, and it is the same card the live stream builds: its type survives, and its metadata names the calls and
 * the chat, so `isGraphApproval` routes the decision to `POST /chats/{id}/resume`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args) }))
vi.mock('@/config/ssot-config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/ssot-config')>()),
  getApiBase: () => '/api',
  getBackendUrl: () => 'http://backend',
}))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

import { ChatRepository } from '../ChatRepository'
import { isGraphApproval } from '@/composables/useGraphApproval'

const restoredApproval = {
  id: 'approval-abc',
  sender: 'assistant',
  type: 'command_approval_request',
  messageType: 'command_approval_request',
  text: 'Command approval required',
  timestamp: '2026-11-26 10:00:00',
  metadata: {
    requires_approval: true,
    session_id: 'chat-1',
    terminal_session_id: 'term-1',
    calls: [{ tool: 'execute_command', params: { command: 'touch x' } }],
  },
}

describe('ChatRepository.getChatMessages restored approval card (#21237)', () => {
  beforeEach(() => {
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ data: { messages: [restoredApproval] } }),
    })
  })

  it('keeps the approval type, its text and the metadata the resume needs', async () => {
    const [card] = await new ChatRepository().getChatMessages('chat-1')
    expect(card.type).toBe('command_approval_request')
    expect(card.content).toBe('Command approval required')
    expect(card.metadata?.requires_approval).toBe(true)
    expect(card.metadata?.session_id).toBe('chat-1')
  })

  it('is a graph approval, so its decision goes to the resume route', async () => {
    const [card] = await new ChatRepository().getChatMessages('chat-1')
    expect(isGraphApproval(card.metadata)).toBe(true)
  })
})
