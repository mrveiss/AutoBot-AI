// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * utils/authToken -- the one main-app reader of the stored JWT (#10861, #17856
 * row 8). ApiClient, fetchWithAuth and ChatRepository all ask it, so an
 * expired token is cleared and never sent by any of them.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { clearStoredAuth, readStoredAuthToken } from '../authToken'

const future = () => new Date(Date.now() + 60_000).toISOString()
const past = () => new Date(Date.now() - 60_000).toISOString()

function store(auth: unknown): void {
  localStorage.setItem('autobot_auth', JSON.stringify(auth))
  localStorage.setItem('autobot_user', '{"username":"u"}')
}

describe('readStoredAuthToken (#17856 row 8)', () => {
  beforeEach(() => localStorage.clear())

  it('returns a live token', () => {
    store({ token: 'jwt', expiresAt: future() })
    expect(readStoredAuthToken()).toBe('jwt')
  })

  it('returns a token that records no expiry', () => {
    store({ token: 'jwt' })
    expect(readStoredAuthToken()).toBe('jwt')
  })

  it('rejects an expired token and clears the stored session', () => {
    store({ token: 'jwt', expiresAt: past() })
    expect(readStoredAuthToken()).toBeNull()
    expect(localStorage.getItem('autobot_auth')).toBeNull()
    expect(localStorage.getItem('autobot_user')).toBeNull()
  })

  it('rejects the legacy single_user_mode marker without clearing', () => {
    store({ token: 'single_user_mode' })
    expect(readStoredAuthToken()).toBeNull()
  })

  it('returns null for absent or malformed storage', () => {
    expect(readStoredAuthToken()).toBeNull()
    localStorage.setItem('autobot_auth', '{not json')
    expect(readStoredAuthToken()).toBeNull()
  })
})

describe('clearStoredAuth', () => {
  it('removes the token and the user record', () => {
    store({ token: 'jwt' })
    clearStoredAuth()
    expect(localStorage.getItem('autobot_auth')).toBeNull()
    expect(localStorage.getItem('autobot_user')).toBeNull()
  })
})
