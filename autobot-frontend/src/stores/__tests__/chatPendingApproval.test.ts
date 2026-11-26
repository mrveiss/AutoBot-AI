// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #21357: a chat's pending-approval flag does not outlive the chat.
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/useChatStore'

describe('pending-approval flag lifetime (#21357)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('is dropped with a deleted chat and with a cleared store', () => {
    const store = useChatStore()
    const a = store.createNewSession('A')
    const b = store.createNewSession('B')
    store.setPendingApproval(true, a)
    store.setPendingApproval(true, b)

    store.deleteSession(a)
    expect(store.isPendingApproval(a)).toBe(false)
    expect(store.isPendingApproval(b)).toBe(true)

    store.clearAllSessions()
    expect(store.isPendingApproval(b)).toBe(false)
  })

  it('ignores a set for a chat that is gone, but still clears one', () => {
    const store = useChatStore()
    const a = store.createNewSession('A')
    store.deleteSession(a)
    store.setPendingApproval(true, a) // a late approval event for the deleted chat
    expect(store.isPendingApproval(a)).toBe(false)
  })
})
