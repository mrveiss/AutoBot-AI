// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #21357: a resume that fails after the person switched chats still restores the card's own chat flag.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/models/controllers', () => ({ useChatController: () => ({ handleStreamingResponse: vi.fn() }) }))

import { useApprovalRouting } from '@/composables/useGraphApproval'
import { useChatStore } from '@/stores/useChatStore'

describe('graph approval across a chat switch (#21357)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    fetchWithAuth.mockReset()
  })

  it('keeps the pending flag true for the card chat when the POST fails after switching away and back', async () => {
    const store = useChatStore()
    const a = store.createNewSession('A')
    const b = store.createNewSession('B')
    store.switchToSession(a)
    const id = store.addMessage({
      content: 'approve?',
      sender: 'assistant',
      type: 'command_approval_request',
      metadata: { session_id: a, terminal_session_id: 'term-1', requires_approval: true, calls: [{ tool: 'crm' }] }
    })!
    store.setPendingApproval(true) // the card was raised in A

    let fail!: (v: unknown) => void
    fetchWithAuth.mockImplementation(() => new Promise((r) => { fail = r }))
    const attempt = useApprovalRouting(vi.fn())('term-1', true)
    store.switchToSession(b) // the person moves on during the POST
    expect(store.hasPendingApproval).toBe(false)
    fail({ ok: false, status: 500 })
    await expect(attempt).rejects.toMatchObject({ status: 500 })

    store.switchToSession(a)
    expect(store.hasPendingApproval).toBe(true)
    expect(store.currentMessages.find((m) => m.id === id)?.metadata?.approval_status).toBeUndefined()
  })
})
