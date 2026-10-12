// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// signInCount distinguishes a fresh sign-in from a session restore (#18240).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUserStore, type UserProfile } from '../useUserStore'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

describe('useUserStore.signInCount', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('counts login() calls', () => {
    const store = useUserStore()
    expect(store.signInCount).toBe(0)
    store.login({ id: 'u', username: 'u', displayName: 'U', role: 'user' } as UserProfile, { token: 't' })
    expect(store.signInCount).toBe(1)
  })

  it('does not count a session restored from storage', () => {
    localStorage.setItem('autobot_auth', JSON.stringify({ isAuthenticated: true, token: 't' }))
    localStorage.setItem('autobot_user', JSON.stringify({ id: 'u', username: 'u', displayName: 'U', role: 'user' }))
    const store = useUserStore()
    store.initializeFromStorage()
    expect(store.isAuthenticated).toBe(true)
    expect(store.signInCount).toBe(0)
  })
})
