// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * An approval card raised by the chat graph's interrupt answers through POST /chats/{id}/resume (#20195).
 *
 * The terminal approve route cannot reach a paused graph, so a card whose metadata names `calls` must post its
 * decision to resume and hand the SSE reply to the chat controller's stream consumer. A terminal card keeps the
 * terminal route, unchanged.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

type Card = { id: string; metadata: Record<string, unknown> }

const fetchWithAuth = vi.fn()
const handleStreamingResponse = vi.fn()
const fakeStore = {
  currentSessionId: 'chat-1',
  currentMessages: [] as Card[],
  updateMessageMetadata: vi.fn((id: string, updates: Record<string, unknown>) => {
    const card = fakeStore.currentMessages.find((m) => m.id === id)
    if (card) Object.assign(card.metadata, updates)
    return !!card
  }),
  setPendingApproval: vi.fn(),
  setTyping: vi.fn(),
}

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args) }))
vi.mock('@/models/controllers', () => ({ useChatController: () => ({ handleStreamingResponse }) }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ error: vi.fn(), warn: vi.fn(), debug: vi.fn() }) }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => fakeStore }))

import { isGraphApproval, useApprovalRouting } from '@/composables/useGraphApproval'

function seedCard(metadata: Record<string, unknown>) {
  const card = { id: 'm1', metadata: { terminal_session_id: 'term-1', requires_approval: true, ...metadata } }
  fakeStore.currentMessages = [card]
  return { store: fakeStore, id: card.id }
}

describe('graph-interrupt approval cards', () => {
  beforeEach(() => {
    fakeStore.currentMessages = []
    fakeStore.updateMessageMetadata.mockClear()
    fetchWithAuth.mockReset()
    handleStreamingResponse.mockReset()
    fetchWithAuth.mockResolvedValue({ ok: true })
  })

  it('tells a graph card from a terminal card by the calls it names', () => {
    expect(isGraphApproval({ calls: [{ tool: 'crm' }] })).toBe(true)
    expect(isGraphApproval({ command: 'ls' })).toBe(false)
    expect(isGraphApproval(undefined)).toBe(false)
  })

  it('posts the decision to /chats/{id}/resume and feeds the reply to the controller', async () => {
    const { store, id } = seedCard({ session_id: 'chat-1', calls: [{ tool: 'crm' }] })
    const terminal = vi.fn()
    const approve = useApprovalRouting(terminal)

    await approve('term-1', true)

    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
    const [url, init] = fetchWithAuth.mock.calls[0]
    expect(url).toMatch(/\/chats\/chat-1\/resume$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ approved: true, reason: '' })
    expect(handleStreamingResponse).toHaveBeenCalledWith({ ok: true })
    expect(terminal).not.toHaveBeenCalled()
    expect(store.currentMessages.find((m) => m.id === id)?.metadata?.approval_status).toBe('approved')
  })

  it('posts a denial with approved=false', async () => {
    seedCard({ session_id: 'chat-1', calls: [{ tool: 'crm' }] })
    await useApprovalRouting(vi.fn())('term-1', false)
    expect(JSON.parse(fetchWithAuth.mock.calls[0][1].body).approved).toBe(false)
  })

  it('leaves a terminal card on the terminal route', async () => {
    seedCard({ command: 'ls', command_id: 'c1' })
    const terminal = vi.fn()
    await useApprovalRouting(terminal)('term-1', true, undefined, 'c1', { command: 'ls', risk_level: 'low' })
    expect(fetchWithAuth).not.toHaveBeenCalled()
    expect(terminal).toHaveBeenCalledTimes(1)
    expect(terminal.mock.calls[0][0]).toBe('term-1')
  })

  it('does not feed the controller when resume is refused', async () => {
    seedCard({ session_id: 'chat-1', calls: [{ tool: 'crm' }] })
    fetchWithAuth.mockResolvedValue({ ok: false, status: 403 })
    await expect(useApprovalRouting(vi.fn())('term-1', true)).rejects.toThrow()
    expect(handleStreamingResponse).not.toHaveBeenCalled()
  })
})
