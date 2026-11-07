// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** utils/authStorage -- the one SLM session reader/writer (#17856 row 8). */
import { describe, it, expect, beforeEach } from 'vitest'
import { clearSlmSession, readSlmToken, readSlmUserRaw, writeSlmToken, writeSlmUser } from './authStorage'

describe('SLM authStorage (#17856 row 8)', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('reads null when nothing is stored', () => {
    expect(readSlmToken()).toBeNull()
    expect(readSlmUserRaw()).toBeNull()
  })

  it('prefers the tab session over a legacy localStorage copy', () => {
    localStorage.setItem('slm_access_token', 'old')
    sessionStorage.setItem('slm_access_token', 'live')
    expect(readSlmToken()).toBe('live')
  })

  it('still reads a legacy localStorage-only session, so an upgrade keeps the operator signed in', () => {
    localStorage.setItem('slm_access_token', 'legacy')
    expect(readSlmToken()).toBe('legacy')
  })

  it('writes to the tab session only', () => {
    writeSlmToken('t')
    writeSlmUser('{"username":"a"}')
    expect(sessionStorage.getItem('slm_access_token')).toBe('t')
    expect(localStorage.getItem('slm_access_token')).toBeNull()
    expect(readSlmUserRaw()).toBe('{"username":"a"}')
  })

  it('clears token and user from both storages', () => {
    for (const s of [sessionStorage, localStorage]) {
      s.setItem('slm_access_token', 't')
      s.setItem('slm_user', 'u')
    }
    clearSlmSession()
    expect(readSlmToken()).toBeNull()
    expect(readSlmUserRaw()).toBeNull()
  })
})
